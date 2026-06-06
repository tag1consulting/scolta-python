"""Cache abstraction for AI endpoint response caching.

Ports ``Tag1\\Scolta\\Cache\\CacheDriverInterface`` and ``NullCacheDriver``.
Each platform adapter implements this with its native backend (Django cache,
etc.). A simple in-memory driver is provided for tests and standalone use.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class CacheDriver(ABC):
    @abstractmethod
    def get(self, key: str) -> Any:
        """Return the cached value, or None if not found."""

    @abstractmethod
    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        """Store a value with a time-to-live in seconds."""


class NullCacheDriver(CacheDriver):
    """No-op driver for when caching is disabled (cache_ttl <= 0)."""

    def get(self, key: str) -> Any:
        return None

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        pass


class InMemoryCacheDriver(CacheDriver):
    """Simple dict-backed cache (TTL not enforced) for tests/standalone use."""

    def __init__(self) -> None:
        self._store: dict[str, Any] = {}

    def get(self, key: str) -> Any:
        return self._store.get(key)

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        self._store[key] = value
