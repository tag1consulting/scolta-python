"""Centralised AiEndpointHandler construction for platform controllers.

Port of ``Tag1\\Scolta\\Http\\AiControllerTrait`` as a mixin. Platform
controllers (e.g. Django views) mix this in and implement the three hooks to
provide the platform cache driver, generation counter, and prompt enricher,
then call :meth:`create_handler` instead of constructing the handler inline.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..cache import CacheDriver
from ..config import ScoltaConfig
from .endpoint import AiEndpointHandler
from .enricher import PromptEnricher


class AiControllerMixin(ABC):
    @abstractmethod
    def _resolve_cache(self, cache_ttl: int) -> CacheDriver:
        """Return a platform cache driver (a NullCacheDriver when ttl is 0)."""

    @abstractmethod
    def _get_cache_generation(self) -> int:
        """Return the current cache-invalidation generation (0 if none)."""

    @abstractmethod
    def _resolve_enricher(self) -> PromptEnricher:
        """Return the prompt enricher for this controller."""

    def create_handler(self, ai_service: object, config: ScoltaConfig) -> AiEndpointHandler:
        return AiEndpointHandler(
            ai_service=ai_service,
            cache=self._resolve_cache(config.cache_ttl),
            generation=self._get_cache_generation(),
            cache_ttl=config.cache_ttl,
            max_follow_ups=config.max_follow_ups,
            prompt_enricher=self._resolve_enricher(),
            ai_languages=config.ai_languages,
            ai_expand_query=config.ai_expand_query,
            ai_summarize=config.ai_summarize,
            ai_summary_max_tokens=config.ai_summary_max_tokens,
            expand_primary_weight=config.expand_primary_weight,
            sortable_fields=config.sortable_fields,
            sortable_field_descriptions=config.sortable_field_descriptions,
            filter_fields=config.filter_fields,
            filter_field_descriptions=config.filter_field_descriptions,
        )
