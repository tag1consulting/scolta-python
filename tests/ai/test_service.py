"""Ported from tests/Service/AiServiceAdapterTest.php (1:1)."""

import pytest

from scolta.ai import prompts
from scolta.ai.amazee import ConfigStorage, KeyExpiryRecovery
from scolta.ai.client import AiClient
from scolta.ai.service import AiServiceAdapter
from scolta.cache import InMemoryCacheDriver
from scolta.config import ScoltaConfig

# -- Custom overrides returned raw (no substitution) --------------------------


def test_custom_expand_prompt_returned_raw():
    cfg = ScoltaConfig.from_dict(
        {
            "site_name": "Acme Corp",
            "prompt_expand_query": "My custom expand prompt for {SITE_NAME}.",
        }
    )
    prompt = AiServiceAdapter(cfg).get_expand_prompt()
    assert prompt == "My custom expand prompt for {SITE_NAME}."
    assert "Acme Corp" not in prompt


def test_custom_summarize_prompt_returned_raw():
    cfg = ScoltaConfig.from_dict(
        {"site_name": "Acme Corp", "prompt_summarize": "Custom summarize for {SITE_NAME}."}
    )
    prompt = AiServiceAdapter(cfg).get_summarize_prompt()
    assert prompt == "Custom summarize for {SITE_NAME}."
    assert "Acme Corp" not in prompt


def test_custom_follow_up_prompt_returned_raw():
    cfg = ScoltaConfig.from_dict(
        {"site_name": "Acme Corp", "prompt_follow_up": "Custom follow-up for {SITE_NAME}."}
    )
    prompt = AiServiceAdapter(cfg).get_follow_up_prompt()
    assert prompt == "Custom follow-up for {SITE_NAME}."
    assert "Acme Corp" not in prompt


# -- Defaults: placeholders substituted ---------------------------------------


def test_default_expand_prompt_contains_site_name():
    cfg = ScoltaConfig.from_dict({"site_name": "Acme Corp", "site_description": "technology blog"})
    prompt = AiServiceAdapter(cfg).get_expand_prompt()
    assert "Acme Corp" in prompt
    assert "{SITE_NAME}" not in prompt
    assert "{SITE_DESCRIPTION}" not in prompt


def test_default_summarize_prompt_contains_site_name():
    cfg = ScoltaConfig.from_dict({"site_name": "Example Site", "site_description": "news website"})
    prompt = AiServiceAdapter(cfg).get_summarize_prompt()
    assert "Example Site" in prompt
    assert "news website" in prompt
    assert "{SITE_NAME}" not in prompt
    assert "{SITE_DESCRIPTION}" not in prompt


def test_default_follow_up_prompt_contains_site_name():
    cfg = ScoltaConfig.from_dict({"site_name": "Widget World"})
    prompt = AiServiceAdapter(cfg).get_follow_up_prompt()
    assert "Widget World" in prompt
    assert "{SITE_NAME}" not in prompt


# -- Empty override falls back to default with substitution --------------------


@pytest.mark.parametrize(
    "key,getter",
    [
        ("prompt_expand_query", "get_expand_prompt"),
        ("prompt_summarize", "get_summarize_prompt"),
        ("prompt_follow_up", "get_follow_up_prompt"),
    ],
)
def test_empty_override_falls_back_to_default(key, getter):
    cfg = ScoltaConfig.from_dict({"site_name": "Test Site", key: ""})
    prompt = getattr(AiServiceAdapter(cfg), getter)()
    assert "Test Site" in prompt
    assert "{SITE_NAME}" not in prompt


# -- resolvePrompt -------------------------------------------------------------


def test_resolve_prompt_substitutes_placeholders():
    cfg = ScoltaConfig.from_dict({"site_name": "My Blog", "site_description": "a personal blog"})
    resolved = AiServiceAdapter(cfg).resolve_prompt(prompts.EXPAND_QUERY)
    assert "My Blog" in resolved
    assert "a personal blog" in resolved
    assert "{SITE_NAME}" not in resolved
    assert "{SITE_DESCRIPTION}" not in resolved


# -- messageForOperation: framework path precedence ---------------------------


def test_message_for_operation_uses_framework_path_when_available():
    cfg = ScoltaConfig.from_dict({"ai_expansion_model": "claude-haiku-4-5-20251001"})

    class _Adapter(AiServiceAdapter):
        def _try_framework_ai(self, system_prompt, user_message, max_tokens):
            return "framework-response"

    assert (
        _Adapter(cfg).message_for_operation("expand_query", "sys", "user", 512)
        == "framework-response"
    )


# -- messageForOperation: temperature pinning ---------------------------------


class _RecordingClient(AiClient):
    """Records the model and temperature passed to each message() call."""

    def __init__(self):
        super().__init__({})
        self.calls: list[dict] = []

    def message(self, system_prompt, user_message, max_tokens=1024, model=None, temperature=None):
        self.calls.append({"model": model, "temperature": temperature})
        return "recorded"


def _make_recording_adapter(cfg):
    class _Adapter(AiServiceAdapter):
        def __init__(self, config, stub):
            super().__init__(config)
            self.recording_client = stub

        def _get_client(self):
            return self.recording_client

    return _Adapter(cfg, _RecordingClient())


def test_expand_query_reaches_client_with_temperature_zero():
    # Expansion is a deterministic semantic mapping — it must run at
    # temperature 0 so the same query yields the same terms every call.
    adapter = _make_recording_adapter(ScoltaConfig.from_dict({}))

    result = adapter.message_for_operation("expand_query", "sys", "user", 512)

    assert result == "recorded"
    assert adapter.recording_client.calls[0]["temperature"] == 0


def test_non_expansion_operation_reaches_client_with_null_temperature():
    # Summarize (and follow-up) are creative surfaces — they keep the provider
    # default, i.e. no temperature is sent (None).
    adapter = _make_recording_adapter(ScoltaConfig.from_dict({}))

    adapter.message_for_operation("summarize", "sys", "user", 512)

    assert adapter.recording_client.calls[0]["temperature"] is None


# -- aiExpansionModel config -------------------------------------------------


def test_ai_expansion_model_defaults_to_empty():
    assert ScoltaConfig().ai_expansion_model == ""


def test_ai_expansion_model_maps_from_dict():
    cfg = ScoltaConfig.from_dict({"ai_expansion_model": "claude-haiku-4-5-20251001"})
    assert cfg.ai_expansion_model == "claude-haiku-4-5-20251001"


def test_ai_expansion_model_not_included_in_ai_client_config():
    cfg = ScoltaConfig.from_dict(
        {
            "ai_model": "claude-sonnet-4-5-20250929",
            "ai_expansion_model": "claude-haiku-4-5-20251001",
        }
    )
    client_config = cfg.to_ai_client_config()
    assert client_config["model"] == "claude-sonnet-4-5-20250929"
    assert "expansion_model" not in client_config
    assert "ai_expansion_model" not in client_config


# -- handlePossibleBudgetException hook ----------------------------------------


class _ThrowingClient(AiClient):
    def __init__(self, to_throw):
        self._to_throw = to_throw
        super().__init__({})

    def message(self, system_prompt, user_message, max_tokens=1024, model=None, temperature=None):
        raise self._to_throw

    def conversation(self, system_prompt, messages, max_tokens=1024, model=None, temperature=None):
        raise self._to_throw


def _make_throwing_adapter(to_throw):
    cfg = ScoltaConfig.from_dict({"ai_expansion_model": "claude-haiku-4-5-20251001"})

    class _Adapter(AiServiceAdapter):
        def __init__(self, config, stub):
            super().__init__(config)
            self._stub = stub
            self.hook_calls = 0
            self.hook_arg = None

        def _get_client(self):
            return self._stub

        def _handle_possible_budget_exception(self, exc):
            self.hook_calls += 1
            self.hook_arg = exc

    return _Adapter(cfg, _ThrowingClient(to_throw))


def test_message_invokes_budget_hook_on_client_exception():
    original = RuntimeError("Budget has been exceeded!")
    adapter = _make_throwing_adapter(original)
    with pytest.raises(RuntimeError) as ei:
        adapter.message("sys", "user")
    assert ei.value is original
    assert adapter.hook_calls == 1
    assert adapter.hook_arg is original


def test_conversation_invokes_budget_hook_on_client_exception():
    original = RuntimeError("Budget has been exceeded!")
    adapter = _make_throwing_adapter(original)
    with pytest.raises(RuntimeError) as ei:
        adapter.conversation("sys", [{"role": "user", "content": "hi"}])
    assert ei.value is original
    assert adapter.hook_calls == 1
    assert adapter.hook_arg is original


def test_message_for_operation_invokes_budget_hook_on_client_exception():
    original = RuntimeError("Budget has been exceeded!")
    adapter = _make_throwing_adapter(original)
    with pytest.raises(RuntimeError) as ei:
        adapter.message_for_operation("expand_query", "sys", "user")
    assert ei.value is original
    assert adapter.hook_calls == 1
    assert adapter.hook_arg is original


def test_default_hook_is_no_op_and_exception_propagates():
    original = RuntimeError("some unrelated client failure")

    class _Adapter(AiServiceAdapter):
        def __init__(self, config, stub):
            super().__init__(config)
            self._stub = stub

        def _get_client(self):
            return self._stub

    adapter = _Adapter(ScoltaConfig.from_dict({}), _ThrowingClient(original))
    with pytest.raises(RuntimeError, match="some unrelated client failure"):
        adapter.message("sys", "user")


def test_hook_may_replace_the_exception():
    original = RuntimeError("Budget has been exceeded!")

    class _Adapter(AiServiceAdapter):
        def __init__(self, config, stub):
            super().__init__(config)
            self._stub = stub

        def _get_client(self):
            return self._stub

        def _handle_possible_budget_exception(self, exc):
            raise ValueError("converted: " + str(exc))

    adapter = _Adapter(ScoltaConfig.from_dict({}), _ThrowingClient(original))
    with pytest.raises(ValueError, match="converted: Budget has been exceeded!"):
        adapter.message("sys", "user")


# -- key-expiry recovery: an auth-class failure of the stored Amazee credentials
# degrades the call gracefully, records the failure for health, and flags the
# site for admin re-authentication. The stored credentials are left intact and
# no replacement credentials are requested on this path.
#
# Regression (django demo, 2026-06-09): expired key -> every call 400
# expired_key -> expand silently echoed the query while ensure_ai_available
# no-opped on the stored dead credentials.


class _MemoryAmazeeStorage(ConfigStorage):
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


def _make_recovering_adapter(to_throw):
    """Adapter whose client always throws ``to_throw``, with recovery wired
    against a credential store seeded with stored credentials. Returns
    (adapter, storage, recovery)."""
    cfg = ScoltaConfig.from_dict({})

    class _Adapter(AiServiceAdapter):
        def __init__(self, config, stub):
            super().__init__(config)
            self._stub = stub

        def _create_client(self):
            return self._stub

    adapter = _Adapter(cfg, _ThrowingClient(to_throw))

    storage = _MemoryAmazeeStorage(
        {
            "litellm_token": "sk-stored-token",
            "litellm_api_url": "https://llm.test.amazee.ai",
            "region": "test-region",
        }
    )

    recovery = KeyExpiryRecovery(storage=storage, cache=InMemoryCacheDriver())
    adapter.set_key_expiry_recovery(recovery)

    return adapter, storage, recovery


def test_expired_credentials_degrade_and_flag_for_upgrade():
    adapter, storage, recovery = _make_recovering_adapter(
        RuntimeError("Scolta AI API request failed: 400 code: expired_key")
    )

    with pytest.raises(RuntimeError, match="expired_key"):
        adapter.message("sys", "user")

    assert storage.load()["litellm_token"] == "sk-stored-token", (
        "Stored credentials must be left intact"
    )
    assert recovery.is_auth_failing() is True, "Health must report AI as degraded"
    assert recovery.is_upgrade_needed() is True, (
        "The site must be flagged for admin re-authentication"
    )


def test_expired_credentials_degrade_on_conversation_path():
    adapter, _storage, recovery = _make_recovering_adapter(
        RuntimeError("Scolta AI API request failed: 401 invalid_api_key")
    )

    with pytest.raises(RuntimeError, match="invalid_api_key"):
        adapter.conversation("sys", [{"role": "user", "content": "hi"}])

    assert recovery.is_auth_failing() is True
    assert recovery.is_upgrade_needed() is True


def test_expired_credentials_degrade_on_message_for_operation_path():
    adapter, _storage, recovery = _make_recovering_adapter(
        RuntimeError("Scolta AI API request failed: 400 code: expired_key")
    )

    with pytest.raises(RuntimeError, match="expired_key"):
        adapter.message_for_operation("expand_query", "sys", "user")

    assert recovery.is_auth_failing() is True
    assert recovery.is_upgrade_needed() is True


def test_budget_exceeded_is_not_treated_as_credential_failure():
    # Budget exhaustion must route to the budget path: it must never flag the
    # credentials as failing or mark the site for re-authentication.
    adapter, storage, recovery = _make_recovering_adapter(RuntimeError("Budget has been exceeded!"))

    with pytest.raises(RuntimeError, match=r"^Budget has been exceeded!$"):
        adapter.message("sys", "user")

    assert storage.load()["litellm_token"] == "sk-stored-token", (
        "Storage untouched by a budget error"
    )
    assert recovery.is_auth_failing() is False, (
        "A budget error must not mark credentials as failing"
    )
    assert recovery.is_upgrade_needed() is False, (
        "A budget error must not flag for re-authentication"
    )


def test_auth_failure_without_recovery_wired_still_propagates():
    adapter = _make_throwing_adapter(RuntimeError("400 code: expired_key"))

    with pytest.raises(RuntimeError, match="expired_key"):
        adapter.message("sys", "user")
