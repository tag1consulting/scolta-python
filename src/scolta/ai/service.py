"""Base AI service adapter.

Port of ``Tag1\\Scolta\\Service\\AiServiceAdapter``. Provides the shared
dual-path AI routing (try a platform-native AI integration first, fall back to
the built-in :class:`AiClient`), prompt resolution, lazy client instantiation,
and the budget-exception hook.
"""

from __future__ import annotations

from ..config import ScoltaConfig
from . import prompts
from .client import AiClient


class AiServiceAdapter:
    def __init__(self, config: ScoltaConfig) -> None:
        self._config = config
        self._client: AiClient | None = None

    def get_config(self) -> ScoltaConfig:
        return self._config

    # -- public AI calls ----------------------------------------------------

    def message(self, system_prompt: str, user_message: str, max_tokens: int = 512) -> str:
        try:
            result = self._try_framework_ai(system_prompt, user_message, max_tokens)
            if result is not None:
                return result
            return self._get_client().message(system_prompt, user_message, max_tokens)
        except RuntimeError as exc:
            self._handle_possible_budget_exception(exc)
            raise

    def conversation(self, system_prompt: str, messages: list[dict], max_tokens: int = 512) -> str:
        try:
            result = self._try_framework_conversation(system_prompt, messages, max_tokens)
            if result is not None:
                return result
            return self._get_client().conversation(system_prompt, messages, max_tokens)
        except RuntimeError as exc:
            self._handle_possible_budget_exception(exc)
            raise

    def message_for_operation(
        self, operation: str, system_prompt: str, user_message: str, max_tokens: int = 512
    ) -> str:
        try:
            result = self._try_framework_ai(system_prompt, user_message, max_tokens)
            if result is not None:
                return result

            model = (
                self._config.ai_expansion_model
                if operation == "expand_query" and self._config.ai_expansion_model != ""
                else None
            )
            return self._get_client().message(system_prompt, user_message, max_tokens, model)
        except RuntimeError as exc:
            self._handle_possible_budget_exception(exc)
            raise

    # -- prompt resolution --------------------------------------------------

    def get_expand_prompt(self) -> str:
        if self._config.prompt_expand_query:
            return self._config.prompt_expand_query
        return self.resolve_prompt(prompts.EXPAND_QUERY)

    def get_summarize_prompt(self) -> str:
        if self._config.prompt_summarize:
            return self._config.prompt_summarize
        return self.resolve_prompt(prompts.SUMMARIZE)

    def get_follow_up_prompt(self) -> str:
        if self._config.prompt_follow_up:
            return self._config.prompt_follow_up
        return self.resolve_prompt(prompts.FOLLOW_UP)

    def resolve_prompt(self, template: str) -> str:
        return prompts.resolve(template, self._config.site_name, self._config.site_description)

    # -- overridable hooks --------------------------------------------------

    def _get_client(self) -> AiClient:
        if self._client is None:
            self._client = self._create_client()
        return self._client

    def _create_client(self) -> AiClient:
        return AiClient(self._config.to_ai_client_config())

    def _try_framework_ai(self, system_prompt: str, user_message: str, max_tokens: int) -> str | None:
        """Override to route through a platform AI layer; None falls back."""
        return None

    def _try_framework_conversation(
        self, system_prompt: str, messages: list[dict], max_tokens: int
    ) -> str | None:
        """Override to route through a platform AI layer; None falls back."""
        return None

    def _handle_possible_budget_exception(self, exc: RuntimeError) -> None:
        """No-op by default. Platform adapters override to convert/notify on
        budget-exhaustion errors before the original exception propagates."""
