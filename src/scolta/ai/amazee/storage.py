"""Credential storage abstraction (port of ConfigStorageInterface)."""

from __future__ import annotations

from abc import ABC, abstractmethod


class ConfigStorage(ABC):
    @abstractmethod
    def store(self, litellm_token: str, litellm_api_url: str, region: str) -> None: ...

    @abstractmethod
    def load(self) -> dict | None:
        """Return {'litellm_token','litellm_api_url','region'} or None."""

    @abstractmethod
    def clear(self) -> None: ...
