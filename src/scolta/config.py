"""Platform-agnostic Scolta configuration.

Port of ``Tag1\\Scolta\\Config\\ScoltaConfig``. Platform adapters map their
native config systems into this object. The JS frontend reads scoring
parameters from the same structure via ``window.scolta.scoring``.

Scoring defaults preserve the original algorithm exactly. PHP property names
are camelCase; here they are snake_case (the PHP ``fromArray`` already accepts
snake_case keys, so the wire contract is unchanged).
"""

from __future__ import annotations

import logging
import typing
from dataclasses import dataclass, field, fields

_LOGGER = logging.getLogger("scolta.config")


@dataclass
class ScoltaConfig:
    # -- AI provider --
    ai_provider: str = "anthropic"
    ai_api_key: str = ""
    ai_model: str = "claude-sonnet-4-5-20250929"
    ai_expansion_model: str = ""
    ai_base_url: str = ""

    # -- Site identity --
    site_name: str = ""
    site_description: str = "website"
    search_page_path: str = "/search"
    pagefind_index_path: str = "/pagefind"

    # -- Caching --
    cache_ttl: int = 2592000  # 30 days in seconds

    # -- Rate limiting --
    max_follow_ups: int = 3

    # -- Scoring: Recency --
    recency_boost_max: float = 0.25
    recency_half_life_days: int = 365
    recency_penalty_after_days: int = 1825
    recency_max_penalty: float = 0.3

    # -- Scoring: Title/Content match --
    title_match_boost: float = 2.0
    title_all_terms_multiplier: float = 1.5
    exact_title_match_boost: float = 5.0
    content_match_boost: float = 0.4

    # -- Scoring: Phrase proximity --
    phrase_adjacent_multiplier: float = 2.5
    phrase_near_multiplier: float = 1.5
    phrase_near_window: int = 5
    phrase_window: int = 15

    # -- Scoring: Expanded terms --
    expand_primary_weight: float = 0.5
    cross_list_bonus: float = 0.05

    # Max corpus frequency for a multi-word expansion term's constituent words
    # to be added as standalone search terms (issue #156). 0 disables; >=1.0
    # admits every sub-word.
    expand_subword_max_frequency: float = 0.05

    # Guard-only veto list for sub-word query-term exemption (#156 follow-up).
    expand_subword_deny_list: list[str] = field(default_factory=list)

    # How per-sub-query result sets are combined for the AI summarizer (#170):
    # 'relevance_union' (default) or 'round_robin'.
    expansion_combine_mode: str = "relevance_union"

    # Results taken from each expansion sub-query per round under round_robin.
    # Locked at 3 — internal constant, never settable from config.
    expansion_per_term_top_k: int = 3

    # -- Scoring: Specificity weighting and co-occurrence agreement --
    specificity_weighting: bool = True
    specificity_floor: float = 0.15
    specificity_strong_match: float = 0.55
    specificity_cooccurrence: float = 0.9
    specificity_agreement_gate: float = 0.45
    specificity_agreement_decay: float = 1.0

    # -- Scoring: Filter-hint recall guard --
    filter_hint_min_results: int = 5
    filter_hint_min_ratio: float = 0.1

    # -- Scoring: Language and stop words --
    language: str = "en"
    custom_stop_words: list[str] = field(default_factory=list)

    # -- Scoring: Recency strategy --
    recency_strategy: str = "exponential"  # exponential|linear|step|none|custom
    recency_curve: list = field(default_factory=list)

    # -- Display --
    excerpt_length: int = 300
    results_per_page: int = 10
    max_pagefind_results: int = 50
    show_attribution: bool = False

    # -- AI feature toggles --
    ai_expand_query: bool = True
    ai_summarize: bool = True
    ai_summary_top_n: int = 10
    ai_summary_max_chars: int = 4000
    ai_summary_max_tokens: int = 1024

    # -- Multilingual --
    ai_languages: list[str] = field(default_factory=lambda: ["en"])
    auto_language_filter: bool = False

    # -- Prompt overrides (empty = use DefaultPrompts) --
    prompt_expand_query: str = ""
    prompt_summarize: str = ""
    prompt_follow_up: str = ""

    # -- Indexer: 'auto' (python indexer) | 'python' | 'binary' --
    indexer: str = "auto"

    # -- Content --
    sortable_fields: list[str] = field(default_factory=list)
    sortable_field_descriptions: dict[str, str] = field(default_factory=dict)
    filter_fields: list[str] = field(default_factory=list)
    filter_field_descriptions: dict[str, str] = field(default_factory=dict)
    hide_empty_facets: bool = True

    # -- Search as you type (SAYT) --
    # Ten top-level browser settings, not scoring keys: to_js_scoring_config()
    # stays at exactly 40, and each of these is emitted top-level by
    # to_browser_config() and read by scolta.js as ``instanceConfig.<camelCase>``
    # (the hideEmptyFacets pattern). Every default is byte-equal to the fallback
    # the browser bundle uses when the key is absent. Full behaviour, including
    # the events and the theming custom properties: scolta-php docs/SAYT.md.
    sayt_enabled: bool = True
    sayt_min_chars: int = 2
    sayt_debounce_ms: int = 150
    sayt_max_suggestions: int = 6
    sayt_recent_searches: bool = True
    sayt_max_recent: int = 3
    sayt_expand: bool = True
    # Client-side sliding-window cap on SAYT expansion calls per minute. SAYT
    # expansions share the platform's AI flood budget with committed searches,
    # so an unbudgeted suggest path would spend a visitor's whole allowance on
    # prefixes and starve the search they actually ran.
    sayt_expand_per_minute: int = 6
    sayt_expansion_delay_ms: int = 500
    sayt_suggestion_action: str = "navigate"

    # -- Scoring preset --
    preset: str = ""

    # Accepted values for sayt_suggestion_action.
    SAYT_SUGGESTION_ACTIONS: typing.ClassVar[tuple[str, ...]] = ("navigate", "search")

    # Named scoring presets with labels and descriptions for adapter UIs.
    # Applied by from_dict() before explicit values so site overrides win.
    PRESETS: typing.ClassVar[dict] = {
        "none": {
            "label": "Start from Scratch",
            "description": "No preset applied. All scoring parameters use Scolta defaults, except sub-word expansion is slightly broadened (10%) since an uncategorized corpus benefits from wider recall. This is your starting point for fully custom configuration — select this as your starting point — or leave it as-is. You can optionally adjust any individual setting below.",
            "values": {
                "expand_subword_max_frequency": 0.10,
                "expansion_combine_mode": "relevance_union",
            },
        },
        "content_catalog": {
            "label": "Recipe & Content Catalog",
            "description": 'Best for recipe sites, wikis, and content collections with structured titles. Strongly prioritizes title matches — a recipe called "Chocolate Brownies" ranks high for that search — and shows more results per page for browsing. Newer and older content rank equally since catalog items stay relevant over time. Select this as your starting point — or leave it as-is. You can optionally adjust any individual setting below.',
            "values": {
                "recency_strategy": "none",
                "recency_boost_max": 0.0,
                "title_match_boost": 2.0,
                "title_all_terms_multiplier": 2.5,
                "exact_title_match_boost": 5.0,
                "content_match_boost": 0.5,
                "expand_primary_weight": 0.9,
                "expand_subword_max_frequency": 0.10,
                "expansion_combine_mode": "round_robin",
                "ai_summary_top_n": 15,
                "max_pagefind_results": 75,
                "results_per_page": 12,
            },
        },
        "reference": {
            "label": "Documentation & Reference",
            "description": 'Best for knowledge bases, documentation, encyclopedias, and compliance references. Strongly favors exact title matches and understands domain synonyms (e.g., searching "GDPR" also finds "data protection regulation"). Newer and older content rank equally since reference material stays relevant over time. Select this as your starting point — or leave it as-is. You can optionally adjust any individual setting below.',
            "values": {
                "recency_strategy": "none",
                "recency_boost_max": 0.0,
                "title_match_boost": 2.0,
                "title_all_terms_multiplier": 2.5,
                "exact_title_match_boost": 5.0,
                "content_match_boost": 0.5,
                "expand_primary_weight": 0.6,
                "expansion_combine_mode": "relevance_union",
                "ai_summary_top_n": 15,
                "max_pagefind_results": 75,
                "results_per_page": 12,
                "excerpt_length": 350,
            },
        },
        "ecommerce": {
            "label": "E-commerce & Product Store",
            "description": 'Best for online stores and product catalogs. People shop in their own words, not yours — so this preset reads product descriptions closely and interprets searches broadly. A search for "sparkly blue gift" finds lapis lazuli, not just items with those exact words. Newer and older products rank equally. Select this as your starting point — or leave it as-is. You can optionally adjust any individual setting below.',
            "values": {
                "recency_strategy": "none",
                "title_match_boost": 1.5,
                "title_all_terms_multiplier": 2.0,
                "content_match_boost": 0.6,
                "expand_primary_weight": 0.8,
                "expansion_combine_mode": "round_robin",
                "ai_summary_top_n": 12,
                "max_pagefind_results": 75,
                "results_per_page": 12,
                "excerpt_length": 300,
            },
        },
        "blog": {
            "label": "Blog & Editorial",
            "description": 'Best for blogs, news sites, and editorial content. Gives a gentle boost to newer posts while keeping older content findable, and interprets searches broadly so readers searching by topic or feeling ("scary moment", "funny story") get good results. Select this as your starting point — or leave it as-is. You can optionally adjust any individual setting below.',
            "values": {
                "recency_strategy": "exponential",
                "recency_boost_max": 0.25,
                "recency_half_life_days": 365,
                "title_match_boost": 1.5,
                "title_all_terms_multiplier": 2.0,
                "content_match_boost": 0.5,
                "expand_primary_weight": 0.7,
                "expansion_combine_mode": "round_robin",
                "ai_summary_top_n": 12,
                "max_pagefind_results": 60,
                "results_per_page": 10,
                "excerpt_length": 350,
            },
        },
    }

    @classmethod
    def _field_types(cls) -> dict[str, type]:
        return {f.name: f.type for f in fields(cls)}

    @classmethod
    def from_dict(cls, values: dict) -> ScoltaConfig:
        """Create from a mapping (Django settings, env, etc.).

        If a ``preset`` key is present, the named preset's values are applied
        first; any other keys override the preset. ``None`` means "not set" and
        falls through to the preset/base default. ``expansion_per_term_top_k``
        is locked at 3 and never settable.
        """
        config = cls()
        valid = {f.name for f in fields(cls)}

        preset = values.get("preset")
        if preset and preset in cls.PRESETS:
            config.preset = preset
            preset_data = cls.PRESETS[preset]
            preset_values = preset_data.get("values", preset_data)
            for key, value in preset_values.items():
                if key in valid:
                    setattr(config, key, value)

        for key, value in values.items():
            if key == "preset":
                continue
            if key == "expansion_per_term_top_k":
                continue
            if value is None:
                continue
            if key not in valid:
                # Debug, not warning: framework adapters pass their whole
                # settings dict here, adapter-only keys included.
                _LOGGER.debug("[scolta] Ignoring unknown config key: %r", key)
                continue
            setattr(config, key, cls._coerce(key, value))

        return config

    @classmethod
    def _coerce(cls, key: str, value):
        """Cast incoming value to the declared field type.

        CMS config layers store everything as strings; mirror PHP's typed
        property coercion, including PHP's (bool) cast semantics where only the
        strings "" and "0" are falsy ("false"/"no" cast to True, as in PHP).
        """
        declared = cls._field_types().get(key, "")
        decl = declared if isinstance(declared, str) else getattr(declared, "__name__", "")
        if decl == "bool":
            if isinstance(value, str):
                return value not in ("", "0")
            return bool(value)
        if decl == "int":
            return int(value)
        if decl == "float":
            return float(value)
        return value

    @classmethod
    def get_presets(cls) -> dict:
        return cls.PRESETS

    @classmethod
    def get_preset_values(cls, name: str) -> dict:
        return cls.PRESETS.get(name, {}).get("values", {})

    def to_js_scoring_config(self) -> dict:
        """Export scoring parameters matching the JS CONFIG object."""
        return {
            "RECENCY_BOOST_MAX": self.recency_boost_max,
            "RECENCY_HALF_LIFE_DAYS": self.recency_half_life_days,
            "RECENCY_PENALTY_AFTER_DAYS": self.recency_penalty_after_days,
            "RECENCY_MAX_PENALTY": self.recency_max_penalty,
            "TITLE_MATCH_BOOST": self.title_match_boost,
            "TITLE_ALL_TERMS_MULTIPLIER": self.title_all_terms_multiplier,
            "EXACT_TITLE_MATCH_BOOST": self.exact_title_match_boost,
            "CONTENT_MATCH_BOOST": self.content_match_boost,
            "PHRASE_ADJACENT_MULTIPLIER": self.phrase_adjacent_multiplier,
            "PHRASE_NEAR_MULTIPLIER": self.phrase_near_multiplier,
            "PHRASE_NEAR_WINDOW": self.phrase_near_window,
            "PHRASE_WINDOW": self.phrase_window,
            "EXCERPT_LENGTH": self.excerpt_length,
            "RESULTS_PER_PAGE": self.results_per_page,
            "MAX_PAGEFIND_RESULTS": self.max_pagefind_results,
            "AI_EXPAND_QUERY": self.ai_expand_query,
            "AI_SUMMARIZE": self.ai_summarize,
            "AI_SUMMARY_TOP_N": self.ai_summary_top_n,
            "AI_SUMMARY_MAX_CHARS": self.ai_summary_max_chars,
            "EXPAND_PRIMARY_WEIGHT": self.expand_primary_weight,
            "CROSS_LIST_BONUS": self.cross_list_bonus,
            "EXPAND_SUBWORD_MAX_FREQ": self.expand_subword_max_frequency,
            "EXPAND_SUBWORD_DENYLIST": self.expand_subword_deny_list,
            "SPECIFICITY_WEIGHTING": self.specificity_weighting,
            "SPECIFICITY_FLOOR": self.specificity_floor,
            "SPECIFICITY_STRONG_MATCH": self.specificity_strong_match,
            "SPECIFICITY_COOCCURRENCE": self.specificity_cooccurrence,
            "SPECIFICITY_AGREEMENT_GATE": self.specificity_agreement_gate,
            "SPECIFICITY_AGREEMENT_DECAY": self.specificity_agreement_decay,
            "FILTER_HINT_MIN_RESULTS": self.filter_hint_min_results,
            "FILTER_HINT_MIN_RATIO": self.filter_hint_min_ratio,
            "EXPANSION_COMBINE_MODE": self.expansion_combine_mode,
            "EXPANSION_PER_TERM_TOP_K": self.expansion_per_term_top_k,
            "AI_MAX_FOLLOWUPS": self.max_follow_ups,
            "AI_LANGUAGES": self.ai_languages,
            "AUTO_LANGUAGE_FILTER": self.auto_language_filter,
            "LANGUAGE": self.language,
            "CUSTOM_STOP_WORDS": self.custom_stop_words,
            "RECENCY_STRATEGY": self.recency_strategy,
            "RECENCY_CURVE": self.recency_curve,
        }

    def to_browser_config(self, endpoints: dict | None = None) -> dict:
        """Browser-side config for rendering ``window.scolta``.

        ``endpoints`` lets the host framework override the default
        ``/api/scolta/v1/...`` URLs with the routes it actually registered
        (e.g. Django ``reverse()`` results under a custom route prefix).
        Unspecified keys keep their defaults.
        """
        resolved_endpoints = {
            "expand": "/api/scolta/v1/expand-query",
            "summarize": "/api/scolta/v1/summarize",
            "followup": "/api/scolta/v1/followup",
        }
        if endpoints:
            resolved_endpoints.update(endpoints)
        return {
            "scoring": self.to_js_scoring_config(),
            "endpoints": resolved_endpoints,
            "wasmPath": "",
            "siteName": self.site_name,
            "pagefindPath": self.pagefind_index_path + "/pagefind.js",
            "filterFieldDescriptions": self.filter_field_descriptions,
            "hideEmptyFacets": self.hide_empty_facets,
            # Search as you type — top-level, not scoring keys.
            "saytEnabled": self.sayt_enabled,
            "saytMinChars": self.sayt_min_chars,
            "saytDebounceMs": self.sayt_debounce_ms,
            "saytMaxSuggestions": self.sayt_max_suggestions,
            "saytRecentSearches": self.sayt_recent_searches,
            "saytMaxRecent": self.sayt_max_recent,
            "saytExpand": self.sayt_expand,
            "saytExpandPerMinute": self.sayt_expand_per_minute,
            "saytExpansionDelayMs": self.sayt_expansion_delay_ms,
            "saytSuggestionAction": self.normalized_sayt_suggestion_action(),
        }

    def normalized_sayt_suggestion_action(self) -> str:
        """The suggestion action, clamped to a value the browser understands.

        An unrecognized configured value reaches the browser as ``navigate``
        rather than as itself, so the clamp happens once here instead of being
        rediscovered client-side.
        """
        if self.sayt_suggestion_action in self.SAYT_SUGGESTION_ACTIONS:
            return self.sayt_suggestion_action
        return "navigate"

    def to_ai_client_config(self) -> dict:
        """AI client config dict for constructing an AiClient."""
        config = {
            "provider": self.ai_provider,
            "api_key": self.ai_api_key,
            "model": self.ai_model,
        }
        if self.ai_base_url:
            config["base_url"] = self.ai_base_url
        return config
