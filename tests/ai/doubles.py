"""Test doubles ported from the PHP AiEndpointHandlerTest doubles."""

from __future__ import annotations

from scolta.cache import CacheDriver
from scolta.exceptions import (
    ApiKeyInvalidException,
    ApiKeyMissingException,
    RateLimitException,
)


class MockAiService:
    """In-memory mock AI service implementing the duck-typed interface."""

    def __init__(
        self,
        response: str = "",
        throw_on_message: bool = False,
        throw_on_conversation: bool = False,
        throw_api_key_missing: bool = False,
        throw_api_key_invalid: bool = False,
        throw_rate_limit: bool = False,
        rate_limit_retry_after: str | None = None,
    ) -> None:
        self.response = response
        self.throw_on_message = throw_on_message
        self.throw_on_conversation = throw_on_conversation
        self.throw_api_key_missing = throw_api_key_missing
        self.throw_api_key_invalid = throw_api_key_invalid
        self.throw_rate_limit = throw_rate_limit
        self.rate_limit_retry_after = rate_limit_retry_after
        self.call_count = 0

    def get_expand_prompt(self) -> str:
        return "Expand the following search query."

    def get_summarize_prompt(self) -> str:
        return "Summarize the following search results."

    def get_follow_up_prompt(self) -> str:
        return "Continue the conversation."

    def message(self, system_prompt: str, user_message: str, max_tokens: int) -> str:
        self._throw_if_configured()
        self.call_count += 1
        return self.response

    def message_for_operation(
        self, operation: str, system_prompt: str, user_message: str, max_tokens: int
    ) -> str:
        return self.message(system_prompt, user_message, max_tokens)

    def conversation(self, system_prompt: str, messages: list, max_tokens: int) -> str:
        if self.throw_on_conversation:
            raise RuntimeError("AI service unavailable")
        self._throw_if_configured()
        self.call_count += 1
        return self.response

    def _throw_if_configured(self) -> None:
        if self.throw_api_key_missing:
            raise ApiKeyMissingException("Scolta AI API key not configured.")
        if self.throw_api_key_invalid:
            raise ApiKeyInvalidException("Scolta AI API key is invalid or expired.")
        if self.throw_rate_limit:
            raise RateLimitException(
                "Scolta AI API rate limit reached.", self.rate_limit_retry_after
            )
        if self.throw_on_message:
            raise RuntimeError("AI service unavailable")


class PromptCapturingAiService(MockAiService):
    """Captures the system prompt passed to message()/conversation()."""

    def __init__(self, response: str = "", capture_conversation: bool = False) -> None:
        super().__init__(response)
        self.capture_conversation = capture_conversation
        self.last_system_prompt: str | None = None

    def message(self, system_prompt: str, user_message: str, max_tokens: int) -> str:
        self.last_system_prompt = system_prompt
        return super().message(system_prompt, user_message, max_tokens)

    def conversation(self, system_prompt: str, messages: list, max_tokens: int) -> str:
        self.last_system_prompt = system_prompt
        return super().conversation(system_prompt, messages, max_tokens)


class TrackingCacheDriver(CacheDriver):
    """Cache driver that tracks how many times get()/set() are called."""

    def __init__(self) -> None:
        self.get_calls = 0
        self.set_calls = 0
        self._store: dict = {}

    def get(self, key: str):
        self.get_calls += 1
        return self._store.get(key)

    def set(self, key: str, value, ttl_seconds: int) -> None:
        self.set_calls += 1
        self._store[key] = value


class SpyEnricher:
    """Spy enricher that records calls and prepends a prefix."""

    def __init__(self, prefix: str = "") -> None:
        self.prefix = prefix
        self.call_count = 0
        self.last_prompt_name = None
        self.last_context = None
        self.last_resolved_prompt = None

    def enrich(self, resolved_prompt: str, prompt_name: str, context: dict | None = None) -> str:
        self.call_count += 1
        self.last_resolved_prompt = resolved_prompt
        self.last_prompt_name = prompt_name
        self.last_context = context
        return self.prefix + resolved_prompt


class SpyLogger:
    """Logger spy that records error() calls (duck-typed)."""

    def __init__(self) -> None:
        self.errors: list[str] = []

    def error(self, msg, *args, **kwargs) -> None:
        self.errors.append(str(msg))
