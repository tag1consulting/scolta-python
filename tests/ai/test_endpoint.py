"""Ported from tests/Http/AiEndpointHandlerTest.php (1:1)."""

from doubles import (
    MockAiService,
    PromptCapturingAiService,
    SpyEnricher,
    SpyLogger,
    TrackingCacheDriver,
)

from scolta.ai.endpoint import AiEndpointHandler
from scolta.ai.enricher import NullEnricher, PromptEnricher
from scolta.cache import InMemoryCacheDriver


def make_handler(
    ai_service=None,
    cache=None,
    generation=1,
    cache_ttl=0,
    max_follow_ups=3,
    enricher=None,
    ai_languages=None,
    ai_expand_query=True,
    ai_summarize=True,
    sortable_fields=None,
    sortable_field_descriptions=None,
    filter_fields=None,
    filter_field_descriptions=None,
):
    return AiEndpointHandler(
        ai_service=ai_service or MockAiService('["term1", "term2"]'),
        cache=cache or InMemoryCacheDriver(),
        generation=generation,
        cache_ttl=cache_ttl,
        max_follow_ups=max_follow_ups,
        prompt_enricher=enricher or NullEnricher(),
        ai_languages=ai_languages or ["en"],
        ai_expand_query=ai_expand_query,
        ai_summarize=ai_summarize,
        sortable_fields=sortable_fields or [],
        sortable_field_descriptions=sortable_field_descriptions or {},
        filter_fields=filter_fields or [],
        filter_field_descriptions=filter_field_descriptions or {},
    )


# -- Validation: expandQuery --------------------------------------------------

def test_expand_query_rejects_empty_string():
    r = make_handler().handle_expand_query("")
    assert r["ok"] is False
    assert r["status"] == 400


def test_expand_query_rejects_over_max_length():
    r = make_handler().handle_expand_query("a" * 501)
    assert r["ok"] is False
    assert r["status"] == 400


def test_expand_query_accepts_max_length():
    h = make_handler(ai_service=MockAiService('["term1", "term2", "term3"]'))
    assert h.handle_expand_query("a" * 500)["ok"] is True


# -- Validation: summarize ----------------------------------------------------

def test_summarize_rejects_empty_query():
    r = make_handler().handle_summarize("", "some context")
    assert r["ok"] is False
    assert r["status"] == 400


def test_summarize_rejects_over_max_context():
    r = make_handler().handle_summarize("query", "x" * 100001)
    assert r["ok"] is False
    assert r["status"] == 400


# -- Validation: followUp -----------------------------------------------------

def test_follow_up_rejects_empty_messages():
    r = make_handler().handle_follow_up([])
    assert r["ok"] is False
    assert r["status"] == 400


def test_follow_up_rejects_when_limit_reached():
    h = make_handler(max_follow_ups=2)
    messages = [
        {"role": "user", "content": "initial question"},
        {"role": "assistant", "content": "first reply"},
        {"role": "user", "content": "follow-up 1"},
        {"role": "assistant", "content": "reply 1"},
        {"role": "user", "content": "follow-up 2"},
        {"role": "assistant", "content": "reply 2"},
        {"role": "user", "content": "follow-up 3 — too many"},
    ]
    r = h.handle_follow_up(messages)
    assert r["ok"] is False
    assert r["status"] == 429


def test_follow_up_counts_correctly():
    h = make_handler(ai_service=MockAiService("follow up response"), max_follow_ups=2)
    messages = [
        {"role": "user", "content": "initial question"},
        {"role": "assistant", "content": "first reply"},
        {"role": "user", "content": "follow-up 1"},
    ]
    r = h.handle_follow_up(messages)
    assert r["ok"] is True
    assert r["data"]["remaining"] == 1


# -- Caching ------------------------------------------------------------------

def test_expand_query_returns_cached_result():
    cache = InMemoryCacheDriver()
    ai = MockAiService("should not be called")
    h = make_handler(ai_service=ai, cache=cache, cache_ttl=3600)
    cache.set(h.cache_key("expand", "test query"),
              {"terms": ["cached term"], "expand_primary_weight": 0.5}, 3600)
    r = h.handle_expand_query("test query")
    assert r["ok"] is True
    assert r["data"]["terms"] == ["cached term"]
    assert ai.call_count == 0


def test_expand_query_stores_result_in_cache():
    cache = InMemoryCacheDriver()
    ai = MockAiService('["expanded1", "expanded2", "expanded3"]')
    h = make_handler(ai_service=ai, cache=cache, cache_ttl=3600)
    h.handle_expand_query("store test")
    assert cache.get(h.cache_key("expand", "store test")) is not None


def test_summarize_uses_cache_with_generation():
    cache = InMemoryCacheDriver()
    ai = MockAiService("should not be called")
    h = make_handler(ai_service=ai, cache=cache, cache_ttl=3600, generation=5)
    cache.set(h.cache_key("summarize", "query", "context"), {"summary": "cached summary"}, 3600)
    r = h.handle_summarize("query", "context")
    assert r["ok"] is True
    assert r["data"]["summary"] == "cached summary"
    assert ai.call_count == 0


def test_cache_key_includes_generation():
    k1 = make_handler(generation=1).cache_key("expand", "test")
    k2 = make_handler(generation=2).cache_key("expand", "test")
    assert k1 != k2
    assert "_1_" in k1
    assert "_2_" in k2


def test_cache_ttl_zero_never_reads_cache():
    cache = TrackingCacheDriver()
    h = make_handler(ai_service=MockAiService('["term1", "term2"]'), cache=cache, cache_ttl=0)
    h.handle_expand_query("test query")
    assert cache.get_calls == 0


def test_cache_ttl_zero_never_writes_cache():
    cache = TrackingCacheDriver()
    h = make_handler(ai_service=MockAiService('["term1", "term2"]'), cache=cache, cache_ttl=0)
    h.handle_expand_query("test query")
    assert cache.set_calls == 0


def test_max_follow_ups_zero_blocks_immediately():
    h = make_handler(max_follow_ups=0)
    messages = [
        {"role": "user", "content": "initial question"},
        {"role": "assistant", "content": "first reply"},
        {"role": "user", "content": "follow-up attempt"},
    ]
    r = h.handle_follow_up(messages)
    assert r["ok"] is False
    assert r["status"] == 429


# -- Response parsing ---------------------------------------------------------

def test_parse_expansion_strips_code_fences():
    h = make_handler()
    assert h.parse_expansion_response('```json\n["term1", "term2", "term3"]\n```', "original") == [
        "term1", "term2", "term3"
    ]


def test_parse_expansion_handles_raw_json():
    h = make_handler()
    assert h.parse_expansion_response('["alpha", "beta", "gamma"]', "original") == [
        "alpha", "beta", "gamma"
    ]


def test_parse_expansion_handles_object_format():
    h = make_handler()
    assert h.parse_expansion_response('{"terms": ["alpha", "beta", "gamma"]}', "original") == [
        "alpha", "beta", "gamma"
    ]


def test_parse_expansion_falls_back_on_invalid_json():
    h = make_handler()
    assert h.parse_expansion_response("this is not json at all", "original query") == [
        "original query"
    ]


def test_parse_expansion_falls_back_on_single_term():
    h = make_handler()
    assert h.parse_expansion_response('["only_one"]', "original") == ["original"]


# -- Sort hint: parsing -------------------------------------------------------

def test_sort_hint_parsed_from_object_format():
    ai = MockAiService('{"terms": ["gem", "gemstone", "rock"], "sort": {"field": "price", "direction": "desc"}}')
    h = make_handler(ai_service=ai, sortable_fields=["price", "date"])
    r = h.handle_expand_query("most expensive stone")
    assert r["ok"] is True
    assert r["data"]["sort_hint"] == {"field": "price", "direction": "desc"}


def test_sort_hint_absent_when_llm_omits_it():
    ai = MockAiService('{"terms": ["gem", "gemstone", "mineral"]}')
    h = make_handler(ai_service=ai, sortable_fields=["price"])
    r = h.handle_expand_query("blue stones")
    assert r["ok"] is True
    assert "sort_hint" not in r["data"]


def test_sort_hint_absent_when_no_sortable_fields_configured():
    ai = MockAiService('{"terms": ["gem", "rock", "mineral"], "sort": {"field": "price", "direction": "desc"}}')
    h = make_handler(ai_service=ai, sortable_fields=[])
    r = h.handle_expand_query("most expensive stone")
    assert r["ok"] is True
    assert "sort_hint" not in r["data"]


def test_sort_hint_ignored_when_field_not_in_sortable_list():
    ai = MockAiService('{"terms": ["gem", "rock"], "sort": {"field": "unknown_field", "direction": "desc"}}')
    h = make_handler(ai_service=ai, sortable_fields=["price", "date"])
    r = h.handle_expand_query("most expensive stone")
    assert "sort_hint" not in r["data"]


def test_sort_hint_ignored_when_direction_invalid():
    ai = MockAiService('{"terms": ["gem", "rock"], "sort": {"field": "price", "direction": "invalid"}}')
    h = make_handler(ai_service=ai, sortable_fields=["price"])
    r = h.handle_expand_query("most expensive stone")
    assert "sort_hint" not in r["data"]


def test_sort_hint_ignored_when_sort_is_not_an_array():
    ai = MockAiService('{"terms": ["gem", "rock"], "sort": "price:desc"}')
    h = make_handler(ai_service=ai, sortable_fields=["price"])
    r = h.handle_expand_query("most expensive stone")
    assert "sort_hint" not in r["data"]


def test_sort_hint_asc_direction_allowed():
    ai = MockAiService('{"terms": ["affordable", "budget"], "sort": {"field": "price", "direction": "asc"}}')
    h = make_handler(ai_service=ai, sortable_fields=["price"])
    r = h.handle_expand_query("cheapest stone")
    assert r["data"]["sort_hint"] == {"field": "price", "direction": "asc"}


# -- Sort hint: ascending price vocabulary (#124) -----------------------------

def test_prompt_contains_ascending_price_patterns():
    ai = PromptCapturingAiService('{"terms": ["gem"]}')
    make_handler(ai_service=ai, sortable_fields=["price"]).handle_expand_query("cheapest crystals")
    for needle in ("cheapest", "lowest price", "most affordable", "least expensive", "budget"):
        assert needle in ai.last_system_prompt


def test_prompt_specifies_asc_direction_for_cheapest_patterns():
    ai = PromptCapturingAiService('{"terms": ["gem"]}')
    make_handler(ai_service=ai, sortable_fields=["price"]).handle_expand_query("cheapest crystals")
    assert "Price/cost (asc)" in ai.last_system_prompt
    assert "direction asc" in ai.last_system_prompt


def test_prompt_specifies_desc_direction_for_expensive_patterns():
    ai = PromptCapturingAiService('{"terms": ["gem"]}')
    make_handler(ai_service=ai, sortable_fields=["price"]).handle_expand_query("most expensive crystals")
    assert "Price/cost (desc)" in ai.last_system_prompt
    assert "direction desc" in ai.last_system_prompt


def _asc_sort_handler():
    ai = MockAiService('{"terms": ["crystal", "gem"], "sort": {"field": "price", "direction": "asc"}, "subject_terms": ["crystals"]}')
    return make_handler(ai_service=ai, sortable_fields=["price"])


def test_cheapest_query_parses_asc_sort_hint():
    r = _asc_sort_handler().handle_expand_query("cheapest crystals")
    assert r["data"]["sort_hint"] == {"field": "price", "direction": "asc"}
    assert r["data"]["subject_terms"] == ["crystals"]


def test_lowest_price_query_parses_asc_sort_hint():
    r = _asc_sort_handler().handle_expand_query("lowest price crystals")
    assert r["data"]["sort_hint"] == {"field": "price", "direction": "asc"}


def test_most_affordable_query_parses_asc_sort_hint():
    r = _asc_sort_handler().handle_expand_query("most affordable crystals")
    assert r["data"]["sort_hint"] == {"field": "price", "direction": "asc"}


def test_least_expensive_query_parses_asc_sort_hint():
    r = _asc_sort_handler().handle_expand_query("least expensive crystals")
    assert r["data"]["sort_hint"] == {"field": "price", "direction": "asc"}


def test_most_expensive_still_parses_desc_sort_hint():
    ai = MockAiService('{"terms": ["crystal", "gem"], "sort": {"field": "price", "direction": "desc"}, "subject_terms": ["crystals"]}')
    h = make_handler(ai_service=ai, sortable_fields=["price"])
    r = h.handle_expand_query("most expensive crystals")
    assert r["data"]["sort_hint"] == {"field": "price", "direction": "desc"}


def test_non_sort_query_omits_sort_hint():
    ai = MockAiService('{"terms": ["crystal", "healing", "meditation"]}')
    h = make_handler(ai_service=ai, sortable_fields=["price"])
    r = h.handle_expand_query("crystals for meditation")
    assert "sort_hint" not in r["data"]


def test_legacy_array_response_still_works_with_sortable_fields():
    ai = MockAiService('["gem", "gemstone", "mineral"]')
    h = make_handler(ai_service=ai, sortable_fields=["price"])
    r = h.handle_expand_query("blue stones")
    assert r["data"]["terms"] == ["gem", "gemstone", "mineral"]
    assert "sort_hint" not in r["data"]


# -- Sort hint: sortable fields in prompt -------------------------------------

def test_sortable_fields_appended_to_prompt_when_configured():
    ai = PromptCapturingAiService('{"terms": ["gem", "rock", "mineral"]}')
    make_handler(ai_service=ai, sortable_fields=["price", "date", "rating"]).handle_expand_query("test query")
    assert "- price" in ai.last_system_prompt
    assert "- date" in ai.last_system_prompt
    assert "- rating" in ai.last_system_prompt
    assert "SORT INTENT" in ai.last_system_prompt


def test_sortable_fields_not_appended_when_empty():
    ai = PromptCapturingAiService('{"terms": ["gem", "rock", "mineral"]}')
    make_handler(ai_service=ai, sortable_fields=[]).handle_expand_query("test query")
    assert "SORT INTENT" not in ai.last_system_prompt
    assert "sortable" not in ai.last_system_prompt


# -- Sort hint: prompt content (false positive guard) -------------------------

def test_sort_intent_prompt_forbids_superlative_qualifiers():
    ai = PromptCapturingAiService('{"terms": ["gem", "rock", "mineral"]}')
    make_handler(ai_service=ai, sortable_fields=["price"]).handle_expand_query("test query")
    assert "SUPERLATIVES AS QUALIFIERS" in ai.last_system_prompt
    assert "most popular" in ai.last_system_prompt


def test_sort_intent_prompt_requires_semantic_field_match():
    import re
    ai = PromptCapturingAiService('{"terms": ["gem", "rock"]}')
    make_handler(ai_service=ai, sortable_fields=["price", "date"]).handle_expand_query("test")
    assert re.search(r"semantically? map|direct.*semantic|semantic.*match", ai.last_system_prompt, re.I)


def test_sort_intent_prompt_prefers_false_negatives():
    import re
    ai = PromptCapturingAiService('{"terms": ["gem", "rock"]}')
    make_handler(ai_service=ai, sortable_fields=["price"]).handle_expand_query("test")
    assert re.search(r"false negative|prefer.*omit|uncertain.*omit|when.*doubt.*omit", ai.last_system_prompt, re.I)


# -- Subject terms: parsing ---------------------------------------------------

def test_subject_terms_parsed_when_present_with_sort():
    ai = MockAiService('{"terms": ["gem", "gemstone"], "sort": {"field": "price", "direction": "desc"}, "subject_terms": ["tooth"]}')
    h = make_handler(ai_service=ai, sortable_fields=["price"])
    r = h.handle_expand_query("most expensive tooth")
    assert r["data"]["subject_terms"] == ["tooth"]
    assert "sort_hint" in r["data"]


def test_subject_terms_multiple_words():
    ai = MockAiService('{"terms": ["gemstone", "mineral"], "sort": {"field": "price", "direction": "asc"}, "subject_terms": ["blue stone"]}')
    h = make_handler(ai_service=ai, sortable_fields=["price"])
    r = h.handle_expand_query("cheapest blue stone")
    assert r["data"]["subject_terms"] == ["blue stone"]


def test_subject_terms_absent_when_only_sort_intent():
    ai = MockAiService('{"terms": ["high price", "costly"], "sort": {"field": "price", "direction": "desc"}, "subject_terms": []}')
    h = make_handler(ai_service=ai, sortable_fields=["price"])
    r = h.handle_expand_query("most expensive")
    assert "subject_terms" not in r["data"]


def test_subject_terms_absent_when_omitted_by_llm():
    ai = MockAiService('{"terms": ["gem", "rock"], "sort": {"field": "price", "direction": "desc"}}')
    h = make_handler(ai_service=ai, sortable_fields=["price"])
    r = h.handle_expand_query("most expensive stone")
    assert "subject_terms" not in r["data"]


def test_subject_terms_absent_when_no_sort():
    ai = MockAiService('{"terms": ["gem", "gemstone", "mineral"]}')
    h = make_handler(ai_service=ai, sortable_fields=["price"])
    r = h.handle_expand_query("blue stones")
    assert "subject_terms" not in r["data"]
    assert "sort_hint" not in r["data"]


def test_subject_terms_malformed_not_array_ignored():
    ai = MockAiService('{"terms": ["gem", "rock"], "sort": {"field": "price", "direction": "desc"}, "subject_terms": "tooth"}')
    h = make_handler(ai_service=ai, sortable_fields=["price"])
    r = h.handle_expand_query("most expensive tooth")
    assert "subject_terms" not in r["data"]


def test_subject_terms_filters_non_string_entries():
    ai = MockAiService('{"terms": ["gem", "rock"], "sort": {"field": "price", "direction": "desc"}, "subject_terms": ["tooth", null, 42, "fossil"]}')
    h = make_handler(ai_service=ai, sortable_fields=["price"])
    r = h.handle_expand_query("most expensive tooth fossil")
    assert r["data"]["subject_terms"] == ["tooth", "fossil"]


def test_subject_terms_in_prompt_when_sortable_fields_configured():
    ai = PromptCapturingAiService('{"terms": ["gem", "rock", "mineral"]}')
    make_handler(ai_service=ai, sortable_fields=["price"]).handle_expand_query("test query")
    assert "SUBJECT TERMS" in ai.last_system_prompt
    assert "subject_terms" in ai.last_system_prompt


def test_subject_terms_example_in_prompt_shows_empty_for_sort_only_query():
    ai = PromptCapturingAiService('{"terms": ["gem", "rock"]}')
    make_handler(ai_service=ai, sortable_fields=["price"]).handle_expand_query("test")
    assert "most expensive" in ai.last_system_prompt
    assert "subject_terms: []" in ai.last_system_prompt


# -- Sort hint: cache round-trip ---------------------------------------------

def test_sort_hint_survives_cache_round_trip():
    cache = InMemoryCacheDriver()
    ai = MockAiService('{"terms": ["gem", "rock"], "sort": {"field": "price", "direction": "desc"}}')
    h = make_handler(ai_service=ai, cache=cache, cache_ttl=3600, sortable_fields=["price"])
    r1 = h.handle_expand_query("most expensive stone")
    h2 = make_handler(ai_service=MockAiService("should not be called"), cache=cache,
                      cache_ttl=3600, sortable_fields=["price"])
    r2 = h2.handle_expand_query("most expensive stone")
    assert r1["data"] == r2["data"]
    assert r2["data"]["sort_hint"] == {"field": "price", "direction": "desc"}


# -- Error paths --------------------------------------------------------------

def test_expand_query_returns_503_on_ai_exception():
    h = make_handler(ai_service=MockAiService("", throw_on_message=True))
    r = h.handle_expand_query("test query")
    assert r["ok"] is False
    assert r["status"] == 503


def test_summarize_returns_503_on_ai_exception():
    h = make_handler(ai_service=MockAiService("", throw_on_message=True))
    r = h.handle_summarize("test", "some context")
    assert r["ok"] is False
    assert r["status"] == 503


def test_follow_up_returns_503_on_ai_exception():
    h = make_handler(ai_service=MockAiService("", throw_on_conversation=True))
    r = h.handle_follow_up([{"role": "user", "content": "hello"}])
    assert r["ok"] is False
    assert r["status"] == 503


# -- Invalid API key: 401 -----------------------------------------------------

def test_expand_query_returns_401_on_invalid_api_key():
    h = make_handler(ai_service=MockAiService("", throw_api_key_invalid=True))
    r = h.handle_expand_query("test query")
    assert r["ok"] is False
    assert r["status"] == 401
    assert "invalid" in r["error"].lower()


def test_summarize_returns_401_on_invalid_api_key():
    h = make_handler(ai_service=MockAiService("", throw_api_key_invalid=True))
    r = h.handle_summarize("test", "some context")
    assert r["status"] == 401


def test_follow_up_returns_401_on_invalid_api_key():
    h = make_handler(ai_service=MockAiService("", throw_api_key_invalid=True))
    r = h.handle_follow_up([{"role": "user", "content": "hello"}])
    assert r["status"] == 401


def test_invalid_api_key_logs_error():
    logger = SpyLogger()
    h = AiEndpointHandler(
        ai_service=MockAiService("", throw_api_key_invalid=True),
        cache=InMemoryCacheDriver(), generation=1, cache_ttl=0, max_follow_ups=3, logger=logger,
    )
    h.handle_summarize("test", "context")
    assert logger.errors


# -- Rate limiting: 429 -------------------------------------------------------

def test_expand_query_returns_429_on_rate_limit():
    h = make_handler(ai_service=MockAiService("", throw_rate_limit=True))
    r = h.handle_expand_query("test query")
    assert r["status"] == 429


def test_summarize_returns_429_on_rate_limit():
    h = make_handler(ai_service=MockAiService("", throw_rate_limit=True))
    assert h.handle_summarize("test", "some context")["status"] == 429


def test_follow_up_returns_429_on_rate_limit():
    h = make_handler(ai_service=MockAiService("", throw_rate_limit=True))
    assert h.handle_follow_up([{"role": "user", "content": "hello"}])["status"] == 429


def test_rate_limit_response_includes_retry_after_when_present():
    h = make_handler(ai_service=MockAiService("", throw_rate_limit=True, rate_limit_retry_after="60"))
    r = h.handle_expand_query("test query")
    assert r["status"] == 429
    assert r["retry_after"] == "60"


def test_rate_limit_response_omits_retry_after_when_absent():
    h = make_handler(ai_service=MockAiService("", throw_rate_limit=True, rate_limit_retry_after=None))
    r = h.handle_expand_query("test query")
    assert r["status"] == 429
    assert "retry_after" not in r


# -- No API key: graceful degradation -----------------------------------------

def test_summarize_returns_200_with_empty_data_when_no_api_key():
    h = make_handler(ai_service=MockAiService("", throw_api_key_missing=True))
    r = h.handle_summarize("test query", "some context")
    assert r["ok"] is True
    assert r["data"] == {}
    assert "status" not in r


def test_expand_query_returns_200_with_original_query_when_no_api_key():
    h = make_handler(ai_service=MockAiService("", throw_api_key_missing=True))
    r = h.handle_expand_query("my search query")
    assert r["ok"] is True
    assert r["data"]["terms"] == ["my search query"]
    assert "expand_primary_weight" in r["data"]
    assert "status" not in r


def test_follow_up_returns_200_with_empty_response_when_no_api_key():
    h = make_handler(ai_service=MockAiService("", throw_api_key_missing=True))
    r = h.handle_follow_up([{"role": "user", "content": "hello"}])
    assert r["ok"] is True
    assert r["data"]["response"] == ""
    assert r["data"]["remaining"] == 0
    assert "status" not in r


def test_summarize_no_api_key_does_not_log_503():
    logger = SpyLogger()
    h = AiEndpointHandler(
        ai_service=MockAiService("", throw_api_key_missing=True),
        cache=InMemoryCacheDriver(), generation=1, cache_ttl=0, max_follow_ups=3, logger=logger,
    )
    h.handle_summarize("test", "context")
    assert not logger.errors


def test_expand_query_no_api_key_does_not_log_503():
    logger = SpyLogger()
    h = AiEndpointHandler(
        ai_service=MockAiService("", throw_api_key_missing=True),
        cache=InMemoryCacheDriver(), generation=1, cache_ttl=0, max_follow_ups=3, logger=logger,
    )
    h.handle_expand_query("test query")
    assert not logger.errors


def test_expand_query_handles_empty_ai_response():
    h = make_handler(ai_service=MockAiService(""))
    r = h.handle_expand_query("test query")
    assert r["ok"] is True
    assert r["data"]["terms"] == ["test query"]


def test_expand_query_response_includes_expand_primary_weight():
    h = AiEndpointHandler(
        ai_service=MockAiService('["term1", "term2"]'),
        cache=InMemoryCacheDriver(), generation=1, cache_ttl=0, max_follow_ups=3,
        expand_primary_weight=0.8,
    )
    r = h.handle_expand_query("test query")
    assert isinstance(r["data"]["terms"], list)
    assert r["data"]["expand_primary_weight"] == 0.8


# -- Prompt enrichment --------------------------------------------------------

def test_null_enricher_passes_through_unchanged():
    original = "You are a helpful search assistant."
    assert NullEnricher().enrich(original, "summarize", {"query": "test"}) == original


def test_expand_query_calls_enricher_before_ai_service():
    enricher = SpyEnricher("ENRICHED: ")
    ai = PromptCapturingAiService('["term1", "term2", "term3"]')
    r = make_handler(ai_service=ai, enricher=enricher).handle_expand_query("test query")
    assert r["ok"] is True
    assert enricher.call_count == 1
    assert enricher.last_prompt_name == "expand_query"
    assert enricher.last_context == {"query": "test query"}
    assert ai.last_system_prompt.startswith("ENRICHED: ")


def test_summarize_calls_enricher_before_ai_service():
    enricher = SpyEnricher("ENRICHED: ")
    ai = PromptCapturingAiService("A helpful summary.")
    r = make_handler(ai_service=ai, enricher=enricher).handle_summarize("test query", "some context")
    assert r["ok"] is True
    assert enricher.call_count == 1
    assert enricher.last_prompt_name == "summarize"
    assert enricher.last_context == {"query": "test query", "context": "some context"}
    assert ai.last_system_prompt.startswith("ENRICHED: ")


def test_follow_up_calls_enricher_before_ai_service():
    enricher = SpyEnricher("ENRICHED: ")
    ai = PromptCapturingAiService("follow up response", capture_conversation=True)
    messages = [{"role": "user", "content": "hello"}]
    r = make_handler(ai_service=ai, enricher=enricher).handle_follow_up(messages)
    assert r["ok"] is True
    assert enricher.call_count == 1
    assert enricher.last_prompt_name == "follow_up"
    assert enricher.last_context == {"messages": messages}
    assert ai.last_system_prompt.startswith("ENRICHED: ")


def test_custom_enricher_modifies_prompt():
    class _E(PromptEnricher):
        def enrich(self, resolved_prompt, prompt_name, context=None):
            return resolved_prompt + "\n\nAlways mention our return policy."

    ai = PromptCapturingAiService('["term1", "term2"]')
    make_handler(ai_service=ai, enricher=_E()).handle_expand_query("pricing")
    assert "Always mention our return policy." in ai.last_system_prompt


def test_default_enricher_is_null_enricher():
    ai = PromptCapturingAiService('["term1", "term2"]')
    h = AiEndpointHandler(
        ai_service=ai, cache=InMemoryCacheDriver(), generation=1, cache_ttl=0, max_follow_ups=3
    )
    h.handle_expand_query("test")
    assert ai.last_system_prompt == "Expand the following search query."


# -- Language instruction -----------------------------------------------------

def test_single_language_does_not_add_instruction():
    ai = PromptCapturingAiService("A helpful summary.")
    make_handler(ai_service=ai, ai_languages=["en"]).handle_summarize("test query", "some context")
    assert "supported languages" not in ai.last_system_prompt


def test_multiple_languages_adds_instruction_to_summarize():
    ai = PromptCapturingAiService("A helpful summary.")
    make_handler(ai_service=ai, ai_languages=["en", "es", "fr"]).handle_summarize("q", "ctx")
    assert "en, es, fr" in ai.last_system_prompt
    assert "Respond in the same language" in ai.last_system_prompt
    assert "Otherwise respond in en" in ai.last_system_prompt


def test_multiple_languages_adds_instruction_to_expand_query():
    ai = PromptCapturingAiService('["term1", "term2", "term3"]')
    make_handler(ai_service=ai, ai_languages=["en", "de"]).handle_expand_query("test query")
    assert "en, de" in ai.last_system_prompt
    assert "Return expansion terms" in ai.last_system_prompt


def test_multiple_languages_adds_instruction_to_follow_up():
    ai = PromptCapturingAiService("follow up response", capture_conversation=True)
    make_handler(ai_service=ai, ai_languages=["en", "ja"]).handle_follow_up(
        [{"role": "user", "content": "hello"}]
    )
    assert "en, ja" in ai.last_system_prompt
    assert "Respond in the same language" in ai.last_system_prompt


def test_language_instruction_mentions_all_configured_languages():
    ai = PromptCapturingAiService("A helpful summary.")
    make_handler(ai_service=ai, ai_languages=["en", "es", "fr", "de", "ja"]).handle_summarize("q", "ctx")
    assert "en, es, fr, de, ja" in ai.last_system_prompt


def test_default_languages_do_not_add_instruction():
    ai = PromptCapturingAiService("A helpful summary.")
    h = AiEndpointHandler(
        ai_service=ai, cache=InMemoryCacheDriver(), generation=1, cache_ttl=0, max_follow_ups=3
    )
    h.handle_summarize("test query", "some context")
    assert "supported languages" not in ai.last_system_prompt


# -- AI feature toggles -------------------------------------------------------

def test_expand_query_disabled_returns_404():
    r = make_handler(ai_expand_query=False).handle_expand_query("test query")
    assert r["ok"] is False
    assert r["status"] == 404
    assert r["error"] == "Feature disabled"


def test_expand_query_disabled_does_not_call_ai_service():
    ai = MockAiService('["term1", "term2"]')
    make_handler(ai_service=ai, ai_expand_query=False).handle_expand_query("test query")
    assert ai.call_count == 0


def test_summarize_disabled_returns_404():
    r = make_handler(ai_summarize=False).handle_summarize("test query", "some context")
    assert r["ok"] is False
    assert r["status"] == 404
    assert r["error"] == "Feature disabled"


def test_summarize_disabled_does_not_call_ai_service():
    ai = MockAiService("A summary.")
    make_handler(ai_service=ai, ai_summarize=False).handle_summarize("test query", "some context")
    assert ai.call_count == 0


def test_follow_up_unaffected_by_expand_query_toggle():
    ai = MockAiService("follow up response")
    h = make_handler(ai_service=ai, ai_expand_query=False, ai_summarize=False)
    r = h.handle_follow_up([{"role": "user", "content": "hello"}])
    assert r["ok"] is True
    assert ai.call_count == 1


# -- Sortable field descriptions ----------------------------------------------

def test_sortable_fields_with_descriptions_appears_in_prompt():
    ai = PromptCapturingAiService('{"terms": ["gem", "rock"]}')
    make_handler(
        ai_service=ai,
        sortable_fields=["price", "word_count"],
        sortable_field_descriptions={"price": "Product price in store currency",
                                     "word_count": "Article length in words"},
    ).handle_expand_query("test")
    assert "- price: Product price in store currency" in ai.last_system_prompt
    assert "- word_count: Article length in words" in ai.last_system_prompt


def test_sortable_fields_without_descriptions_fall_back_to_bare_names():
    ai = PromptCapturingAiService('{"terms": ["gem", "rock"]}')
    make_handler(ai_service=ai, sortable_fields=["price", "date"]).handle_expand_query("test")
    assert "- price" in ai.last_system_prompt
    assert "- date" in ai.last_system_prompt
    assert "- price:" not in ai.last_system_prompt


def test_sortable_field_descriptions_ignored_when_no_sortable_fields():
    ai = PromptCapturingAiService('{"terms": ["gem", "rock"]}')
    make_handler(
        ai_service=ai, sortable_fields=[],
        sortable_field_descriptions={"price": "Should not appear"},
    ).handle_expand_query("test")
    assert "SORT INTENT" not in ai.last_system_prompt
    assert "Should not appear" not in ai.last_system_prompt


# -- Filter fields: prompt generation -----------------------------------------

def test_filter_fields_instruction_appears_when_configured():
    ai = PromptCapturingAiService('{"terms": ["gem", "rock"]}')
    make_handler(
        ai_service=ai,
        filter_fields=["topic", "era"],
        filter_field_descriptions={"topic": "Subject area (Science, History, etc.)",
                                   "era": "Historical period"},
    ).handle_expand_query("test")
    assert "FILTER INTENT" in ai.last_system_prompt
    assert "- topic: Subject area (Science, History, etc.)" in ai.last_system_prompt
    assert "- era: Historical period" in ai.last_system_prompt


def test_filter_fields_instruction_absent_when_not_configured():
    ai = PromptCapturingAiService('{"terms": ["gem", "rock"]}')
    make_handler(ai_service=ai, filter_fields=[]).handle_expand_query("test")
    assert "FILTER INTENT" not in ai.last_system_prompt


def test_filter_fields_without_descriptions_fall_back_to_bare_names():
    ai = PromptCapturingAiService('{"terms": ["gem", "rock"]}')
    make_handler(ai_service=ai, filter_fields=["topic", "era"]).handle_expand_query("test")
    assert "- topic" in ai.last_system_prompt
    assert "- era" in ai.last_system_prompt
    assert "- topic:" not in ai.last_system_prompt


# -- Filter hint: parsing -----------------------------------------------------

def test_filter_hint_parsed_from_object_format():
    ai = MockAiService('{"terms": ["water", "hydrology"], "filters": {"topic": "Science"}}')
    h = make_handler(ai_service=ai, filter_fields=["topic", "era"])
    r = h.handle_expand_query("Science articles about water")
    assert r["data"]["filter_hint"] == {"topic": "Science"}


def test_filter_hint_multiple_dimensions():
    ai = MockAiService('{"terms": ["roman", "engineering"], "filters": {"topic": "History", "era": "Ancient"}}')
    h = make_handler(ai_service=ai, filter_fields=["topic", "era"])
    r = h.handle_expand_query("Ancient Roman engineering")
    assert r["data"]["filter_hint"] == {"topic": "History", "era": "Ancient"}


def test_filter_hint_absent_when_llm_omits_it():
    ai = MockAiService('{"terms": ["water", "aqua"]}')
    h = make_handler(ai_service=ai, filter_fields=["topic"])
    assert "filter_hint" not in h.handle_expand_query("water")["data"]


def test_filter_hint_absent_when_no_filter_fields_configured():
    ai = MockAiService('{"terms": ["water", "aqua"], "filters": {"topic": "Science"}}')
    h = make_handler(ai_service=ai, filter_fields=[])
    assert "filter_hint" not in h.handle_expand_query("Science water")["data"]


def test_filter_hint_invalid_dimension_rejected():
    ai = MockAiService('{"terms": ["water", "aqua"], "filters": {"unknown_dim": "Science"}}')
    h = make_handler(ai_service=ai, filter_fields=["topic", "era"])
    assert "filter_hint" not in h.handle_expand_query("water")["data"]


def test_filter_hint_malformed_ignored():
    ai = MockAiService('{"terms": ["water", "aqua"], "filters": "invalid"}')
    h = make_handler(ai_service=ai, filter_fields=["topic"])
    assert "filter_hint" not in h.handle_expand_query("water")["data"]


def test_filter_hint_and_sort_hint_coexist():
    ai = MockAiService('{"terms": ["science", "articles"], "sort": {"field": "date", "direction": "desc"}, "filters": {"topic": "Science"}}')
    h = make_handler(ai_service=ai, sortable_fields=["date"], filter_fields=["topic"])
    r = h.handle_expand_query("newest Science articles")
    assert r["data"]["sort_hint"] == {"field": "date", "direction": "desc"}
    assert r["data"]["filter_hint"] == {"topic": "Science"}


def test_backward_compat_no_both_descriptions():
    ai = PromptCapturingAiService('{"terms": ["gem", "rock"]}')
    make_handler(ai_service=ai, sortable_fields=["price", "date"]).handle_expand_query("most expensive stone")
    assert "SORT INTENT" in ai.last_system_prompt
    assert "FILTER INTENT" not in ai.last_system_prompt
    assert "- price" in ai.last_system_prompt
    assert "- date" in ai.last_system_prompt
