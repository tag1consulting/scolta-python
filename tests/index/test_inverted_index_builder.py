"""InvertedIndexBuilder tests.

Ports tests/Index/PageNumberingTest.php behaviours (the string-key / UUID-key
cases are PHP-associative-array specific and N/A for Python lists; the
sequential / gap-free / page-offset / valid-index-range invariants are ported),
plus core builder behaviours and a lightweight posting-list semantic check
(the heavier PostingListValidityTest needs PhpIndexer and ports in Phase 6).
"""

import glob
import gzip
import json
import re
from pathlib import Path

import pytest

from scolta.content import ContentItem
from scolta.index.inverted_index_builder import InvertedIndexBuilder
from scolta.index.stemmer import Stemmer
from scolta.index.streaming_format_writer import StreamingFormatWriter
from scolta.index.tokenizer import Tokenizer


@pytest.fixture
def builder():
    return InvertedIndexBuilder(Tokenizer(), Stemmer("en"))


def _item(item_id, body=""):
    body = (
        body
        or f"This is a sufficient body text for item {item_id} to pass the minimum length check."
    )
    return ContentItem(
        item_id, f"Title for {item_id}", f"<p>{body}</p>", f"/{item_id}", "2024-01-01"
    )


# -- Page numbering -----------------------------------------------------------


def test_sequential_pages(builder):
    result = builder.build([_item("item-0"), _item("item-1"), _item("item-2")])
    assert sorted(result["pages"].keys()) == [0, 1, 2]


def test_skipped_items_do_not_gap_page_numbers(builder):
    items = [
        _item(
            "item-a", "This is a sufficient body text to pass the minimum character length check."
        ),
        ContentItem("item-skip", "Short", "<p>Too short</p>", "/skip", "2024-01-01"),
        _item(
            "item-c", "Another sufficient body text for item c that passes the length requirement."
        ),
    ]
    result = builder.build(items)
    assert sorted(result["pages"].keys()) == [0, 1]
    assert len(result["pages"]) == 2


def test_word_entry_page_references_are_valid_indices(builder):
    items = [
        _item("x", "The quick brown fox searches for information online quickly."),
        _item("y", "The search engine processes all the searching queries carefully."),
        _item("z", "No matching words here, completely unrelated content about databases."),
    ]
    result = builder.build(items)
    valid = set(range(len(result["pages"])))
    for word, entries in result["index"].items():
        for page_num in entries:
            if page_num == "_variants":
                continue
            assert page_num in valid, f"word {word!r} references invalid page {page_num}"


def test_page_offset_produces_globally_unique_numbers(builder):
    c0 = builder.build(
        [
            _item(
                "c0-a", "First chunk first item with adequate body text for indexing purposes here."
            ),
            _item(
                "c0-b",
                "First chunk second item with adequate body text for indexing purposes here.",
            ),
        ],
        0,
    )
    offset = len(c0["pages"])
    c1 = builder.build(
        [
            _item(
                "c1-a",
                "Second chunk first item with adequate body text for indexing purposes here.",
            ),
            _item(
                "c1-b",
                "Second chunk second item with adequate body text for indexing purposes here.",
            ),
        ],
        offset,
    )
    all_keys = list(c0["pages"].keys()) + list(c1["pages"].keys())
    assert len(all_keys) == len(set(all_keys))
    assert sorted(all_keys) == [0, 1, 2, 3]


# -- Builder behaviours -------------------------------------------------------


def test_tokenize_item_skips_short_content(builder):
    assert builder.tokenize_item(ContentItem("s", "T", "<p>hi</p>", "/s", "2024-01-01")) is None


def test_content_field_prefixes_title(builder):
    td = builder.tokenize_item(
        _item("a", "Body content here that is long enough to index properly.")
    )
    assert td["content"].startswith(td["cleanTitle"] + ". ")


def test_title_tokens_go_to_meta_positions(builder):
    # A word only in the title should have meta_positions but empty body positions.
    item = ContentItem("p", "Zucchini", "<p>" + "filler word " * 20 + "</p>", "/p", "2024-01-01")
    result = builder.build([item])
    stem = "zucchini"
    assert stem in result["index"]
    entry = result["index"][stem][0]
    assert entry["meta_positions"]  # title contributed a meta position
    assert entry["positions"] == {}  # not in body


def test_body_tokens_go_to_positions(builder):
    item = ContentItem("p", "Title", "<p>" + "cucumber " * 5 + "</p>", "/p", "2024-01-01")
    result = builder.build([item])
    entry = result["index"]["cucumb"][0]
    assert entry["positions"].get(InvertedIndexBuilder.BODY_WEIGHT)


def test_word_count_is_title_plus_body(builder):
    td = builder.tokenize_item(_item("a", "one two three four five six seven eight nine ten."))
    assert td["wordCount"] == len(td["titleTokens"]) + len(td["bodyTokens"])


# -- Lightweight posting-list semantic check ----------------------------------


def test_indexed_words_appear_in_referenced_fragments(tmp_path):
    """Every stemmed word in pf_index appears (re-stemmed) in the fragment it
    references — a lightweight PostingListValidityTest over the recipe corpus."""
    items = []
    for i, p in enumerate(
        sorted(glob.glob(str(Path(__file__).parent.parent / "fixtures" / "recipes" / "*.html")))
    ):
        html = Path(p).read_text(encoding="utf-8")
        title = re.search(r"<title>(.*?)</title>", html, re.S).group(1)
        url = re.search(r'data-pagefind-meta="url:([^"]*)"', html).group(1)
        items.append(ContentItem(str(i + 1), title, html, url, "2024-01-01", "Recipes", "en"))

    tok, stem = Tokenizer(), Stemmer("en")
    builder = InvertedIndexBuilder(tok, stem)
    built = builder.build(items)

    out = str(tmp_path / "idx")
    w = StreamingFormatWriter()
    w.begin_write(out)
    for pn in sorted(built["pages"]):
        w.write_page(pn, built["pages"][pn])
    for term in sorted(built["index"]):
        w.write_term(term, built["index"][term])
    w.end_write()

    bd = Path(out) / ".scolta-building"
    # Map fragment hash -> set of stems from content + title + url path.
    frag_stems = {}
    for f in glob.glob(str(bd / "fragment" / "*.pf_fragment")):
        raw = gzip.decompress(Path(f).read_bytes())
        if raw.startswith(b"pagefind_dcd"):
            raw = raw[12:]
        j = json.loads(raw.decode("utf-8"))
        text = j.get("content", "")
        title = j.get("meta", {}).get("title", "")
        url_path = re.sub(r"\.\w+$", "", j.get("url", ""))
        url_text = " ".join(s for s in url_path.split("/") if s)
        stems = set()
        for src in (text, title, url_text):
            for t in tok.tokenize(src):
                stems.add(stem.stem(t.stem))
        frag_stems[Path(f).stem] = stems

    # pf_meta pages[] gives the page_num -> fragment hash mapping.
    import sys

    sys.path.insert(0, str(Path(__file__).parent.parent / "support"))
    import cbor_decoder

    meta = cbor_decoder.decode_pf_file(glob.glob(str(bd / "pagefind.*.pf_meta"))[0])
    pages_meta = meta[1]  # [[fragmentHash, wordCount], ...]

    failures = []
    for f in glob.glob(str(bd / "index" / "*.pf_index")):
        chunk = cbor_decoder.decode_pf_file(f)
        for word, page_refs, _variants in chunk[0]:
            running = 0
            for ref in page_refs:
                running += ref[0]  # delta page num
                frag_hash = pages_meta[running][0]
                if word not in frag_stems.get(frag_hash, set()):
                    failures.append((word, running))
    assert not failures, (
        f"{len(failures)} indexed words not found in their fragments: {failures[:10]}"
    )
