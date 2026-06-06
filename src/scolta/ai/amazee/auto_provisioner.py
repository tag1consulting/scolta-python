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
        Returns True only on a successful first provisioning."""
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
