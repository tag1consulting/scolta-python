"""Progress reporter protocol + no-op (ported 1:1)."""

from __future__ import annotations

from abc import ABC, abstractmethod


class ProgressReporter(ABC):
    @abstractmethod
    def start(self, total_steps: int, label: str) -> None: ...

    @abstractmethod
    def advance(self, steps: int = 1, detail: str | None = None) -> None: ...

    @abstractmethod
    def finish(self, summary: str | None = None) -> None: ...


class NullProgressReporter(ProgressReporter):
    def start(self, total_steps: int, label: str) -> None:
        pass

    def advance(self, steps: int = 1, detail: str | None = None) -> None:
        pass

    def finish(self, summary: str | None = None) -> None:
        pass
