"""Trial provisioning orchestration (port of AmazeeTrialProvisioner)."""

from __future__ import annotations

from collections.abc import Callable

from .client import AmazeeClient
from .model_resolver import AmazeeModelResolver
from .results import ProvisioningResult
from .storage import ConfigStorage


class AmazeeTrialProvisioner:
    def __init__(
        self,
        client: AmazeeClient,
        storage: ConfigStorage,
        has_existing_provider: Callable[[], bool] | None = None,
        model_resolver: AmazeeModelResolver | None = None,
    ) -> None:
        self.client = client
        self.storage = storage
        self.has_existing_provider = has_existing_provider
        self.model_resolver = model_resolver

    def provision(self, email: str = "") -> ProvisioningResult:
        if self.has_existing_provider is not None and self.has_existing_provider():
            return ProvisioningResult.skipped_existing_provider()

        result = self.client.provision_trial(email)
        self.storage.store(result.litellm_token, result.litellm_api_url, result.region)

        if self.model_resolver is not None:
            models = self.model_resolver.resolve(result.litellm_api_url, result.litellm_token)
            return ProvisioningResult.make_success(
                result.litellm_token,
                result.litellm_api_url,
                result.region,
                models["ai_model"],
                models["ai_expansion_model"],
            )
        return result
