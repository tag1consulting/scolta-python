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
    ) -> bool:
        """Provision a free trial unless AI is already configured. Idempotent;
        no-op when an explicit key exists or credentials are already stored.
        Returns True only on a successful first provisioning.

        The stored-credentials no-op deliberately does NOT validate that the
        stored key still works — trial keys are revoked server-side when the
        trial ends, and that expiry is not announced at provisioning time, so a
        cheap install-hook/lazy-init guard cannot know. Call-time auth failures
        are the reliable signal: :class:`KeyExpiryRecovery` detects them and
        recovers through :meth:`reprovision`, which bypasses this no-op.
        """
        if has_explicit_api_key:
            return False
        if storage.load() is not None:
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

        if on_models_resolved is not None and (result.ai_model is not None or result.ai_expansion_model is not None):
            on_models_resolved(result.ai_model or "", result.ai_expansion_model or "")
        return True

    @staticmethod
    def reprovision(
        storage: ConfigStorage,
        on_models_resolved: Callable[[str, str], None] | None = None,
        client: AmazeeClient | None = None,
    ) -> bool:
        """Replace stored (known-bad) credentials with a freshly provisioned trial.

        The expired-key recovery entry point: unlike :meth:`ensure_ai_available`,
        stored credentials do not short-circuit — they are cleared first, then a
        fresh trial is provisioned and stored through the same provisioner path.
        Callers are responsible for rate-limiting (see :class:`KeyExpiryRecovery`,
        which guards this behind a one-attempt-per-window marker).

        Provisioning failures are caught internally and returned as False; the
        old credentials are already cleared at that point, which is correct —
        they were known-bad, and an empty store lets :meth:`ensure_ai_available`
        retry on the next lazy-init pass.

        Returns True if fresh credentials were provisioned and stored.
        """
        storage.clear()

        return AutoProvisioner.ensure_ai_available(storage, False, on_models_resolved, client)
