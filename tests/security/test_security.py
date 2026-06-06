"""Security-oriented tests (ported from tests/Security/).

InputValidationTest: malicious/pathological inputs cannot inject HTML/JS into
indexed content, crash the indexer, or escape the index directory; the endpoint
rejects invalid queries and enforces follow-up limits. AiErrorHandlingTest: the
Ai client maps provider errors to the right exceptions (the bulk is also in
tests/ai/test_client.py; the OpenAI-branch + degenerate-response cases are here).
"""

import glob
from pathlib import Path

import httpx
import pytest

from scolta.ai.client import AiClient
from scolta.ai.endpoint import AiEndpointHandler
from scolta.cache import NullCacheDriver
from scolta.content import ContentItem
from scolta.exceptions import ApiKeyInvalidException, RateLimitException
from scolta.index.build_intent import BuildIntent
from scolta.index.indexer import PythonIndexer
from scolta.index.inverted_index_builder import InvertedIndexBuilder
from scolta.index.memory_budget import MemoryBudget
from scolta.index.orchestrator import IndexBuildOrchestrator
from scolta.index.stemmer import Stemmer
from scolta.index.tokenizer import Tokenizer


class _MockAi:
    def __init__(self, response='["a","b"]'):
        self.response = response

    def get_expand_prompt(self):
        return "expand"

    def get_summarize_prompt(self):
        return "summarize"

    def get_follow_up_prompt(self):
        return "follow"

    def message(self, *a):
        return self.response

    def message_for_operation(self, *a):
        return self.response

    def conversation(self, *a):
        return self.response


def _handler(**kw):
    return AiEndpointHandler(_MockAi(), NullCacheDriver(), generation=0, cache_ttl=0,
                            max_follow_ups=kw.pop("max_follow_ups", 3), **kw)


def _build_vocab(items, tmp_path):
    out = str(tmp_path / "out")
    IndexBuildOrchestrator(str(tmp_path / "st"), out).build(
        BuildIntent.fresh(len(items), MemoryBudget.default()), items
    )
    return out


# -- HTML/JS injection --------------------------------------------------------


def test_script_tag_in_title_stripped_from_tokens():
    builder = InvertedIndexBuilder(Tokenizer(), Stemmer("en"))
    td = builder.tokenize_item(ContentItem(
        "x", '<script>alert("xss")</script>Legitimate Title',
        "<p>Safe body content that is sufficiently long for indexing.</p>", "/p", "2026-01-01",
    ))
    stems = {t.stem for t in td["titleTokens"]}
    assert "script" not in stems
    assert "alert" not in stems
    assert "legitimate" in stems
    assert "<script>" not in td["content"]


def test_html_entities_in_title_decoded():
    builder = InvertedIndexBuilder(Tokenizer(), Stemmer("en"))
    td = builder.tokenize_item(ContentItem(
        "x", "Tom &amp; Jerry &lt;Show&gt;",
        "<p>Body content long enough to index properly here.</p>", "/p", "2026-01-01",
    ))
    assert td["cleanTitle"] == "Tom & Jerry <Show>"
    assert "amp" not in {t.stem for t in td["titleTokens"]}


# -- pathological sizes / bytes -----------------------------------------------


def test_very_long_title_does_not_crash():
    builder = InvertedIndexBuilder(Tokenizer(), Stemmer("en"))
    td = builder.tokenize_item(ContentItem(
        "x", "word " * 5000, "<p>" + "body " * 50 + "</p>", "/p", "2026-01-01",
    ))
    assert td is not None


def test_very_large_body_does_not_crash():
    builder = InvertedIndexBuilder(Tokenizer(), Stemmer("en"))
    td = builder.tokenize_item(ContentItem(
        "x", "Title", "<p>" + "lorem ipsum " * 20000 + "</p>", "/p", "2026-01-01",
    ))
    assert td is not None
    assert td["wordCount"] > 1000


def test_null_bytes_in_content_are_safe():
    builder = InvertedIndexBuilder(Tokenizer(), Stemmer("en"))
    td = builder.tokenize_item(ContentItem(
        "x", "Title", "<p>safe\x00content with null bytes embedded here for testing</p>", "/p", "2026-01-01",
    ))
    assert td is not None


def test_bidi_and_zero_width_chars_are_safe():
    builder = InvertedIndexBuilder(Tokenizer(), Stemmer("en"))
    body = "<p>normal‮text‍with‌bidi and zero-width characters mixed in here</p>"
    td = builder.tokenize_item(ContentItem("x", "Title", body, "/p", "2026-01-01"))
    assert td is not None


def test_path_traversal_in_id_is_contained(tmp_path):
    # A malicious id must not let any output file escape the fragment directory
    # (fragments are hash-named, not id-named).
    items = [ContentItem("../../etc/passwd", "Pwned",
                         "<p>Body content sufficiently long for indexing here.</p>",
                         "/safe-url", "2026-01-01")]
    out = _build_vocab(items, tmp_path)
    frag_dir = Path(out) / "pagefind" / "fragment"
    files = glob.glob(str(frag_dir / "*"))
    assert files
    for f in files:
        # Every fragment resolves inside the fragment directory.
        assert Path(f).resolve().parent == frag_dir.resolve()


# -- endpoint validation ------------------------------------------------------


def test_empty_query_rejected():
    assert _handler().handle_expand_query("")["status"] == 400


def test_whitespace_only_query_rejected():
    assert _handler().handle_expand_query("   ")["status"] == 400


def test_extremely_long_query_rejected():
    assert _handler().handle_expand_query("a" * 5000)["status"] == 400


def test_follow_up_refused_when_max_is_zero():
    msgs = [{"role": "user", "content": "q"}, {"role": "assistant", "content": "a"},
            {"role": "user", "content": "f"}]
    assert _handler(max_follow_ups=0).handle_follow_up(msgs)["status"] == 429


def test_follow_up_refused_when_history_exceeds_limit():
    msgs = [{"role": "user", "content": "q"}, {"role": "assistant", "content": "a"}] * 5
    msgs.append({"role": "user", "content": "too many"})
    assert _handler(max_follow_ups=2).handle_follow_up(msgs)["status"] == 429


# -- AI error handling (OpenAI branch + degenerate responses) -----------------


def _oai_client(handler):
    return AiClient({"provider": "openai", "api_key": "k", "base_url": "https://gw/v1/chat/completions"},
                    http_client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_openai_rate_limit_is_ratelimit_exception():
    c = _oai_client(lambda r: httpx.Response(429, json={}))
    with pytest.raises(RateLimitException):
        c.message("s", "u")


def test_openai_invalid_key():
    c = _oai_client(lambda r: httpx.Response(401, json={}))
    with pytest.raises(ApiKeyInvalidException):
        c.message("s", "u")


def test_openai_server_error_is_runtime_error():
    c = _oai_client(lambda r: httpx.Response(500, json={}))
    with pytest.raises(RuntimeError):
        c.message("s", "u")


def test_openai_empty_choices_returns_empty_string():
    c = _oai_client(lambda r: httpx.Response(200, json={"choices": []}))
    assert c.message("s", "u") == ""


def test_openai_missing_choices_returns_empty_string():
    c = _oai_client(lambda r: httpx.Response(200, json={}))
    assert c.message("s", "u") == ""


def test_truncated_json_raises_runtime_error():
    c = _oai_client(lambda r: httpx.Response(200, content=b'{"choices": ['))
    with pytest.raises(RuntimeError, match="malformed JSON"):
        c.message("s", "u")


def test_indexer_handles_pathological_corpus(tmp_path):
    # End-to-end: a corpus mixing XSS, huge body, null bytes, and bidi builds
    # a valid index without crashing.
    items = [
        ContentItem("1", "<script>x</script>Recipe", "<p>" + "word " * 2000 + "</p>", "/a", "2026-01-01"),
        ContentItem("2", "Null\x00Title", "<p>body with \x00 null and ‮ bidi text here padded out</p>", "/b", "2026-01-01"),
    ]
    idx = PythonIndexer(str(tmp_path / "s"), str(tmp_path / "o"))
    idx.process_chunk(items, 0, total_pages=2)
    result = idx.finalize()
    assert result.success is True
    assert result.page_count == 2
