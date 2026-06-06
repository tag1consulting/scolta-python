"""Budget-aware AiClient decorator (port of BudgetAwareProviderDecorator)."""

from __future__ import annotations

from ..client import AiClient
from .exceptions import AmazeeBudgetExceededException

_BUDGET_MESSAGE = "Budget has been exceeded!"


class BudgetAwareProviderDecorator:
    def __init__(self, client: AiClient) -> None:
        self._client = client

    def message(self, system_prompt, user_message, max_tokens=1024, model=None) -> str:
        try:
            return self._client.message(system_prompt, user_message, max_tokens, model)
        except RuntimeError as exc:
            self._rethrow_if_budget_exceeded(exc)
            raise

    def conversation(self, system_prompt, messages, max_tokens=1024, model=None) -> str:
        try:
            return self._client.conversation(system_prompt, messages, max_tokens, model)
        except RuntimeError as exc:
            self._rethrow_if_budget_exceeded(exc)
            raise

    def get_client(self) -> AiClient:
        return self._client

    @staticmethod
    def _rethrow_if_budget_exceeded(exc: BaseException) -> None:
        cause: BaseException | None = exc
        while cause is not None:
            if _BUDGET_MESSAGE in str(cause):
                raise AmazeeBudgetExceededException(exc)
            cause = cause.__cause__
