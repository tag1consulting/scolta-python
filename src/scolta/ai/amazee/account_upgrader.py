"""Account upgrade flow (port of AmazeeAccountUpgrader)."""

from __future__ import annotations

from .client import AmazeeClient
from .connection_source import AmazeeConnectionSource
from .results import UpgradeResult
from .storage import ConfigStorage, ProvenanceAwareConfigStorage


class AmazeeAccountUpgrader:
    """Connects a site to an amazee.ai account, by email.

    The only way to reach a real amazee.ai account, and email-only by design: it
    mirrors amazee.ai's own ``ai_provider_amazeeio`` Drupal module, where an
    operator never generates or pastes an API key. Signing in returns the
    account's credentials and Scolta persists them. There is deliberately no
    bring-your-own-key path — an operator who already holds an account attaches
    it by signing in with that account's email, and the same flow creates the
    account when it does not exist yet.

    It serves two operator journeys with the same steps: connecting an account
    from a clean install, and continuing after the demo credit runs out, which
    :class:`KeyExpiryRecovery` flags with its upgrade-needed marker.
    """

    def __init__(self, client: AmazeeClient, storage: ConfigStorage) -> None:
        self.client = client
        self.storage = storage

    def request_verification_code(self, email: str) -> None:
        self.client.request_verification_code(email)

    def sign_in(self, email: str, code: str) -> str:
        return self.client.sign_in(email, code)

    def list_regions(self, session_token: str) -> list:
        return self.client.list_regions(session_token)

    def upgrade(self, session_token: str, region_id: str) -> UpgradeResult:
        """Provision a private AI key in the given region and store it.

        New credentials replace any existing stored credentials — including a
        demo connection this account is replacing — and the connection source is
        recorded as ``ACCOUNT`` when the store supports it.
        """
        result = self.client.create_private_key(session_token, region_id)
        self.storage.store(result.litellm_token, result.litellm_api_url, result.region)
        if isinstance(self.storage, ProvenanceAwareConfigStorage):
            self.storage.store_connection_source(AmazeeConnectionSource.ACCOUNT)
        return result
