"""Persisted memory-budget configuration (port of ``Config\\MemoryBudgetConfig``
and the ``MemoryBudgetRepository`` contract)."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections.abc import Callable

from .index.memory_budget import MemoryBudget
from .index.memory_telemetry import MemoryBudgetSuggestion

_NAMED_PROFILES = ("conservative", "balanced", "aggressive")
_BYTE_STRING = re.compile(r"^\d+[KkMmGg]?$")


def _is_valid_memory_string(value: str) -> bool:
    return value in _NAMED_PROFILES or bool(_BYTE_STRING.match(value))


class MemoryBudgetConfig:
    def __init__(
        self, profile: str, custom_bytes: int | None = None, chunk_size: int | None = None
    ) -> None:
        self._profile = profile
        self._custom_bytes = custom_bytes
        self._chunk_size = chunk_size

    @classmethod
    def defaults(cls) -> MemoryBudgetConfig:
        return cls("conservative")

    @classmethod
    def load(cls, data: dict) -> MemoryBudgetConfig:
        profile = data.get("profile", "conservative")
        custom_bytes = int(data["custom_bytes"]) if data.get("custom_bytes") is not None else None
        raw_chunk = data.get("chunk_size")
        chunk_size = int(raw_chunk) if raw_chunk is not None and int(raw_chunk) >= 1 else None
        if not _is_valid_memory_string(str(profile)):
            profile = "conservative"
        return cls(profile, custom_bytes or None, chunk_size)

    def to_memory_budget(self) -> MemoryBudget:
        memory_str = str(self._custom_bytes) if self._custom_bytes is not None else self._profile
        return MemoryBudget.from_options(memory_str, self._chunk_size)

    def validate(self) -> list[str]:
        errors = []
        if not _is_valid_memory_string(self._profile):
            errors.append(
                f'Invalid memory_budget profile "{self._profile}". '
                f'Must be a named profile ({", ".join(_NAMED_PROFILES)}) or a byte value like "256M".'
            )
        if self._custom_bytes is not None and self._custom_bytes < 0:
            errors.append("custom_bytes must be a non-negative integer.")
        if self._chunk_size is not None and self._chunk_size < 1:
            errors.append("chunk_size must be a positive integer.")
        return errors

    @staticmethod
    def from_cli_and_config(
        cli_budget_option: str | None,
        cli_chunk_option: str | None,
        config_reader: Callable[[], dict],
    ) -> MemoryBudget:
        config = config_reader()
        budget_str = (
            cli_budget_option
            if cli_budget_option is not None
            else config.get("profile", "conservative")
        )
        raw_chunk = cli_chunk_option if cli_chunk_option is not None else config.get("chunk_size")
        chunk_size = int(raw_chunk) if raw_chunk is not None and int(raw_chunk) >= 1 else None
        return MemoryBudget.from_options(str(budget_str), chunk_size)

    def suggest(self) -> dict:
        return MemoryBudgetSuggestion.suggest()

    def profile(self) -> str:
        return self._profile

    def custom_bytes(self) -> int | None:
        return self._custom_bytes

    def chunk_size(self) -> int | None:
        return self._chunk_size

    def to_array(self) -> dict:
        return {
            "profile": self._profile,
            "custom_bytes": self._custom_bytes,
            "chunk_size": self._chunk_size,
        }


class MemoryBudgetRepository(ABC):
    @abstractmethod
    def load(self) -> MemoryBudgetConfig: ...

    @abstractmethod
    def save(self, config: MemoryBudgetConfig) -> None: ...

    @abstractmethod
    def resolve(self) -> MemoryBudget: ...
