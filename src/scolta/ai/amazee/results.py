"""Amazee result DTOs (ported 1:1)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProvisioningResult:
    STATUS_PROVISIONED = "provisioned"
    STATUS_SKIPPED_EXISTING_PROVIDER = "skipped_existing_provider"
    STATUS_FAILED = "failed"

    success: bool
    litellm_token: str
    litellm_api_url: str
    region: str
    error: str | None = None
    status: str = STATUS_PROVISIONED
    ai_model: str | None = None
    ai_expansion_model: str | None = None

    @classmethod
    def make_success(
        cls, litellm_token, litellm_api_url, region, ai_model=None, ai_expansion_model=None
    ):
        return cls(
            True,
            litellm_token,
            litellm_api_url,
            region,
            status=cls.STATUS_PROVISIONED,
            ai_model=ai_model,
            ai_expansion_model=ai_expansion_model,
        )

    @classmethod
    def failure(cls, error: str):
        return cls(False, "", "", "", error=error, status=cls.STATUS_FAILED)

    @classmethod
    def skipped_existing_provider(cls):
        return cls(True, "", "", "", status=cls.STATUS_SKIPPED_EXISTING_PROVIDER)


@dataclass(frozen=True)
class UpgradeResult:
    success: bool
    litellm_token: str
    litellm_api_url: str
    region: str
    error: str | None = None

    @classmethod
    def make_success(cls, litellm_token, litellm_api_url, region):
        return cls(True, litellm_token, litellm_api_url, region)

    @classmethod
    def failure(cls, error: str):
        return cls(False, "", "", "", error=error)
