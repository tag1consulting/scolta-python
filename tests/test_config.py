"""Config behaviour tests.

These guard the from_dict/preset/coercion logic ported from
Config/ScoltaConfig.php (the PHP suite covers this behaviour across
ConfigReferenceDocTest and the adapter tests; the core semantics are pinned
here).
"""

from scolta.config import ScoltaConfig


def test_defaults():
    c = ScoltaConfig()
    assert c.ai_provider == "anthropic"
    assert c.indexer == "auto"
    assert c.expand_subword_max_frequency == 0.05
    assert c.expansion_combine_mode == "relevance_union"
    assert c.expansion_per_term_top_k == 3
    assert c.ai_languages == ["en"]


def test_preset_applied_before_explicit_values():
    c = ScoltaConfig.from_dict({"preset": "content_catalog"})
    assert c.preset == "content_catalog"
    assert c.recency_strategy == "none"
    assert c.title_all_terms_multiplier == 2.5
    assert c.expansion_combine_mode == "round_robin"
    assert c.results_per_page == 12


def test_explicit_value_overrides_preset():
    c = ScoltaConfig.from_dict({"preset": "content_catalog", "results_per_page": 99})
    assert c.results_per_page == 99
    # Non-overridden preset values still apply.
    assert c.expansion_combine_mode == "round_robin"


def test_none_value_falls_through_to_default():
    # Adapters emit every key; null means "use the preset/base default".
    c = ScoltaConfig.from_dict({"preset": "content_catalog", "results_per_page": None})
    assert c.results_per_page == 12  # preset value, not overridden by None


def test_expansion_per_term_top_k_locked():
    c = ScoltaConfig.from_dict({"expansion_per_term_top_k": 99})
    assert c.expansion_per_term_top_k == 3


def test_unknown_keys_ignored():
    c = ScoltaConfig.from_dict({"nonexistent_key": "x", "site_name": "Foo"})
    assert c.site_name == "Foo"
    assert not hasattr(c, "nonexistent_key")


def test_string_coercion_to_typed_fields():
    # CMS layers store everything as strings.
    c = ScoltaConfig.from_dict(
        {
            "results_per_page": "25",
            "title_match_boost": "3.5",
            "show_attribution": "1",
            "ai_summarize": "0",
        }
    )
    assert c.results_per_page == 25
    assert c.title_match_boost == 3.5
    assert c.show_attribution is True
    assert c.ai_summarize is False


def test_bool_coercion_matches_php_semantics():
    # PHP (bool): only "" and "0" are falsy; "false" casts to True.
    assert ScoltaConfig.from_dict({"show_attribution": "false"}).show_attribution is True
    assert ScoltaConfig.from_dict({"show_attribution": "0"}).show_attribution is False
    assert ScoltaConfig.from_dict({"show_attribution": ""}).show_attribution is False


def test_combine_mode_preset_resolution():
    expected = {
        "none": "relevance_union",
        "reference": "relevance_union",
        "content_catalog": "round_robin",
        "ecommerce": "round_robin",
        "blog": "round_robin",
    }
    for preset, mode in expected.items():
        assert ScoltaConfig.from_dict({"preset": preset}).expansion_combine_mode == mode


def test_get_presets_and_values():
    assert set(ScoltaConfig.get_presets().keys()) == {
        "none",
        "content_catalog",
        "reference",
        "ecommerce",
        "blog",
    }
    assert ScoltaConfig.get_preset_values("content_catalog")["results_per_page"] == 12
    assert ScoltaConfig.get_preset_values("unknown") == {}


def test_to_js_scoring_config_shape():
    js = ScoltaConfig().to_js_scoring_config()
    assert js["TITLE_MATCH_BOOST"] == 2.0
    assert js["EXPANSION_PER_TERM_TOP_K"] == 3
    assert js["LANGUAGE"] == "en"
    assert js["RECENCY_CURVE"] == []


def test_to_browser_config_endpoints_and_paths():
    c = ScoltaConfig.from_dict({"site_name": "My Site", "pagefind_index_path": "/pf"})
    b = c.to_browser_config()
    assert b["endpoints"]["expand"] == "/api/scolta/v1/expand-query"
    assert b["pagefindPath"] == "/pf/pagefind.js"
    assert b["siteName"] == "My Site"


def test_to_ai_client_config_omits_empty_base_url():
    c = ScoltaConfig()
    assert "base_url" not in c.to_ai_client_config()
    c2 = ScoltaConfig.from_dict({"ai_base_url": "https://x/v1"})
    assert c2.to_ai_client_config()["base_url"] == "https://x/v1"


def test_to_browser_config_endpoint_overrides():
    """Framework adapters can substitute the routes they actually registered
    (e.g. a custom route prefix) for the default /api/scolta/v1/... URLs."""
    c = ScoltaConfig()
    b = c.to_browser_config(
        endpoints={
            "expand": "/custom/expand-query",
            "summarize": "/custom/summarize",
        }
    )
    assert b["endpoints"]["expand"] == "/custom/expand-query"
    assert b["endpoints"]["summarize"] == "/custom/summarize"
    # Unspecified keys keep their defaults.
    assert b["endpoints"]["followup"] == "/api/scolta/v1/followup"


def test_hide_empty_facets_defaults_to_true():
    assert ScoltaConfig().hide_empty_facets is True


def test_hide_empty_facets_opt_out_maps_from_bool():
    assert ScoltaConfig.from_dict({"hide_empty_facets": False}).hide_empty_facets is False


def test_hide_empty_facets_string_coercion_matches_php():
    # PHP (bool): only "" and "0" are falsy; "false" casts to True.
    assert ScoltaConfig.from_dict({"hide_empty_facets": "0"}).hide_empty_facets is False
    assert ScoltaConfig.from_dict({"hide_empty_facets": ""}).hide_empty_facets is False
    assert ScoltaConfig.from_dict({"hide_empty_facets": "false"}).hide_empty_facets is True


def test_hide_empty_facets_stays_true_when_key_absent():
    assert ScoltaConfig.from_dict({"site_name": "x"}).hide_empty_facets is True


def test_to_browser_config_carries_hide_empty_facets_top_level():
    b = ScoltaConfig().to_browser_config()
    assert b["hideEmptyFacets"] is True
    # Top-level, not nested under scoring.
    assert "hideEmptyFacets" not in b["scoring"]


def test_to_browser_config_carries_hide_empty_facets_opt_out():
    b = ScoltaConfig.from_dict({"hide_empty_facets": False}).to_browser_config()
    assert b["hideEmptyFacets"] is False


def test_specificity_and_filter_hint_defaults_match_js_fallbacks():
    js = ScoltaConfig().to_js_scoring_config()
    assert js["SPECIFICITY_WEIGHTING"] is True
    assert js["SPECIFICITY_FLOOR"] == 0.15
    assert js["SPECIFICITY_STRONG_MATCH"] == 0.55
    assert js["SPECIFICITY_COOCCURRENCE"] == 0.9
    assert js["SPECIFICITY_AGREEMENT_GATE"] == 0.45
    assert js["SPECIFICITY_AGREEMENT_DECAY"] == 1.0
    assert js["FILTER_HINT_MIN_RESULTS"] == 5
    assert js["FILTER_HINT_MIN_RATIO"] == 0.1


def test_specificity_and_filter_hint_map_from_snake_case():
    js = ScoltaConfig.from_dict(
        {
            "specificity_weighting": False,
            "specificity_floor": 0.05,
            "specificity_strong_match": 0.7,
            "specificity_cooccurrence": 1.4,
            "specificity_agreement_gate": 0.3,
            "specificity_agreement_decay": 0.65,
            "filter_hint_min_results": 12,
            "filter_hint_min_ratio": 0.25,
        }
    ).to_js_scoring_config()
    assert js["SPECIFICITY_WEIGHTING"] is False
    assert js["SPECIFICITY_FLOOR"] == 0.05
    assert js["SPECIFICITY_STRONG_MATCH"] == 0.7
    assert js["SPECIFICITY_COOCCURRENCE"] == 1.4
    assert js["SPECIFICITY_AGREEMENT_GATE"] == 0.3
    assert js["SPECIFICITY_AGREEMENT_DECAY"] == 0.65
    assert js["FILTER_HINT_MIN_RESULTS"] == 12
    assert js["FILTER_HINT_MIN_RATIO"] == 0.25


def test_specificity_cooccurrence_zero_restores_maximum_only_merge():
    assert ScoltaConfig.from_dict({"specificity_cooccurrence": 0}).specificity_cooccurrence == 0


def test_specificity_and_filter_hint_coerce_from_strings():
    c = ScoltaConfig.from_dict(
        {
            "specificity_weighting": "0",
            "specificity_cooccurrence": "0.75",
            "specificity_agreement_gate": "0.5",
            "specificity_agreement_decay": "0.8",
            "filter_hint_min_results": "12",
            "filter_hint_min_ratio": "0.25",
        }
    )
    assert c.specificity_weighting is False
    assert c.specificity_cooccurrence == 0.75
    assert c.specificity_agreement_gate == 0.5
    assert c.specificity_agreement_decay == 0.8
    # int-annotated fields take an integer-shaped string, as elsewhere in _coerce.
    assert c.filter_hint_min_results == 12
    assert c.filter_hint_min_ratio == 0.25
