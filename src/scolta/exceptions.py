"""Exception types, ported 1:1 from ``Tag1\\Scolta\\Exception``."""

from __future__ import annotations


class ApiKeyMissingException(RuntimeError):
    """Raised when an AI operation is attempted without an API key configured.

    Callers that catch this should degrade gracefully — returning an
    empty/null response rather than a server error — because the missing key
    is an expected configuration state rather than a transient failure.
    """


class ApiKeyInvalidException(RuntimeError):
    """Raised when the AI provider rejects the configured API key (HTTP 401).

    Callers should return a 401 response with an admin-visible message so site
    administrators can distinguish a bad key from a transient failure.
    """


class RateLimitException(RuntimeError):
    """Raised when the AI provider responds with HTTP 429 (rate limited).

    Callers should return a 429 response and include the ``retry_after`` value
    as a header so clients know when to retry.
    """

    def __init__(self, message: str = "", retry_after: str | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after
