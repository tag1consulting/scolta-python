"""Memory budget profiles (port of ``Tag1\\Scolta\\Index\\MemoryBudget``).

Advisory budget shaping chunk sizes, flush thresholds and merge fan-in. The
runtime default is always conservative; larger profiles are opt-in.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_MIB = 1024 * 1024


@dataclass(frozen=True)
class MemoryBudget:
    profile: str
    _chunk_size: int
    _fragment_flush_bytes: int
    _word_index_chunk_bytes: int
    _merge_open_file_handles: int
    _total_budget_bytes: int
    _token_cache_chunk_bytes: int

    @classmethod
    def conservative(cls) -> MemoryBudget:
        return cls("conservative", 50, 40_000, 40_000, 50, 96 * _MIB, 4 * _MIB)

    @classmethod
    def balanced(cls) -> MemoryBudget:
        return cls("balanced", 200, 160_000, 160_000, 200, 384 * _MIB, 16 * _MIB)

    @classmethod
    def aggressive(cls) -> MemoryBudget:
        return cls("aggressive", 500, 512_000, 512_000, 500, 1024 * _MIB, 64 * _MIB)

    @classmethod
    def from_bytes(cls, num_bytes: int) -> MemoryBudget:
        if num_bytes >= 768 * _MIB:
            return cls.aggressive()
        if num_bytes >= 192 * _MIB:
            return cls.balanced()
        return cls.conservative()

    @classmethod
    def from_string(cls, value: str) -> MemoryBudget:
        v = value.strip().lower()
        if v == "conservative":
            return cls.conservative()
        if v == "balanced":
            return cls.balanced()
        if v == "aggressive":
            return cls.aggressive()
        return cls.from_bytes(_parse_byte_string(v))

    @classmethod
    def default(cls) -> MemoryBudget:
        return cls.conservative()

    @classmethod
    def from_options(
        cls, memory_budget: str = "conservative", chunk_size: int | None = None
    ) -> MemoryBudget:
        budget = cls.from_string(memory_budget)
        if chunk_size is not None and chunk_size >= 1:
            return budget.with_chunk_size(chunk_size)
        return budget

    def with_chunk_size(self, chunk_size: int) -> MemoryBudget:
        return MemoryBudget(
            self.profile,
            chunk_size,
            self._fragment_flush_bytes,
            self._word_index_chunk_bytes,
            max(chunk_size, self._merge_open_file_handles),
            self._total_budget_bytes,
            self._token_cache_chunk_bytes,
        )

    def chunk_size(self) -> int:
        return self._chunk_size

    def fragment_flush_bytes(self) -> int:
        return self._fragment_flush_bytes

    def word_index_chunk_bytes(self) -> int:
        return self._word_index_chunk_bytes

    def merge_open_file_handles(self) -> int:
        return self._merge_open_file_handles

    def total_budget_bytes(self) -> int:
        return self._total_budget_bytes

    def token_cache_chunk_bytes(self) -> int:
        return self._token_cache_chunk_bytes


def _parse_byte_string(value: str) -> int:
    if value in ("", "0"):
        return 0
    m = re.match(r"^(\d+)", value)
    num = int(m.group(1)) if m else 0
    unit = value.rstrip()[-1:].lower()
    if unit == "g":
        return num * 1024 * 1024 * 1024
    if unit == "m":
        return num * _MIB
    if unit == "k":
        return num * 1024
    return int(value) if value.isdigit() else 0
