"""Expired trial-key detection and guarded re-provisioning (port of KeyExpiryRecovery).

Amazee.ai trial keys are revoked server-side when the trial lifecycle ends.
The expiry is NOT announced at provisioning time (verified against the live
API: ``/auth/generate-trial-access`` returns only ``created_at``, and the
LiteLLM key's own ``expires`` is a year out while observed trial revocation is
on the order of a day) — so the only reliable signal is the auth failure the
LiteLLM proxy returns on the next inference call. Without this class that
failure was swallowed by the expand/summarize graceful-degrade path while
``AutoProvisioner.ensure_ai_available()`` kept no-opping on the stored dead
credentials: AI stayed down fleet-wide with health reporting
``ai_configured: true`` (django demo outage, 2026-06-09).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from ...cache import CacheDriver
from ...exceptions import ApiKeyInvalidException
from .auto_provisioner import AutoProvisioner
from .budget_decorator import BudgetAwareProviderDecorator
from .client import AmazeeClient
from .storage import ConfigStorage

_DEFAULT_LOGGER = logging.getLogger("scolta.ai.amazee")


class KeyExpiryRecovery:
    """Detects Amazee trial-key auth failures at call time and recovers by
    re-provisioning through the existing provisioner path.

    Two cache-backed markers (any :class:`~scolta.cache.CacheDriver`)
    coordinate the recovery across requests:

    - an auth-failure marker, recorded on every detected failure and read by
      health checks so "AI configured" stops implying "AI usable";
    - a re-provision-attempt marker with a TTL window, so a fleet of failing
      requests triggers exactly one re-provision attempt per window instead of
      hammering the provisioning API in a loop.

    Budget-exhaustion errors are explicitly excluded — those belong to
    :class:`BudgetAwareProviderDecorator` and must not trigger re-provisioning
    (a re-provisioned trial key would reset the spend ceiling, which is the
    upgrade flow's job, not an error-recovery side effect).
    """

    #: Cache key for the "last AI call failed authentication" marker. Health
    #: checks read this (see HealthChecker) to report AI as unusable while the
    #: stored credentials are known-bad. Public so adapters and health wiring
    #: reference one definition.
    CACHE_KEY_AUTH_FAILURE = "scolta_amazee_auth_failure"

    #: Cache key for the one-attempt-per-window re-provision guard.
    CACHE_KEY_REPROVISION_ATTEMPT = "scolta_amazee_reprovision_attempt"

    #: How long a recorded auth failure keeps health reporting AI unusable
    #: before a fresh failing call must re-confirm it, in seconds.
    AUTH_FAILURE_TTL = 3600

    # Message substrings that identify an auth-class failure from the LiteLLM
    # proxy. The proxy returns the expired/invalid-key error inside an HTTP
    # 400/401 body, which AiClient preserves in the exception message chain
    # (a 401 additionally becomes ApiKeyInvalidException, matched by type).
    _AUTH_FAILURE_MARKERS = (
        "expired_key",
        "invalid_api_key",
        "authentication error",
        "invalid proxy server token",
    )

    def __init__(
        self,
        storage: ConfigStorage,
        cache: CacheDriver,
        client: AmazeeClient | None = None,
        failure_window_seconds: int = 600,
        logger: object | None = None,
    ) -> None:
        """:param storage: Adapter credential store (same instance the provisioner uses).
        :param cache: Cache for the failure/attempt markers.
        :param client: Optional pre-configured client (testing / base-URL override).
        :param failure_window_seconds: Minimum spacing between re-provision attempts.
        :param logger: Duck-typed logger (defaults to ``scolta.ai.amazee``).
        """
        self._storage = storage
        self._cache = cache
        self._client = client
        self._failure_window_seconds = failure_window_seconds
        self._logger = logger if logger is not None else _DEFAULT_LOGGER

    @staticmethod
    def is_auth_failure(exc: BaseException) -> bool:
        """Whether an exception (anywhere in its cause chain) is an auth-class
        failure for which re-provisioning is the correct recovery.

        Budget-exhaustion errors return False even though they also surface as
        4xx responses — they route to the budget path, never to re-provisioning.
        """
        if BudgetAwareProviderDecorator.is_budget_error(exc):
            return False

        cause: BaseException | None = exc
        while cause is not None:
            if isinstance(cause, ApiKeyInvalidException):
                return True
            message = str(cause).lower()
            if any(marker in message for marker in KeyExpiryRecovery._AUTH_FAILURE_MARKERS):
                return True
            cause = cause.__cause__
        return False

    def handle_auth_failure(
        self,
        exc: BaseException,
        on_models_resolved: Callable[[str, str], None] | None = None,
    ) -> bool:
        """Record an auth failure and attempt a one-shot re-provision.

        Returns True only when the exception is an auth failure AND a
        re-provision was attempted in this call AND it succeeded — i.e. fresh
        credentials are now in storage and a retry makes sense. Returns False
        for non-auth errors, when another attempt already ran inside the
        current failure window, or when re-provisioning failed.

        :param exc: The AI call failure.
        :param on_models_resolved: Forwarded to the provisioner so adapters can
            persist resolved model names.
        """
        if not self.is_auth_failure(exc):
            return False

        self.record_auth_failure()

        return self._attempt_reprovision(on_models_resolved)

    def record_auth_failure(self) -> None:
        """Mark the stored credentials as auth-failing so health reports AI as
        unusable until recovery succeeds or the marker ages out."""
        self._cache.set(self.CACHE_KEY_AUTH_FAILURE, time.time(), self.AUTH_FAILURE_TTL)

    def is_auth_failing(self) -> bool:
        """Whether the stored credentials are known to be auth-failing.

        Cache-marker read only — never a live API call, so health checks can
        call this on every request.
        """
        return self.marker_active(
            self._cache.get(self.CACHE_KEY_AUTH_FAILURE), self.AUTH_FAILURE_TTL
        )

    def credentials(self) -> dict | None:
        """The currently stored credentials, or None when none are stored.

        After a successful :meth:`handle_auth_failure` these are the fresh
        post-re-provision credentials callers rebuild their client from.
        """
        return self._storage.load()

    @staticmethod
    def marker_active(value: object, ttl_seconds: int) -> bool:
        """Whether a cached marker value is present and still inside its window.

        PHP runs one short-lived process per request and relies on the platform
        cache's TTL eviction; Python serves from a long-running process and the
        bundled :class:`~scolta.cache.InMemoryCacheDriver` does not enforce
        TTLs. Markers therefore store their timestamp and the window is checked
        on read — TTL-enforcing backends (e.g. the Django cache) simply evict
        the entry as well, so both backend kinds agree on the semantics.
        """
        if not value:
            return False
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return time.time() - value < ttl_seconds
        return True

    def _attempt_reprovision(
        self, on_models_resolved: Callable[[str, str], None] | None
    ) -> bool:
        """Attempt one re-provision through the existing provisioner path,
        guarded to a single attempt per failure window."""
        if self.marker_active(
            self._cache.get(self.CACHE_KEY_REPROVISION_ATTEMPT), self._failure_window_seconds
        ):
            return False

        # Set the guard before attempting: a failed attempt must also wait
        # out the window, otherwise every failing request retries provisioning.
        self._cache.set(
            self.CACHE_KEY_REPROVISION_ATTEMPT, time.time(), self._failure_window_seconds
        )

        self._logger.warning(
            "Scolta: stored Amazee credentials failed authentication, attempting re-provision"
        )

        provisioned = AutoProvisioner.reprovision(self._storage, on_models_resolved, self._client)

        if provisioned:
            # AI is usable again — stop health from reporting the old failure.
            self._cache.set(self.CACHE_KEY_AUTH_FAILURE, False, 1)
            self._logger.info("Scolta: Amazee re-provisioning succeeded, fresh credentials stored")
        else:
            self._logger.error("Scolta: Amazee re-provisioning failed, AI remains unavailable")

        return provisioned
