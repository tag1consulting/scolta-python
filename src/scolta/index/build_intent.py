"""Build intent value object + factory (port of BuildIntent / BuildIntentFactory)."""

from __future__ import annotations

from dataclasses import dataclass, field

from .memory_budget import MemoryBudget


@dataclass(frozen=True)
class BuildIntent:
    """What kind of index build to run: 'fresh' | 'resume' | 'restart'."""

    mode: str
    total_pages: int | None
    memory_budget: MemoryBudget
    source_meta: dict = field(default_factory=dict)

    @classmethod
    def fresh(cls, total_pages: int, budget: MemoryBudget, source_meta: dict | None = None):
        return cls("fresh", total_pages, budget, source_meta or {})

    @classmethod
    def resume(cls, budget: MemoryBudget):
        return cls("resume", None, budget, {})

    @classmethod
    def restart(cls, total_pages: int, budget: MemoryBudget, source_meta: dict | None = None):
        return cls("restart", total_pages, budget, source_meta or {})

    def is_fresh(self) -> bool:
        """True for fresh and restart — both wipe existing state."""
        return self.mode in ("fresh", "restart")


class BuildIntentFactory:
    @staticmethod
    def from_flags(resume: bool, restart: bool, total_count: int, budget: MemoryBudget) -> BuildIntent:
        if resume:
            return BuildIntent.resume(budget)
        if restart:
            return BuildIntent.restart(total_count, budget)
        return BuildIntent.fresh(total_count, budget)
