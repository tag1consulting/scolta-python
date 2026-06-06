"""Provider-agnostic AI client for LLM API calls.

Port of ``Tag1\\Scolta\\AiClient`` on httpx (Guzzle -> httpx is ~1:1).
Supports Anthropic's native API and any OpenAI-compatible chat-completions
endpoint (Ollama, LiteLLM and self-hosted gateways via the OpenAI-compatible
``base_url`` path).
"""

from __future__ import annotations

from urllib.parse import urlsplit

import httpx

from ..exceptions import (
    ApiKeyInvalidException,
    ApiKeyMissingException,
    RateLimitException,
)

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_API_VERSION = "2023-06-01"
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"


class AiClient:
    def __init__(self, config: dict, http_client: httpx.Client | None = None) -> None:
        self.provider = config.get("provider", "anthropic")
        self.api_key = config.get("api_key", "")
        self.model = config.get("model", "claude-sonnet-4-5-20250929")
        self.api_version = config.get("api_version", ANTHROPIC_API_VERSION)
        self.timeout = int(config.get("timeout", 30))

        if self.provider == "openai":
            base_url = config.get("base_url", OPENAI_API_URL)
            # If only a domain/origin is provided (no path), append the standard
            # OpenAI chat completions path — supports LiteLLM and other proxies
            # that return a base URL without a trailing API path.
            path = urlsplit(base_url).path or "/"
            if path in ("", "/"):
                base_url = base_url.rstrip("/") + "/v1/chat/completions"
            self.base_url = base_url
        else:
            self.base_url = config.get("base_url", ANTHROPIC_API_URL)

        self._http = http_client if http_client is not None else httpx.Client()

    def message(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 1024,
        model: str | None = None,
    ) -> str:
        """Send a single-turn message and return the response text."""
        return self._send_request(
            system_prompt,
            [{"role": "user", "content": user_message}],
            max_tokens,
            model,
        )

    def conversation(
        self,
        system_prompt: str,
        messages: list[dict],
        max_tokens: int = 1024,
        model: str | None = None,
    ) -> str:
        """Send a multi-turn conversation and return the response text."""
        return self._send_request(system_prompt, messages, max_tokens, model)

    def _send_request(
        self,
        system_prompt: str,
        messages: list[dict],
        max_tokens: int,
        model: str | None,
    ) -> str:
        if not self.api_key:
            raise ApiKeyMissingException(
                "Scolta AI API key not configured. Set the api_key in your "
                "platform's Scolta configuration."
            )

        use_model = model or self.model

        try:
            if self.provider == "openai":
                return self._send_openai(system_prompt, messages, max_tokens, use_model)
            return self._send_anthropic(system_prompt, messages, max_tokens, use_model)
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status == 401:
                raise ApiKeyInvalidException(
                    "Scolta AI API key is invalid or expired. Verify the key in "
                    "your Scolta configuration."
                ) from exc
            if status == 429:
                retry_after = exc.response.headers.get("Retry-After") or None
                raise RateLimitException(
                    "Scolta AI API rate limit reached.", retry_after
                ) from exc
            raise RuntimeError(f"Scolta AI API request failed: {exc}") from exc
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Scolta AI API request failed: {exc}") from exc

    def _send_anthropic(
        self, system_prompt: str, messages: list[dict], max_tokens: int, model: str
    ) -> str:
        response = self._http.post(
            self.base_url,
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": self.api_version,
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": max_tokens,
                "system": system_prompt,
                "messages": messages,
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = self._parse_json(response)
        try:
            return data["content"][0]["text"]
        except (KeyError, IndexError, TypeError):
            return ""

    def _send_openai(
        self, system_prompt: str, messages: list[dict], max_tokens: int, model: str
    ) -> str:
        all_messages = [{"role": "system", "content": system_prompt}, *messages]
        response = self._http.post(
            self.base_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": max_tokens,
                "messages": all_messages,
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = self._parse_json(response)
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            return ""

    @staticmethod
    def _parse_json(response: httpx.Response):
        try:
            return response.json()
        except ValueError as exc:
            raise RuntimeError(
                f"Scolta AI API returned malformed JSON: {exc}"
            ) from exc
