"""Account upgrade flow (port of AmazeeAccountUpgrader)."""

from __future__ import annotations

from .client import AmazeeClient
from .results import UpgradeResult
from .storage import ConfigStorage


class AmazeeAccountUpgrader:
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
        result = self.client.create_private_key(session_token, region_id)
        self.storage.store(result.litellm_token, result.litellm_api_url, result.region)
        return result
