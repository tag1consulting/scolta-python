"""Idempotent auto-provisioning guard (port of AutoProvisioner)."""

from __future__ import annotations

from collections.abc import Callable

from .client import AmazeeClient
from .exceptions import AmazeeApiException
from .model_resolver import AmazeeModelResolver
from .results import ProvisioningResult
from .storage import ConfigStorage
from .trial_provisioner import AmazeeTrialProvisioner


class AutoProvisioner:
    @staticmethod
    def ensure_ai_available(
        storage: ConfigStorage,
        has_explicit_api_key: bool = False,
        on_models_resolved: Callable[[str, str], None] | None = None,
        client: AmazeeClient | None = None,
        has_resolved_models: Callable[[], bool] | None = None,
    ) -> bool:
        """Provision a free trial unless AI is already configured. Idempotent;
        no-op when an explicit key exists or credentials are already stored.
        Returns True only when a fresh trial was provisioned.

        The stored-credentials no-op deliberately does NOT validate that the
        stored key still works — trial keys are revoked server-side when the
        trial ends, and that expiry is not announced at provisioning time, so a
        cheap install-hook/lazy-init guard cannot know. Call-time auth failures
        are the reliable signal: :class:`KeyExpiryRecovery` detects them, records
        the failure for health, and flags the site for admin re-authentication
        without requesting replacement credentials.

        Stored credentials are treated as a *complete* provision only once their
        model names are resolved. A provision whose ``/model/info`` call failed
        stores the token+url with no models, leaving the caller to fall back to
        the dated config default — which the Amazee gateway rejects with HTTP
        400, breaking AI permanently because this guard kept no-opping on the
        half-provisioned credentials. When the caller can confirm models are
        still unresolved (via ``has_resolved_models``), model resolution is
        re-attempted against the ALREADY-STORED key — never a fresh trial, which
        would waste a server-side-limited allocation — so the incomplete-provision
        state self-heals. Without that callback the historical no-op stands: the
        caller cannot tell us, and we must not re-resolve blindly every request.
        """
        if has_explicit_api_key:
            return False

        credentials = storage.load()
        if credentials is not None:
            # Already provisioned. Self-heal only an incomplete provision — one
            # whose model resolution failed, leaving credentials with no models
            # — and only when the caller can confirm that state. Re-resolve
            # against the stored key (not a new trial) and persist the result.
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

        amazee_client = client or AmazeeClient()
        provisioner = AmazeeTrialProvisioner(
            amazee_client, storage, None, AmazeeModelResolver(amazee_client)
        )
        try:
            result = provisioner.provision()
        except AmazeeApiException:
            return False

        if not result.success or result.status != ProvisioningResult.STATUS_PROVISIONED:
            return False

        if on_models_resolved is not None and (
            result.ai_model is not None or result.ai_expansion_model is not None
        ):
            on_models_resolved(result.ai_model or "", result.ai_expansion_model or "")
        return True
