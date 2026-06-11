"""Base AI service adapter.

Port of ``Tag1\\Scolta\\Service\\AiServiceAdapter``. Provides the shared
dual-path AI routing (try a platform-native AI integration first, fall back to
the built-in :class:`AiClient`), prompt resolution, lazy client instantiation,
and the budget-exception hook.
"""

from __future__ import annotations

from ..config import ScoltaConfig
from . import prompts
from .amazee.key_expiry_recovery import KeyExpiryRecovery
from .client import AiClient


class AiServiceAdapter:
    def __init__(self, config: ScoltaConfig) -> None:
        self._config = config
        self._client: AiClient | None = None
        self._key_recovery: KeyExpiryRecovery | None = None

    def set_key_expiry_recovery(self, recovery: KeyExpiryRecovery) -> None:
        """Wire Amazee key-expiry recovery into the AI call path.

        When set, an auth-class failure (expired/revoked trial key) on any AI
        call triggers a one-shot re-provision through the recovery's guarded
        path and, on success, a single retry with the fresh credentials.
        Without it (an explicit user-configured key, or a platform that has
        not adopted recovery yet) behavior is unchanged: the failure
        propagates.
        """
        self._key_recovery = recovery

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
            if self._recover_from_auth_failure(exc):
                return self._get_client().message(system_prompt, user_message, max_tokens)
            raise

    def conversation(self, system_prompt: str, messages: list[dict], max_tokens: int = 512) -> str:
        try:
            result = self._try_framework_conversation(system_prompt, messages, max_tokens)
            if result is not None:
                return result
            return self._get_client().conversation(system_prompt, messages, max_tokens)
        except RuntimeError as exc:
            self._handle_possible_budget_exception(exc)
            if self._recover_from_auth_failure(exc):
                return self._get_client().conversation(system_prompt, messages, max_tokens)
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
            if self._recover_from_auth_failure(exc):
                model = (
                    self._config.ai_expansion_model
                    if operation == "expand_query" and self._config.ai_expansion_model != ""
                    else None
                )
                return self._get_client().message(system_prompt, user_message, max_tokens, model)
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

    def _try_framework_ai(
        self, system_prompt: str, user_message: str, max_tokens: int
    ) -> str | None:
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

    def _recover_from_auth_failure(self, exc: RuntimeError) -> bool:
        """Attempt expired-key recovery and prepare a fresh client for one retry.

        Returns True only when recovery is wired, the failure is auth-class
        (never budget-exhaustion — KeyExpiryRecovery excludes it), the guarded
        re-provision succeeded, and fresh credentials are available. The
        caller then retries the original request exactly once; a failure of
        that retry propagates normally (the recovery's window guard prevents
        another re-provision attempt).
        """
        if self._key_recovery is None:
            return False

        if not self._key_recovery.handle_auth_failure(exc):
            return False

        credentials = self._key_recovery.credentials()
        if credentials is None:
            return False

        self._client = self._create_recovered_client(credentials)

        return True

    def _create_recovered_client(self, credentials: dict) -> AiClient:
        """Build an AiClient from freshly re-provisioned Amazee credentials.

        Recovered credentials are by definition Amazee LiteLLM ones, so the
        provider is the OpenAI-compatible path regardless of what the (stale)
        config says. Override in platform subclasses to inject a custom HTTP
        client, mirroring :meth:`_create_client`.
        """
        config = self._config.to_ai_client_config()
        config["provider"] = "openai"
        config["api_key"] = credentials["litellm_token"]
        config["base_url"] = credentials["litellm_api_url"]

        return AiClient(config)
