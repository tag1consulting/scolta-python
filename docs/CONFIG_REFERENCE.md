# Configuration reference

`ScoltaConfig` is the single source of truth for Scolta's configuration defaults
and presets. This document mirrors it; the `tests/test_documentation.py` drift
guard fails the build if the two diverge — so this file can never silently fall
out of sync with the code.

## Configuration Properties

| Property | Type | Default | Description |
|---|---|---|---|
| `ai_provider` | string | `anthropic` |  |
| `ai_api_key` | string | `(empty)` |  |
| `ai_model` | string | `claude-sonnet-4-5-20250929` |  |
| `ai_expansion_model` | string | `(empty)` |  |
| `ai_base_url` | string | `(empty)` |  |
| `site_name` | string | `(empty)` |  |
| `site_description` | string | `website` |  |
| `search_page_path` | string | `/search` |  |
| `pagefind_index_path` | string | `/pagefind` |  |
| `cache_ttl` | int | `2592000` |  |
| `max_follow_ups` | int | `3` |  |
| `recency_boost_max` | float | `0.25` |  |
| `recency_half_life_days` | int | `365` |  |
| `recency_penalty_after_days` | int | `1825` |  |
| `recency_max_penalty` | float | `0.3` |  |
| `title_match_boost` | float | `2.0` |  |
| `title_all_terms_multiplier` | float | `1.5` |  |
| `exact_title_match_boost` | float | `5.0` |  |
| `content_match_boost` | float | `0.4` |  |
| `phrase_adjacent_multiplier` | float | `2.5` |  |
| `phrase_near_multiplier` | float | `1.5` |  |
| `phrase_near_window` | int | `5` |  |
| `phrase_window` | int | `15` |  |
| `expand_primary_weight` | float | `0.5` |  |
| `cross_list_bonus` | float | `0.05` |  |
| `expand_subword_max_frequency` | float | `0.05` |  |
| `expand_subword_deny_list` | array | `[]` |  |
| `expansion_combine_mode` | string | `relevance_union` |  |
| `expansion_per_term_top_k` | int | `3` | internal constant, not user-configurable (locked at 3) |
| `specificity_weighting` | bool | `true` | specificity-weighted ranking of partial matches; browser-side only |
| `specificity_floor` | float | `0.15` | floor for the specificity weight of a ubiquitous term; browser-side only |
| `specificity_strong_match` | float | `0.55` | specificity threshold at which a match counts as strong and on-intent; browser-side only |
| `specificity_cooccurrence` | float | `0.9` | multiplier on the co-occurrence agreement bonus; 0 restores the maximum-only merge; browser-side only |
| `specificity_agreement_gate` | float | `0.45` | specificity a term must clear to count toward the agreement bonus; browser-side only |
| `specificity_agreement_decay` | float | `1.0` | geometric factor applied to each successive agreeing axis; browser-side only |
| `filter_hint_min_results` | int | `5` | recall guard: minimum results a filter hint must keep to be auto-applied; browser-side only |
| `filter_hint_min_ratio` | float | `0.1` | recall guard: minimum fraction of the unfiltered union a filter hint must keep; browser-side only |
| `language` | string | `en` |  |
| `custom_stop_words` | array | `[]` |  |
| `recency_strategy` | string | `exponential` |  |
| `recency_curve` | array | `[]` |  |
| `excerpt_length` | int | `300` |  |
| `results_per_page` | int | `10` |  |
| `max_pagefind_results` | int | `50` |  |
| `show_attribution` | bool | `false` |  |
| `ai_expand_query` | bool | `true` |  |
| `ai_summarize` | bool | `true` |  |
| `ai_summary_top_n` | int | `10` |  |
| `ai_summary_max_chars` | int | `4000` |  |
| `ai_summary_max_tokens` | int | `1024` |  |
| `ai_languages` | array | `[]` |  |
| `auto_language_filter` | bool | `false` |  |
| `prompt_expand_query` | string | `(empty)` |  |
| `prompt_summarize` | string | `(empty)` |  |
| `prompt_follow_up` | string | `(empty)` |  |
| `indexer` | string | `auto` |  |
| `sortable_fields` | array | `[]` |  |
| `sortable_field_descriptions` | array | `{}` |  |
| `filter_fields` | array | `[]` |  |
| `filter_field_descriptions` | array | `{}` |  |
| `hide_empty_facets` | bool | `true` | hide a zero-count facet value and drop an all-zero filter group; false renders zero-count values as disabled rows |

## Presets

A `preset` is applied before explicit values (explicit always wins). `none` is
the default. Each row lists the non-default overrides the preset sets.

Available presets:

| Preset | Label | Key `values` |
|---|---|---|
| `none` | Start from Scratch | `expand_subword_max_frequency: 0.1`, `expansion_combine_mode: relevance_union` |
| `content_catalog` | Recipe & Content Catalog | `recency_strategy: none`, `recency_boost_max: 0.0`, `title_match_boost: 2.0`, `title_all_terms_multiplier: 2.5`, `exact_title_match_boost: 5.0`, `content_match_boost: 0.5`, `expand_primary_weight: 0.9`, `expand_subword_max_frequency: 0.1`, `expansion_combine_mode: round_robin`, `ai_summary_top_n: 15`, `max_pagefind_results: 75`, `results_per_page: 12` |
| `reference` | Documentation & Reference | `recency_strategy: none`, `recency_boost_max: 0.0`, `title_match_boost: 2.0`, `title_all_terms_multiplier: 2.5`, `exact_title_match_boost: 5.0`, `content_match_boost: 0.5`, `expand_primary_weight: 0.6`, `expansion_combine_mode: relevance_union`, `ai_summary_top_n: 15`, `max_pagefind_results: 75`, `results_per_page: 12`, `excerpt_length: 350` |
| `ecommerce` | E-commerce & Product Store | `recency_strategy: none`, `title_match_boost: 1.5`, `title_all_terms_multiplier: 2.0`, `content_match_boost: 0.6`, `expand_primary_weight: 0.8`, `expansion_combine_mode: round_robin`, `ai_summary_top_n: 12`, `max_pagefind_results: 75`, `results_per_page: 12`, `excerpt_length: 300` |
| `blog` | Blog & Editorial | `recency_strategy: exponential`, `recency_boost_max: 0.25`, `recency_half_life_days: 365`, `title_match_boost: 1.5`, `title_all_terms_multiplier: 2.0`, `content_match_boost: 0.5`, `expand_primary_weight: 0.7`, `expansion_combine_mode: round_robin`, `ai_summary_top_n: 12`, `max_pagefind_results: 60`, `results_per_page: 10`, `excerpt_length: 350` |
