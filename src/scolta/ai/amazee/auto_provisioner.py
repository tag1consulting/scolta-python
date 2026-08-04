"""Self-heal guard for stored managed-gateway credentials (port of AutoProvisioner)."""

from __future__ import annotations

from collections.abc import Callable

from .client import AmazeeClient
from .model_resolver import AmazeeModelResolver
from .storage import ConfigStorage


class AutoProvisioner:
    """Keeps already-stored managed-gateway credentials usable.

    This helper never establishes a managed gateway connection. Establishing one
    is an explicit caller action: an operator-initiated enable path calls
    :meth:`AmazeeTrialProvisioner.provision` directly. Nothing here does it on
    the caller's behalf, from an install hook, from a request path, or behind a
    flag.

    The name predates the policy and is kept for callers compiled against it.
    What remains is :meth:`ensure_ai_available`: a self-heal for credentials that
    are already stored but whose model names were never resolved.
    """

    @staticmethod
    def ensure_ai_available(
        storage: ConfigStorage,
        has_explicit_api_key: bool = False,
        on_models_resolved: Callable[[str, str], None] | None = None,
        client: AmazeeClient | None = None,
        has_resolved_models: Callable[[], bool] | None = None,
    ) -> bool:
        """Re-resolve model names for credentials that are already stored.

        This method never establishes a managed gateway connection, and it makes
        no outbound call at all unless credentials are already stored. It is a
        no-op when:

        - ``has_explicit_api_key`` is true (the caller has their own provider),
        - no credentials are stored — nothing to heal, and nothing is
          established here; that is :meth:`AmazeeTrialProvisioner.provision`,
          reached only from an explicit operator action, or
        - credentials are stored and ``has_resolved_models`` is absent or
          reports that model names are already resolved.

        The stored-credentials path deliberately does NOT validate that the
        stored key still works — credentials are revoked server-side when their
        lifecycle ends, and that is not announced at issue time, so a cheap
        lazy-init guard cannot know. Call-time auth failures are the reliable
        signal: :class:`KeyExpiryRecovery` detects them, records the failure for
        health, and flags the site for admin re-authentication without
        requesting replacement credentials.

        Stored credentials are, however, usable only once their model names have
        been resolved. Credentials stored while ``/model/info`` was unreachable
        carry no resolved models, leaving the caller to fall back to the dated
        config default — which the Amazee gateway rejects with HTTP 400, breaking
        AI permanently because this guard kept no-opping on the half-configured
        credentials. When the caller can confirm models are still unresolved (via
        ``has_resolved_models``), model resolution is re-attempted against the
        ALREADY-STORED key, so that state self-heals. Without that callback the
        historical no-op stands: the caller cannot tell us, and we must not
        re-resolve blindly on every request.

        Returns:
            Always ``False``. The return value is retained for callers written
            against the previous signature; nothing is established here, so
            there is no success to report.
        """
        if has_explicit_api_key:
            return False

        credentials = storage.load()
        if credentials is None:
            # POLICY: nothing is established here. Automatic enrollment was
            # removed outright — there is no automatic path and no flag-gated
            # one. A managed gateway connection is established only by an
            # explicit operator action that calls
            # AmazeeTrialProvisioner.provision(). With no stored credentials
            # this is a no-op that makes no outbound call.
            return False

        # Credentials are stored. Self-heal only the incomplete case — model
        # resolution never completed, leaving credentials with no models — and
        # only when the caller can confirm that state. Re-resolve against the
        # stored key and persist the result.
        if has_resolved_models is None or has_resolved_models():
            return False

        models = AmazeeModelResolver(client or AmazeeClient()).resolve(
            credentials["litellm_api_url"], credentials["litellm_token"]
        )
        if on_models_resolved is not None and (
            models["ai_model"] is not None or models["ai_expansion_model"] is not None
        ):
            on_models_resolved(models["ai_model"] or "", models["ai_expansion_model"] or "")

        return False
