"""Amazee credential auth-failure detection and clean degradation (port of KeyExpiryRecovery).

Amazee.ai credentials are revoked server-side when their lifecycle ends. The
expiry is NOT announced at issue time (verified against the live API:
``/auth/generate-trial-access`` returns only ``created_at``, and the LiteLLM
key's own ``expires`` is a year out while observed revocation is on the order of
a day) — so the only reliable signal is the auth failure the LiteLLM proxy
returns on the next inference call. Without this class that failure was swallowed
by the expand/summarize graceful-degrade path while
``AutoProvisioner.ensure_ai_available()`` kept no-opping on the stored dead
credentials: AI stayed down fleet-wide with health reporting
``ai_configured: true`` (django demo outage, 2026-06-09).

On an auth-class failure this class leaves AI off and records two cache-backed
markers (any :class:`~scolta.cache.CacheDriver`) so the rest of the system
reflects the real state across requests:

- an auth-failure marker, recorded on every detected failure and read by
  :class:`~scolta.health.HealthChecker` so "AI configured" stops implying "AI
  usable"; it ages out so a transient blip self-clears once calls succeed again;
- an upgrade-needed marker, set when the stored credentials are no longer
  accepted, that persists until the admin re-authenticates. Adapter admin UIs
  read :meth:`is_upgrade_needed` to prompt the admin to continue by entering an
  email, which runs the verification flow (``AmazeeClient.request_verification_code``
  + ``AmazeeClient.sign_in``, used by ``AmazeeAccountUpgrader``). On a successful
  upgrade the adapter calls :meth:`clear_upgrade_needed`.

The stored credentials are never cleared and no new credentials are requested on
this path; recovery is a deliberate, admin-initiated step. Budget-exhaustion
errors are excluded — those belong to :class:`BudgetAwareProviderDecorator` and
follow the budget path, not this one.
"""

from __future__ import annotations

import logging
import time

from ...cache import CacheDriver
from ...exceptions import ApiKeyInvalidException
from .budget_decorator import BudgetAwareProviderDecorator
from .storage import ConfigStorage

_DEFAULT_LOGGER = logging.getLogger("scolta.ai.amazee")


class KeyExpiryRecovery:
    """Detects Amazee credential auth failures at call time and degrades cleanly.

    Two cache-backed markers (any :class:`~scolta.cache.CacheDriver`) coordinate
    the degraded state across requests:

    - an auth-failure marker, recorded on every detected failure and read by
      health checks so "AI configured" stops implying "AI usable"; it ages out
      so a transient blip self-clears once calls succeed again;
    - a persistent upgrade-needed marker, set when the stored credentials are no
      longer accepted, that admin UIs read to prompt the site to re-authenticate.

    Budget-exhaustion errors are explicitly excluded — those belong to
    :class:`BudgetAwareProviderDecorator` and follow the budget path, not this one.
    """

    #: Cache key for the "last AI call failed authentication" marker. Health
    #: checks read this (see HealthChecker) to report AI as unusable while the
    #: stored credentials are known-bad. Public so adapters and health wiring
    #: reference one definition.
    CACHE_KEY_AUTH_FAILURE = "scolta_amazee_auth_failure"

    #: Cache key for the persistent "credentials no longer accepted, admin must
    #: re-authenticate" marker. Unlike the auth-failure marker this does NOT age
    #: out on its own: once the stored credentials stop being accepted, AI stays
    #: off until the admin completes the email re-authentication flow and the
    #: adapter clears it via :meth:`clear_upgrade_needed`. Public so adapter
    #: admin UIs reference one definition.
    CACHE_KEY_UPGRADE_NEEDED = "scolta_amazee_upgrade_needed"

    #: How long a recorded auth failure keeps health reporting AI unusable
    #: before a fresh failing call must re-confirm it, in seconds.
    AUTH_FAILURE_TTL = 3600

    #: How long the upgrade-needed marker is retained, in seconds. Long enough to
    #: outlast any cache backend's practical eviction window so the prompt does
    #: not disappear on its own; the marker is meant to be cleared explicitly by
    #: :meth:`clear_upgrade_needed` once the admin re-authenticates, not to expire.
    UPGRADE_NEEDED_TTL = 31536000

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
        logger: object | None = None,
    ) -> None:
        """:param storage: Adapter credential store (same instance the provisioner uses).
        :param cache: Cache for the failure/upgrade markers.
        :param logger: Duck-typed logger (defaults to ``scolta.ai.amazee``).
        """
        self._storage = storage
        self._cache = cache
        self._logger = logger if logger is not None else _DEFAULT_LOGGER

    @staticmethod
    def is_auth_failure(exc: BaseException) -> bool:
        """Whether an exception (anywhere in its cause chain) is an auth-class
        failure of the stored Amazee credentials.

        Budget-exhaustion errors return False even though they also surface as
        4xx responses — they route to the budget path, never here.
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

    def handle_auth_failure(self, exc: BaseException) -> bool:
        """Handle an AI call failure on the auto-provisioned Amazee path.

        For an auth-class failure (the stored credentials are no longer accepted)
        this records the auth-failure marker so health reports AI as degraded,
        sets the persistent upgrade-needed marker so admin UIs can prompt the
        site to re-authenticate, and leaves the stored credentials untouched. It
        always returns False: there is nothing to retry, so the caller degrades
        gracefully (unexpanded query / no summary). Non-auth errors are ignored
        and also return False.

        :param exc: The AI call failure.
        """
        if not self.is_auth_failure(exc):
            return False

        self.record_auth_failure()
        self.flag_upgrade_needed()

        self._logger.warning(
            "Scolta: stored Amazee credentials were not accepted; "
            "AI is off until re-authentication."
        )

        return False

    def record_auth_failure(self) -> None:
        """Mark the stored credentials as auth-failing so health reports AI as
        unusable until calls succeed again or the marker ages out."""
        self._cache.set(self.CACHE_KEY_AUTH_FAILURE, time.time(), self.AUTH_FAILURE_TTL)

    def is_auth_failing(self) -> bool:
        """Whether the stored credentials are known to be auth-failing.

        Cache-marker read only — never a live API call, so health checks can
        call this on every request.
        """
        return self.marker_active(
            self._cache.get(self.CACHE_KEY_AUTH_FAILURE), self.AUTH_FAILURE_TTL
        )

    def flag_upgrade_needed(self) -> None:
        """Set the persistent upgrade-needed marker."""
        self._cache.set(self.CACHE_KEY_UPGRADE_NEEDED, time.time(), self.UPGRADE_NEEDED_TTL)

    def is_upgrade_needed(self) -> bool:
        """Whether the stored credentials need an admin re-authentication.

        Adapter admin UIs read this to show the "enter your email to continue"
        prompt. Cache-marker read only — never a live API call.
        """
        return self.marker_active(
            self._cache.get(self.CACHE_KEY_UPGRADE_NEEDED), self.UPGRADE_NEEDED_TTL
        )

    def clear_upgrade_needed(self) -> None:
        """Clear the upgrade-needed marker after a successful re-authentication.

        Adapters call this once the admin has completed the email verification
        flow and fresh credentials are in storage.
        """
        self._cache.set(self.CACHE_KEY_UPGRADE_NEEDED, False, 1)

    def credentials(self) -> dict | None:
        """The currently stored credentials, or None when none are stored."""
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
