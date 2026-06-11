"""Ported from tests/Service/AiServiceAdapterTest.php (1:1)."""

import httpx
import pytest

from scolta.ai import prompts
from scolta.ai.amazee import AmazeeClient, ConfigStorage, KeyExpiryRecovery
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

    def message(self, system_prompt, user_message, max_tokens=1024, model=None):
        raise self._to_throw

    def conversation(self, system_prompt, messages, max_tokens=1024, model=None):
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


# -- key-expiry recovery: expired Amazee trial key triggers a guarded ----------
# re-provision and exactly one retry with the fresh credentials.
#
# Regression (django demo, 2026-06-09): expired key -> every call 400
# expired_key -> expand silently echoed the query while ensure_ai_available
# no-opped on the stored dead credentials.

_FRESH_TRIAL_RESPONSE = {
    "key": {
        "litellm_token": "sk-fresh-token",
        "litellm_api_url": "https://llm.test.amazee.ai",
        "region": "test-region",
    }
}
_MODEL_INFO_RESPONSE = {
    "data": [{"model_name": "claude-sonnet-4-5"}, {"model_name": "claude-haiku-4-5"}]
}


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


class _RecoveredClient(AiClient):
    def __init__(self):
        super().__init__({})

    def message(self, system_prompt, user_message, max_tokens=1024, model=None):
        return "recovered response"

    def conversation(self, system_prompt, messages, max_tokens=1024, model=None):
        return "recovered response"


def _make_recovering_adapter(to_throw, provision_ok=True):
    """Adapter whose first client throws ``to_throw``, with recovery wired
    against a mocked Amazee provisioning API. The recovered client returns
    'recovered response' and records the credentials it was built from.
    Returns (adapter, storage, trial_calls)."""
    cfg = ScoltaConfig.from_dict({})

    class _Adapter(AiServiceAdapter):
        def __init__(self, config, stub):
            super().__init__(config)
            self._stub = stub
            self.recovered_with = None

        def _create_client(self):
            return self._stub

        def _create_recovered_client(self, credentials):
            self.recovered_with = credentials
            return _RecoveredClient()

    adapter = _Adapter(cfg, _ThrowingClient(to_throw))

    storage = _MemoryAmazeeStorage(
        {
            "litellm_token": "sk-expired-token",
            "litellm_api_url": "https://llm.test.amazee.ai",
            "region": "test-region",
        }
    )

    trial_calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/auth/generate-trial-access":
            trial_calls.append(request.url.path)
            if not provision_ok:
                return httpx.Response(500, json={"detail": "server error"})
            return httpx.Response(200, json=_FRESH_TRIAL_RESPONSE)
        if request.url.path == "/model/info":
            return httpx.Response(200, json=_MODEL_INFO_RESPONSE)
        return httpx.Response(404, json={})

    amazee_client = AmazeeClient(http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    adapter.set_key_expiry_recovery(
        KeyExpiryRecovery(storage=storage, cache=InMemoryCacheDriver(), client=amazee_client)
    )

    return adapter, storage, trial_calls


def test_expired_key_reprovisions_once_and_retries_with_fresh_creds():
    adapter, storage, trial_calls = _make_recovering_adapter(
        RuntimeError("Scolta AI API request failed: 400 code: expired_key")
    )

    result = adapter.message("sys", "user")

    assert result == "recovered response"
    assert adapter.recovered_with["litellm_token"] == "sk-fresh-token", (
        "Retry client must be built from the freshly provisioned credentials"
    )
    assert storage.load()["litellm_token"] == "sk-fresh-token", (
        "Fresh credentials must be stored for subsequent requests"
    )
    assert len(trial_calls) == 1, "Re-provision attempted exactly once"


def test_expired_key_recovery_works_on_conversation_path():
    adapter, _storage, _trial_calls = _make_recovering_adapter(
        RuntimeError("Scolta AI API request failed: 401 invalid_api_key")
    )

    result = adapter.conversation("sys", [{"role": "user", "content": "hi"}])

    assert result == "recovered response"


def test_expired_key_recovery_works_on_message_for_operation_path():
    adapter, _storage, _trial_calls = _make_recovering_adapter(
        RuntimeError("Scolta AI API request failed: 400 code: expired_key")
    )

    result = adapter.message_for_operation("expand_query", "sys", "user")

    assert result == "recovered response"


def test_budget_exceeded_does_not_trigger_reprovision():
    # Budget exhaustion must route to the budget path, not re-provisioning:
    # a fresh trial key would reset the spend ceiling, which is the upgrade
    # flow's job. The trial-call recorder proves provisioning is never hit.
    adapter, storage, trial_calls = _make_recovering_adapter(
        RuntimeError("Budget has been exceeded!")
    )

    with pytest.raises(RuntimeError, match="^Budget has been exceeded!$"):
        adapter.message("sys", "user")

    assert trial_calls == [], "No provisioning call for a budget error"
    assert storage.load()["litellm_token"] == "sk-expired-token", (
        "Storage untouched by a budget error"
    )


def test_failed_reprovision_propagates_original_auth_failure():
    adapter, storage, trial_calls = _make_recovering_adapter(
        RuntimeError("Scolta AI API request failed: 400 code: expired_key"),
        provision_ok=False,
    )

    with pytest.raises(RuntimeError, match="expired_key"):
        adapter.message("sys", "user")

    assert len(trial_calls) == 1, "One guarded attempt, then the failure propagates"
    assert storage.load() is None, "Known-bad credentials are cleared by the attempt"


def test_auth_failure_without_recovery_wired_still_propagates():
    adapter = _make_throwing_adapter(RuntimeError("400 code: expired_key"))

    with pytest.raises(RuntimeError, match="expired_key"):
        adapter.message("sys", "user")
