"""Base AI service adapter.

Port of ``Tag1\\Scolta\\Service\\AiServiceAdapter``. Provides the shared
dual-path AI routing (try a platform-native AI integration first, fall back to
the built-in :class:`AiClient`), prompt resolution, lazy client instantiation,
and the budget-exception hook.
"""

from __future__ import annotations

from ..config import ScoltaConfig
from ..exceptions import ApiKeyMissingException
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

        When set, an auth-class failure (expired/revoked credentials) on any AI
        call is recorded so health reports AI as degraded and the site is
        flagged for admin re-authentication; the call still degrades gracefully
        (the original failure propagates, no retry). Without it (an explicit
        user-configured key, or a platform that has not adopted recovery yet)
        behavior is unchanged: the failure propagates.
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
            self._note_auth_failure(exc)
            raise

    def conversation(self, system_prompt: str, messages: list[dict], max_tokens: int = 512) -> str:
        try:
            result = self._try_framework_conversation(system_prompt, messages, max_tokens)
            if result is not None:
                return result
            return self._get_client().conversation(system_prompt, messages, max_tokens)
        except RuntimeError as exc:
            self._handle_possible_budget_exception(exc)
            self._note_auth_failure(exc)
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
            # Query expansion is a deterministic semantic mapping: pin it to
            # temperature 0 so the same query yields the same terms on every
            # uncached call. Summarize and follow-up keep the provider default
            # (None -> temperature field omitted).
            temperature = 0.0 if operation == "expand_query" else None
            return self._get_client().message(
                system_prompt, user_message, max_tokens, model, temperature
            )
        except RuntimeError as exc:
            self._handle_possible_budget_exception(exc)
            self._note_auth_failure(exc)
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
        """Get the built-in AiClient, refusing to build one with no provider.

        Scolta ships without a provider selected, and an unselected provider
        means AI is off — not that it is Anthropic. Constructing a client here
        would pick a vendor on the site's behalf, so instead this raises the
        :class:`ApiKeyMissingException` the callers already degrade on: the
        query goes out unexpanded and no summary is produced, which is what
        "AI off" looks like from the outside.
        """
        if not self._config.ai_provider.strip():
            raise ApiKeyMissingException(
                "No AI provider is selected, so AI features are off. Select one in the "
                "Scolta settings, or set the AI provider in configuration."
            )

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

    def _note_auth_failure(self, exc: RuntimeError) -> None:
        """Record an auth-class failure of the stored Amazee credentials.

        When recovery is wired and the failure means the stored credentials are
        no longer accepted (never budget-exhaustion — KeyExpiryRecovery excludes
        it), this marks AI as degraded for health and flags the site for admin
        re-authentication. It never retries: the caller's original exception
        propagates and the request degrades gracefully (unexpanded query / no
        summary). A no-op when recovery is not wired.
        """
        if self._key_recovery is not None:
            self._key_recovery.handle_auth_failure(exc)
