"""Ported from tests/Http/AiControllerTraitTest.php (1:1)."""

from scolta.ai.controller import AiControllerMixin
from scolta.ai.endpoint import AiEndpointHandler
from scolta.ai.enricher import NullEnricher
from scolta.cache import NullCacheDriver
from scolta.config import ScoltaConfig


class ConcreteAiController(AiControllerMixin):
    def __init__(self):
        self.last_cache_ttl = -1

    def _resolve_cache(self, cache_ttl):
        self.last_cache_ttl = cache_ttl
        return NullCacheDriver()

    def _get_cache_generation(self):
        return 0

    def _resolve_enricher(self):
        return NullEnricher()


def test_create_handler_returns_ai_endpoint_handler():
    handler = ConcreteAiController().create_handler(object(), ScoltaConfig())
    assert isinstance(handler, AiEndpointHandler)


def test_create_handler_passes_cache_ttl_to_resolve_cache():
    controller = ConcreteAiController()
    config = ScoltaConfig()
    config.cache_ttl = 300
    controller.create_handler(object(), config)
    assert controller.last_cache_ttl == 300


def test_create_handler_passes_zero_cache_ttl():
    controller = ConcreteAiController()
    config = ScoltaConfig()
    config.cache_ttl = 0
    controller.create_handler(object(), config)
    assert controller.last_cache_ttl == 0
