"""Budget-aware AiClient decorator (port of BudgetAwareProviderDecorator)."""

from __future__ import annotations

from ..client import AiClient
from .exceptions import AmazeeBudgetExceededException


class BudgetAwareProviderDecorator:
    #: The exact message the Amazee LiteLLM proxy returns on budget exhaustion.
    #: Public (mirroring the PHP ``BUDGET_MESSAGE`` constant) so classifiers
    #: reference one definition instead of duplicating the magic string.
    BUDGET_MESSAGE = "Budget has been exceeded!"

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
    def is_budget_error(exc: BaseException) -> bool:
        """Whether an exception (anywhere in its cause chain) is the Amazee
        budget-exhaustion error — by :class:`AmazeeBudgetExceededException`
        type or by the :attr:`BUDGET_MESSAGE` proxy message.

        The single classification API (port of the PHP ``isBudgetError()``);
        :class:`KeyExpiryRecovery` uses it to keep budget exhaustion routed to
        the budget path instead of triggering re-provisioning.
        """
        cause: BaseException | None = exc
        while cause is not None:
            if isinstance(cause, AmazeeBudgetExceededException):
                return True
            if BudgetAwareProviderDecorator.BUDGET_MESSAGE in str(cause):
                return True
            cause = cause.__cause__
        return False

    @staticmethod
    def _rethrow_if_budget_exceeded(exc: BaseException) -> None:
        if BudgetAwareProviderDecorator.is_budget_error(exc):
            raise AmazeeBudgetExceededException(exc)
