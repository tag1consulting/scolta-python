"""Parity Gate #1 — HTML cleaning + Pagefind-document building.

Asserts the Python html.py reproduces, byte-for-byte, the output of the real
PHP HtmlCleaner / PagefindHtmlBuilder. The golden file
(tests/fixtures/html_parity.json) was generated from scolta-php's actual
classes via a PHP harness, then committed so this runs PHP-free in CI.

Covers the 20 recipe fixtures (the Phase 3 gate corpus), plus edge-case units
(malformed HTML, nbsp, entities, nested main-content, <-space-literal, leading
title strip, region-footer, diacritics) and 14 builder cases.
"""

import json
from pathlib import Path

import pytest

from scolta import html as htmlmod

_FIXTURES = Path(__file__).parent / "fixtures"
_GOLDEN = json.loads((_FIXTURES / "html_parity.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", sorted(_GOLDEN["cleaner_fixtures"].keys()))
def test_cleaner_recipe_fixture_parity(name):
    raw = (_FIXTURES / "recipes" / name).read_text(encoding="utf-8")
    case = _GOLDEN["cleaner_fixtures"][name]
    assert htmlmod.clean(raw) == case["clean_no_title"]
    assert htmlmod.clean(raw, case["title"]) == case["clean_with_title"]


@pytest.mark.parametrize("key", sorted(_GOLDEN["cleaner_units"].keys()))
def test_cleaner_unit_parity(key):
    case = _GOLDEN["cleaner_units"][key]
    assert htmlmod.clean(case["input"], case["title"]) == case["expected"]


@pytest.mark.parametrize("i", range(len(_GOLDEN["builder_cases"])))
def test_builder_parity(i):
    case = _GOLDEN["builder_cases"][i]
    p = case["params"]
    result = htmlmod.build(
        p["id"],
        p["title"],
        p["body"],
        p["url"],
        p["date"],
        p["siteName"],
        p["language"],
        p["filters"],
        p["metadata"],
        p["sortable"],
    )
    assert result == case["expected"]
