"""Ported from tests/Service/AiServiceAdapterTest.php (1:1)."""

import pytest

from scolta.ai import prompts
from scolta.ai.client import AiClient
from scolta.ai.service import AiServiceAdapter
from scolta.config import ScoltaConfig

# -- Custom overrides returned raw (no substitution) --------------------------

def test_custom_expand_prompt_returned_raw():
    cfg = ScoltaConfig.from_dict(
        {"site_name": "Acme Corp", "prompt_expand_query": "My custom expand prompt for {SITE_NAME}."}
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

@pytest.mark.parametrize("key,getter", [
    ("prompt_expand_query", "get_expand_prompt"),
    ("prompt_summarize", "get_summarize_prompt"),
    ("prompt_follow_up", "get_follow_up_prompt"),
])
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

    assert _Adapter(cfg).message_for_operation("expand_query", "sys", "user", 512) == "framework-response"


# -- aiExpansionModel config -------------------------------------------------

def test_ai_expansion_model_defaults_to_empty():
    assert ScoltaConfig().ai_expansion_model == ""


def test_ai_expansion_model_maps_from_dict():
    cfg = ScoltaConfig.from_dict({"ai_expansion_model": "claude-haiku-4-5-20251001"})
    assert cfg.ai_expansion_model == "claude-haiku-4-5-20251001"


def test_ai_expansion_model_not_included_in_ai_client_config():
    cfg = ScoltaConfig.from_dict(
        {"ai_model": "claude-sonnet-4-5-20250929", "ai_expansion_model": "claude-haiku-4-5-20251001"}
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
