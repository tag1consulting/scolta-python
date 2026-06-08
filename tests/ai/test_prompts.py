"""Tests for prompt template resolution (DefaultPrompts port)."""

import pytest

from scolta.ai import prompts


def test_resolve_substitutes_placeholders():
    r = prompts.resolve(prompts.EXPAND_QUERY, "Acme", "tech blog")
    assert "Acme" in r
    assert "tech blog" in r
    assert "{SITE_NAME}" not in r
    assert "{SITE_DESCRIPTION}" not in r


def test_resolve_default_site_description():
    r = prompts.resolve(prompts.FOLLOW_UP, "Acme")
    assert "Acme" in r
    assert "{SITE_DESCRIPTION}" not in r  # follow_up has no description placeholder but stays clean


def test_resolve_custom_template_passthrough():
    # An unknown template string is treated as a custom prompt and substituted.
    r = prompts.resolve("Hello {SITE_NAME}", "Acme")
    assert r == "Hello Acme"


def test_get_template_returns_raw_with_placeholders():
    t = prompts.get_template(prompts.SUMMARIZE)
    assert "{SITE_NAME}" in t


def test_get_template_unknown_raises():
    with pytest.raises(ValueError, match="Unknown prompt template"):
        prompts.get_template("nope")


def test_template_constants():
    assert prompts.EXPAND_QUERY == "expand_query"
    assert prompts.SUMMARIZE == "summarize"
    assert prompts.FOLLOW_UP == "follow_up"


def test_expand_query_forbids_fabricating_unverified_entities():
    template = prompts.get_template(prompts.EXPAND_QUERY)
    assert "UNRECOGNIZED OR UNVERIFIABLE NAMED ENTITIES" in template
    assert "do NOT manufacture" in template
