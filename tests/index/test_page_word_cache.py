"""Phase 7 — token cache efficiency (the "maintain the index" proof).

The PageWordCache lives in its own cache subdir, so a fresh-build cleanup never
evicts it. These tests prove: a no-change rebuild re-tokenizes zero pages, a
one-page edit re-tokenizes exactly one, and a deleted page leaves the index.
Plus PageWordCache unit behaviour.
"""

import glob
import re
import sys
from pathlib import Path

from scolta.content import ContentItem
from scolta.index.build_intent import BuildIntent
from scolta.index.memory_budget import MemoryBudget
from scolta.index.orchestrator import IndexBuildOrchestrator
from scolta.index.page_word_cache import PageWordCache
from scolta.index.token import Token
from scolta.storage import FilesystemDriver

sys.path.insert(0, str(Path(__file__).parent.parent / "support"))

_FIX = Path(__file__).parent.parent / "fixtures"


def _items():
    out = []
    for i, p in enumerate(sorted(glob.glob(str(_FIX / "recipes" / "*.html")))):
        h = Path(p).read_text(encoding="utf-8")
        out.append(ContentItem(
            str(i + 1), re.search(r"<title>(.*?)</title>", h, re.S).group(1),
            h, re.search(r'data-pagefind-meta="url:([^"]*)"', h).group(1),
            "2024-01-01", "Recipes", "en",
        ))
    return out


def _build(sd, od, items, probe_calls):
    orch = IndexBuildOrchestrator(sd, od)
    original = orch.builder.tokenize_item

    def counting(item):
        probe_calls.append(item.id)
        return original(item)

    orch.builder.tokenize_item = counting
    orch.build(BuildIntent.fresh(len(items), MemoryBudget.default()), items)


def _urls(od):
    urls = set()
    for f in glob.glob(od + "/pagefind/fragment/*.pf_fragment"):
        import gzip
        import json
        raw = gzip.decompress(Path(f).read_bytes())
        if raw.startswith(b"pagefind_dcd"):
            raw = raw[12:]
        urls.add(json.loads(raw.decode("utf-8"))["url"])
    return urls


def test_no_change_rebuild_retokenizes_zero(tmp_path):
    sd, od = str(tmp_path / "s"), str(tmp_path / "o")
    items = _items()

    first = []
    _build(sd, od, items, first)
    assert len(first) == 20  # cold cache: all tokenized

    second = []
    _build(sd, od, items, second)
    assert second == []  # warm cache: zero re-tokenizations


def test_one_page_edit_retokenizes_one(tmp_path):
    sd, od = str(tmp_path / "s"), str(tmp_path / "o")
    items = _items()
    _build(sd, od, items, [])

    # Edit exactly one page's body (changes its content hash).
    edited = list(items)
    edited[7] = edited[7].clone_with(body_html=edited[7].body_html + "<p>newly added paragraph text</p>")

    calls = []
    _build(sd, od, edited, calls)
    assert calls == [edited[7].id]  # only the edited page re-tokenized


def test_deleted_page_absent_from_index(tmp_path):
    sd, od = str(tmp_path / "s"), str(tmp_path / "o")
    items = _items()
    _build(sd, od, items, [])
    removed_url = items[3].url

    remaining = [it for it in items if it.id != items[3].id]
    _build(sd, od, remaining, [])

    urls = _urls(od)
    assert removed_url not in urls
    assert len(urls) == 19


# -- PageWordCache unit behaviour --------------------------------------------


def _td(content="hello world content"):
    return {
        "titleTokens": [Token("title", "title", 0)],
        "bodyTokens": [Token("hello", "hello", 1), Token("world", "world", 2)],
        "urlTokens": [],
        "wordCount": 3,
        "cleanTitle": "Title",
        "content": content,
    }


def test_cache_put_get_round_trip(tmp_path):
    cache = PageWordCache(str(tmp_path / "c"), FilesystemDriver())
    cache.put("h1", _td())
    got = cache.get("h1")
    assert got["content"] == "hello world content"
    assert [t.stem for t in got["bodyTokens"]] == ["hello", "world"]


def test_cache_survives_reopen(tmp_path):
    cdir = str(tmp_path / "c")
    cache = PageWordCache(cdir, FilesystemDriver())
    cache.put("h1", _td())
    cache.prune_and_save()
    reopened = PageWordCache(cdir, FilesystemDriver())
    assert reopened.get("h1") is not None


def test_cache_prune_drops_unseen(tmp_path):
    cdir = str(tmp_path / "c")
    c1 = PageWordCache(cdir, FilesystemDriver())
    c1.put("keep", _td())
    c1.put("drop", _td())
    c1.prune_and_save()
    # New build: only touch "keep".
    c2 = PageWordCache(cdir, FilesystemDriver())
    assert c2.get("keep") is not None
    c2.prune_and_save()  # "drop" was never get/put this round -> pruned
    c3 = PageWordCache(cdir, FilesystemDriver())
    assert c3.get("keep") is not None
    assert c3.get("drop") is None


def test_cache_flush_at_chunk_size(tmp_path):
    cdir = str(tmp_path / "c")
    cache = PageWordCache(cdir, FilesystemDriver(), chunk_size=2)
    for i in range(5):
        cache.put(f"h{i}", _td())
    cache.prune_and_save()
    reopened = PageWordCache(cdir, FilesystemDriver())
    for i in range(5):
        assert reopened.get(f"h{i}") is not None
