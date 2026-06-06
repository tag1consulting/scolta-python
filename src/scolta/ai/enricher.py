"""Prompt enrichment hook.

Ports ``Tag1\\Scolta\\Prompt\\PromptEnricherInterface`` and ``NullEnricher``.
Allows site-specific context injection between prompt resolution and the LLM
call.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class PromptEnricher(ABC):
    @abstractmethod
    def enrich(self, resolved_prompt: str, prompt_name: str, context: dict | None = None) -> str:
        """Enrich a resolved prompt before it is sent to the AI provider.

        ``prompt_name`` is 'expand_query', 'summarize', or 'follow_up'.
        """


class NullEnricher(PromptEnricher):
    """No-op enricher that passes the prompt through unchanged."""

    def enrich(self, resolved_prompt: str, prompt_name: str, context: dict | None = None) -> str:
        return resolved_prompt
