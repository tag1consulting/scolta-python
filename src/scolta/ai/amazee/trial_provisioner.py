"""Trial provisioning orchestration (port of AmazeeTrialProvisioner)."""

from __future__ import annotations

from collections.abc import Callable

from .client import AmazeeClient
from .connection_source import AmazeeConnectionSource
from .model_resolver import AmazeeModelResolver
from .results import ProvisioningResult
from .storage import ConfigStorage, ProvenanceAwareConfigStorage


class AmazeeTrialProvisioner:
    """Establishes the free Amazee.ai demo connection, on an explicit request.

    **Nothing calls this on its own.** It is reached only from an operator
    action — the "Try the demo" button in an admin UI, a provisioning management
    command, or a first-use path in a headless framework where a developer set
    ``ai_provider`` to ``amazee`` in code. :class:`AutoProvisioner` deliberately
    does not call it: that class self-heals credentials that are already stored
    and establishes nothing.
    """

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
        """Provision the free demo, optionally bound to an email address.

        ``email`` defaults to empty — anonymous provisioning — which is what the
        "Try the demo" action in the admin UIs does, so that trying Scolta's AI
        costs an operator no input at all.
        """
        if self.has_existing_provider is not None and self.has_existing_provider():
            return ProvisioningResult.skipped_existing_provider()

        result = self.client.provision_trial(email)
        self.storage.store(result.litellm_token, result.litellm_api_url, result.region)
        if isinstance(self.storage, ProvenanceAwareConfigStorage):
            self.storage.store_connection_source(AmazeeConnectionSource.DEMO)

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
