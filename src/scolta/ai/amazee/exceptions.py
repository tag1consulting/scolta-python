"""Amazee exception types (ported 1:1)."""

from __future__ import annotations


class AmazeeApiException(RuntimeError):
    """The Amazee.ai API returned an error or an unexpected response."""

    def __init__(self, message: str, status_code: int = 0) -> None:
        super().__init__(message)
        self.status_code = status_code

    def get_status_code(self) -> int:
        return self.status_code


class AmazeeBudgetExceededException(RuntimeError):
    """The account's AI budget has been exhausted (HTTP 429, budget message)."""

    def __init__(self, previous: BaseException | None = None) -> None:
        super().__init__("Amazee.ai AI budget has been exceeded. Upgrade your plan to continue.")
        self.__cause__ = previous
