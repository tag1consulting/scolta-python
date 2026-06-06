"""AiClient transport tests (httpx MockTransport).

Mirrors the behaviour of the PHP AiClient (Guzzle): Anthropic vs
OpenAI-compatible request shaping, model selection, base_url path completion,
and HTTP error -> typed-exception mapping.
"""

import json

import httpx
import pytest

from scolta.ai.client import AiClient
from scolta.exceptions import (
    ApiKeyInvalidException,
    ApiKeyMissingException,
    RateLimitException,
)


def _client(config, handler):
    transport = httpx.MockTransport(handler)
    return AiClient(config, http_client=httpx.Client(transport=transport))


def test_anthropic_request_shape():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = request.headers
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"content": [{"text": "hello"}]})

    client = _client({"provider": "anthropic", "api_key": "sk-ant", "model": "claude-x"}, handler)
    result = client.message("system", "user msg", max_tokens=256)

    assert result == "hello"
    assert captured["url"] == "https://api.anthropic.com/v1/messages"
    assert captured["headers"]["x-api-key"] == "sk-ant"
    assert captured["headers"]["anthropic-version"] == "2023-06-01"
    assert captured["body"]["model"] == "claude-x"
    assert captured["body"]["system"] == "system"
    assert captured["body"]["max_tokens"] == 256
    assert captured["body"]["messages"] == [{"role": "user", "content": "user msg"}]


def test_openai_request_shape_prepends_system_message():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = request.headers
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "hi"}}]})

    client = _client(
        {"provider": "openai", "api_key": "sk-oai", "model": "gpt-x"}, handler
    )
    result = client.message("sys", "u")

    assert result == "hi"
    assert captured["url"] == "https://api.openai.com/v1/chat/completions"
    assert captured["headers"]["authorization"] == "Bearer sk-oai"
    assert captured["body"]["messages"][0] == {"role": "system", "content": "sys"}
    assert captured["body"]["messages"][1] == {"role": "user", "content": "u"}


def test_openai_base_url_origin_only_gets_path_appended():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"choices": [{"message": {"content": "x"}}]})

    client = _client(
        {"provider": "openai", "api_key": "k", "base_url": "http://localhost:11434"}, handler
    )
    client.message("sys", "u")
    assert captured["url"] == "http://localhost:11434/v1/chat/completions"


def test_openai_base_url_with_path_left_untouched():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"choices": [{"message": {"content": "x"}}]})

    client = _client(
        {"provider": "openai", "api_key": "k", "base_url": "http://gw/v1/chat/completions"}, handler
    )
    client.message("sys", "u")
    assert captured["url"] == "http://gw/v1/chat/completions"


def test_model_override_per_call():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"content": [{"text": "ok"}]})

    client = _client({"api_key": "k", "model": "default-model"}, handler)
    client.message("s", "u", model="override-model")
    assert captured["body"]["model"] == "override-model"


def test_missing_api_key_raises_before_request():
    def handler(request):  # pragma: no cover - must never be called
        raise AssertionError("request should not be sent without an API key")

    client = _client({"api_key": ""}, handler)
    with pytest.raises(ApiKeyMissingException):
        client.message("s", "u")


def test_401_maps_to_api_key_invalid():
    client = _client({"api_key": "k"}, lambda r: httpx.Response(401, json={"error": "bad"}))
    with pytest.raises(ApiKeyInvalidException):
        client.message("s", "u")


def test_429_maps_to_rate_limit_with_retry_after():
    def handler(request):
        return httpx.Response(429, headers={"Retry-After": "42"}, json={})

    client = _client({"api_key": "k"}, handler)
    with pytest.raises(RateLimitException) as ei:
        client.message("s", "u")
    assert ei.value.retry_after == "42"


def test_429_without_retry_after():
    client = _client({"api_key": "k"}, lambda r: httpx.Response(429, json={}))
    with pytest.raises(RateLimitException) as ei:
        client.message("s", "u")
    assert ei.value.retry_after is None


def test_500_maps_to_runtime_error():
    client = _client({"api_key": "k"}, lambda r: httpx.Response(500, json={}))
    with pytest.raises(RuntimeError):
        client.message("s", "u")


def test_malformed_json_raises_runtime_error():
    client = _client({"api_key": "k"}, lambda r: httpx.Response(200, content=b"not json"))
    with pytest.raises(RuntimeError, match="malformed JSON"):
        client.message("s", "u")


def test_empty_content_returns_empty_string():
    client = _client({"api_key": "k"}, lambda r: httpx.Response(200, json={}))
    assert client.message("s", "u") == ""


def test_conversation_sends_all_messages_anthropic():
    captured = {}

    def handler(request):
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"content": [{"text": "r"}]})

    client = _client({"api_key": "k"}, handler)
    msgs = [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"},
            {"role": "user", "content": "c"}]
    client.conversation("sys", msgs)
    assert captured["body"]["messages"] == msgs
