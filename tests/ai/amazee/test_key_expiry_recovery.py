"""Ported from tests/AiProvider/Amazee/KeyExpiryRecoveryTest.php (1:1 intent).

Regression (django demo, 2026-06-09): an Amazee trial key expired server-side,
every LiteLLM call returned 400 expired_key, and nothing detected it — expand
silently echoed the query for ~24h while ensure_ai_available() kept no-opping
on the stored dead credentials.
"""

from types import SimpleNamespace

import httpx

from scolta.ai.amazee import (
    AmazeeBudgetExceededException,
    AmazeeClient,
    BudgetAwareProviderDecorator,
    ConfigStorage,
    KeyExpiryRecovery,
)
from scolta.cache import InMemoryCacheDriver
from scolta.exceptions import ApiKeyInvalidException

FRESH_TRIAL_RESPONSE = {
    "key": {
        "litellm_token": "sk-fresh-token",
        "litellm_api_url": "https://llm.test.amazee.ai",
        "region": "test-region",
    }
}
MODEL_INFO_RESPONSE = {
    "data": [{"model_name": "claude-sonnet-4-5"}, {"model_name": "claude-haiku-4-5"}]
}


class MemoryStorage(ConfigStorage):
    def __init__(self, stored=None):
        self._data = stored

    def store(self, litellm_token, litellm_api_url, region):
        self._data = {
            "litellm_token": litellm_token,
            "litellm_api_url": litellm_api_url,
            "region": region,
        }

    def load(self):
        return self._data

    def clear(self):
        self._data = None


def _expired_storage():
    return MemoryStorage(
        {
            "litellm_token": "sk-expired-token",
            "litellm_api_url": "https://llm.test.amazee.ai",
            "region": "test-region",
        }
    )


def _amazee_client(trial_calls: list, trial_status: int = 200) -> AmazeeClient:
    """Mocked provisioning API; records every trial-provisioning request."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/auth/generate-trial-access":
            trial_calls.append(request.url.path)
            if trial_status != 200:
                return httpx.Response(trial_status, json={"detail": "server error"})
            return httpx.Response(200, json=FRESH_TRIAL_RESPONSE)
        if request.url.path == "/model/info":
            return httpx.Response(200, json=MODEL_INFO_RESPONSE)
        return httpx.Response(404, json={})

    return AmazeeClient(http_client=httpx.Client(transport=httpx.MockTransport(handler)))


def _make_recovery(trial_calls: list, trial_status: int = 200, failure_window_seconds: int = 600):
    storage = _expired_storage()
    cache = InMemoryCacheDriver()
    recovery = KeyExpiryRecovery(
        storage=storage,
        cache=cache,
        client=_amazee_client(trial_calls, trial_status),
        failure_window_seconds=failure_window_seconds,
    )
    return recovery, storage, cache


# -- is_auth_failure() classification ------------------------------------------


def test_api_key_invalid_exception_is_auth_failure():
    exc = ApiKeyInvalidException("Scolta AI API key is invalid or expired.")
    assert KeyExpiryRecovery.is_auth_failure(exc) is True


def test_expired_key_message_is_auth_failure():
    # LiteLLM returns the expired-key error inside an HTTP 400 body, which
    # AiClient wraps in a generic RuntimeError with the body in the message.
    exc = RuntimeError(
        'Scolta AI API request failed: Client error: 400 {"error": {"message": '
        '"Authentication Error - Expired Key. Key Expired. code: expired_key"}}'
    )
    assert KeyExpiryRecovery.is_auth_failure(exc) is True


def test_auth_failure_detected_anywhere_in_exception_chain():
    inner = RuntimeError("code: invalid_api_key")
    outer = RuntimeError("Scolta AI API request failed")
    outer.__cause__ = inner
    assert KeyExpiryRecovery.is_auth_failure(outer) is True


def test_budget_exceeded_is_not_auth_failure():
    # Budget exhaustion belongs to BudgetAwareProviderDecorator and must
    # never trigger re-provisioning (a fresh trial key would reset the
    # spend ceiling — that is the upgrade flow's job).
    by_message = RuntimeError(BudgetAwareProviderDecorator.BUDGET_MESSAGE)
    by_type = AmazeeBudgetExceededException(RuntimeError("429"))

    assert KeyExpiryRecovery.is_auth_failure(by_message) is False
    assert KeyExpiryRecovery.is_auth_failure(by_type) is False


def test_generic_error_is_not_auth_failure():
    exc = RuntimeError("Scolta AI API request failed: network timeout")
    assert KeyExpiryRecovery.is_auth_failure(exc) is False


# -- handle_auth_failure() — detection, recovery, fresh credentials -------------


def test_expired_key_triggers_one_reprovision_and_stores_fresh_creds():
    trial_calls = []
    recovery, storage, _cache = _make_recovery(trial_calls)

    result = recovery.handle_auth_failure(RuntimeError("code: expired_key"))

    assert result is True
    assert recovery.credentials()["litellm_token"] == "sk-fresh-token"
    assert storage.load()["litellm_token"] == "sk-fresh-token"
    assert trial_calls == ["/auth/generate-trial-access"], "Re-provision attempted exactly once"
    assert recovery.is_auth_failing() is False, (
        "Successful recovery must clear the auth-failure marker"
    )


def test_second_failure_in_window_does_not_reprovision_again():
    trial_calls = []
    recovery, _storage, _cache = _make_recovery(trial_calls)

    assert recovery.handle_auth_failure(RuntimeError("code: expired_key")) is True

    # A second auth failure inside the window must not hit the API again.
    result = recovery.handle_auth_failure(RuntimeError("code: expired_key"))

    assert result is False
    assert trial_calls == ["/auth/generate-trial-access"], "No second provisioning call"


def test_failed_reprovision_leaves_auth_failure_marker_and_waits_out_window():
    trial_calls = []
    recovery, _storage, _cache = _make_recovery(trial_calls, trial_status=500)

    first = recovery.handle_auth_failure(RuntimeError("code: expired_key"))
    second = recovery.handle_auth_failure(RuntimeError("code: expired_key"))

    assert first is False, "Provisioning failure must report unrecovered"
    assert second is False, "Second failure must wait out the window, not retry the API"
    assert recovery.is_auth_failing() is True, "Health must keep seeing the failure"
    assert len(trial_calls) == 1, "Exactly one provisioning attempt"


def test_elapsed_window_allows_a_new_reprovision_attempt(monkeypatch):
    # Python adaptation: the bundled InMemoryCacheDriver does not enforce TTLs
    # (long-running process, no per-request platform cache), so the window is
    # checked against the marker's stored timestamp on read.
    from scolta.ai.amazee import key_expiry_recovery as mod

    now = {"t": 1000.0}
    monkeypatch.setattr(mod, "time", SimpleNamespace(time=lambda: now["t"]))

    trial_calls = []
    recovery, _storage, _cache = _make_recovery(trial_calls, trial_status=500)

    assert recovery.handle_auth_failure(RuntimeError("code: expired_key")) is False
    assert len(trial_calls) == 1

    now["t"] += 601  # past the 600s failure window

    assert recovery.handle_auth_failure(RuntimeError("code: expired_key")) is False
    assert len(trial_calls) == 2, "A new window must permit one more attempt"


def test_non_auth_failure_is_ignored():
    trial_calls = []
    recovery, storage, _cache = _make_recovery(trial_calls)

    result = recovery.handle_auth_failure(RuntimeError(BudgetAwareProviderDecorator.BUDGET_MESSAGE))

    assert result is False
    assert recovery.is_auth_failing() is False, "Budget errors must not mark auth as failing"
    assert storage.load()["litellm_token"] == "sk-expired-token", "Storage untouched"
    assert trial_calls == [], "No provisioning call for non-auth errors"


def test_models_resolved_callback_forwarded_on_recovery():
    trial_calls = []
    recovery, _storage, _cache = _make_recovery(trial_calls)

    resolved = {}
    recovery.handle_auth_failure(
        RuntimeError("code: expired_key"),
        on_models_resolved=lambda model, expansion: resolved.update(
            {"model": model, "expansion": expansion}
        ),
    )

    assert resolved == {"model": "claude-sonnet-4-5", "expansion": "claude-haiku-4-5"}


# -- markers --------------------------------------------------------------------


def test_record_auth_failure_is_visible_to_is_auth_failing():
    recovery, _storage, cache = _make_recovery([])

    assert recovery.is_auth_failing() is False

    recovery.record_auth_failure()

    assert recovery.is_auth_failing() is True
    assert cache.get(KeyExpiryRecovery.CACHE_KEY_AUTH_FAILURE) is not None


def test_stale_auth_failure_marker_ages_out(monkeypatch):
    # Python adaptation of the PHP cache-TTL expiry: the marker stores its
    # timestamp and is treated as expired AUTH_FAILURE_TTL seconds later even
    # when the cache backend never evicts it.
    from scolta.ai.amazee import key_expiry_recovery as mod

    now = {"t": 1000.0}
    monkeypatch.setattr(mod, "time", SimpleNamespace(time=lambda: now["t"]))

    recovery, _storage, _cache = _make_recovery([])
    recovery.record_auth_failure()
    assert recovery.is_auth_failing() is True

    now["t"] += KeyExpiryRecovery.AUTH_FAILURE_TTL + 1

    assert recovery.is_auth_failing() is False
