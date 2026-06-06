"""Token value object (port of ``Tag1\\Scolta\\Index\\Token``)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Token:
    stem: str
    original: str
    position: int
