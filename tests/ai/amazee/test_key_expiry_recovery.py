"""Ported from tests/AiProvider/Amazee/KeyExpiryRecoveryTest.php (1:1 intent).

Regression (django demo, 2026-06-09): Amazee credentials were revoked
server-side, every LiteLLM call returned 400 expired_key, and nothing detected
it — expand silently echoed the query for ~24h while ensure_ai_available() kept
no-opping on the stored dead credentials. When the stored credentials stop being
accepted, AI must turn off and the site must be flagged for an admin to
re-authenticate; the stored credentials are left in place and no replacement
credentials are requested on this path.
"""

from types import SimpleNamespace

from scolta.ai.amazee import (
    AmazeeBudgetExceededException,
    BudgetAwareProviderDecorator,
    ConfigStorage,
    KeyExpiryRecovery,
)
from scolta.cache import InMemoryCacheDriver
from scolta.exceptions import ApiKeyInvalidException

STORED_CREDS = {
    "litellm_token": "sk-stored-token",
    "litellm_api_url": "https://llm.test.amazee.ai",
    "region": "test-region",
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


class TripwireStorage(ConfigStorage):
    """Credential store that records whether its mutators were invoked, so a
    test can assert the stored credentials were left untouched."""

    def __init__(self, stored=None):
        self._data = stored
        self.was_cleared = False
        self.was_stored = False

    def store(self, litellm_token, litellm_api_url, region):
        self.was_stored = True
        self._data = {
            "litellm_token": litellm_token,
            "litellm_api_url": litellm_api_url,
            "region": region,
        }

    def load(self):
        return self._data

    def clear(self):
        self.was_cleared = True
        self._data = None


def _make_recovery():
    storage = MemoryStorage(dict(STORED_CREDS))
    cache = InMemoryCacheDriver()
    recovery = KeyExpiryRecovery(storage=storage, cache=cache)
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
    # Budget exhaustion belongs to BudgetAwareProviderDecorator and follows the
    # budget path, never this credential-handling path.
    by_message = RuntimeError(BudgetAwareProviderDecorator.BUDGET_MESSAGE)
    by_type = AmazeeBudgetExceededException(RuntimeError("429"))

    assert KeyExpiryRecovery.is_auth_failure(by_message) is False
    assert KeyExpiryRecovery.is_auth_failure(by_type) is False


def test_generic_error_is_not_auth_failure():
    exc = RuntimeError("Scolta AI API request failed: network timeout")
    assert KeyExpiryRecovery.is_auth_failure(exc) is False


# -- handle_auth_failure() — degrade, record health, flag for re-auth ----------


def test_expired_credentials_degrade_and_flag_for_upgrade():
    recovery, storage, _cache = _make_recovery()

    result = recovery.handle_auth_failure(RuntimeError("code: expired_key"))

    assert result is False, "There is nothing to retry; the caller must degrade gracefully"
    assert storage.load()["litellm_token"] == "sk-stored-token", (
        "Stored credentials must be left intact"
    )
    assert recovery.is_auth_failing() is True, "Health must report AI as degraded"
    assert recovery.is_upgrade_needed() is True, (
        "The site must be flagged for admin re-authentication"
    )


def test_stored_credentials_are_never_discarded_on_auth_failure():
    # The credential store must not be touched: leaving it in place is what
    # keeps the failure path from requesting any replacement credentials.
    storage = TripwireStorage(dict(STORED_CREDS))
    recovery = KeyExpiryRecovery(storage=storage, cache=InMemoryCacheDriver())

    recovery.handle_auth_failure(RuntimeError("code: expired_key"))

    assert storage.was_cleared is False, "clear() must never be called on an auth failure"
    assert storage.was_stored is False, "store() must never be called on an auth failure"


def test_repeated_failures_keep_flags_set_without_touching_storage():
    storage = TripwireStorage(dict(STORED_CREDS))
    recovery = KeyExpiryRecovery(storage=storage, cache=InMemoryCacheDriver())

    assert recovery.handle_auth_failure(RuntimeError("code: expired_key")) is False
    assert recovery.handle_auth_failure(RuntimeError("code: expired_key")) is False

    assert recovery.is_auth_failing() is True
    assert recovery.is_upgrade_needed() is True
    assert storage.was_cleared is False
    assert storage.was_stored is False


def test_non_auth_failure_is_ignored():
    recovery, storage, _cache = _make_recovery()

    result = recovery.handle_auth_failure(RuntimeError(BudgetAwareProviderDecorator.BUDGET_MESSAGE))

    assert result is False
    assert recovery.is_auth_failing() is False, "Budget errors must not mark auth as failing"
    assert recovery.is_upgrade_needed() is False, (
        "Budget errors must not flag for re-authentication"
    )
    assert storage.load()["litellm_token"] == "sk-stored-token", "Storage untouched"


# -- markers --------------------------------------------------------------------


def test_record_auth_failure_is_visible_to_is_auth_failing():
    recovery, _storage, cache = _make_recovery()

    assert recovery.is_auth_failing() is False

    recovery.record_auth_failure()

    assert recovery.is_auth_failing() is True
    assert cache.get(KeyExpiryRecovery.CACHE_KEY_AUTH_FAILURE) is not None


def test_upgrade_needed_marker_can_be_set_and_cleared():
    recovery, _storage, _cache = _make_recovery()

    assert recovery.is_upgrade_needed() is False

    recovery.flag_upgrade_needed()
    assert recovery.is_upgrade_needed() is True

    recovery.clear_upgrade_needed()
    assert recovery.is_upgrade_needed() is False, (
        "A completed re-authentication must clear the prompt"
    )


def test_stale_auth_failure_marker_ages_out(monkeypatch):
    # Python adaptation of the PHP cache-TTL expiry: the marker stores its
    # timestamp and is treated as expired AUTH_FAILURE_TTL seconds later even
    # when the cache backend never evicts it.
    from scolta.ai.amazee import key_expiry_recovery as mod

    now = {"t": 1000.0}
    monkeypatch.setattr(mod, "time", SimpleNamespace(time=lambda: now["t"]))

    recovery, _storage, _cache = _make_recovery()
    recovery.record_auth_failure()
    assert recovery.is_auth_failing() is True

    now["t"] += KeyExpiryRecovery.AUTH_FAILURE_TTL + 1

    assert recovery.is_auth_failing() is False


def test_upgrade_needed_marker_persists_far_past_the_auth_failure_window(monkeypatch):
    # The upgrade-needed marker is deliberately long-lived: it outlasts the
    # auth-failure window so the re-authentication prompt does not disappear on
    # its own before the admin acts. It clears only on an explicit clear.
    from scolta.ai.amazee import key_expiry_recovery as mod

    now = {"t": 1000.0}
    monkeypatch.setattr(mod, "time", SimpleNamespace(time=lambda: now["t"]))

    recovery, _storage, _cache = _make_recovery()
    recovery.flag_upgrade_needed()
    assert recovery.is_upgrade_needed() is True

    now["t"] += KeyExpiryRecovery.AUTH_FAILURE_TTL * 24  # a day later
    assert recovery.is_upgrade_needed() is True
