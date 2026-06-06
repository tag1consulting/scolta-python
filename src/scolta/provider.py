"""AI provider response DTO, ported from ``Tag1\\Scolta\\Provider\\AiResponse``."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AiResponse:
    content: str
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""
