"""Parity Gate #3 — CBOR / format-writer (the byte/structural heart).

Two complementary proofs against the real scolta-php writers (golden in
tests/fixtures/index_parity.json, regenerable via parity/index_harness.php):

1. Controlled alphabetic-only corpus -> BYTE-EXACT: every output file's
   uncompressed payload (fragment JSON, pf_index/filter/meta CBOR) matches PHP
   byte-for-byte, proving CBOR canonical encoding, delta + weight markers,
   hashing/filenames, and chunking.
2. Recipe corpus -> STRUCTURAL: decoded word postings, fragments, filters and
   pf_meta (version/pages/sorts/meta_fields) match. Word *order* / chunk
   partitioning is a documented tolerance because PHP sort() (SORT_REGULAR) is
   non-transitive on numeric tokens; the Python writer uses canonical
   lexicographic order. Per-word postings are identical regardless.
"""

import glob
import gzip
import json
import re
import sys
from pathlib import Path

from scolta.content import ContentItem
from scolta.index.format_writer import PagefindFormatWriter
from scolta.index.inverted_index_builder import InvertedIndexBuilder
from scolta.index.stemmer import Stemmer
from scolta.index.streaming_format_writer import StreamingFormatWriter
from scolta.index.tokenizer import Tokenizer

sys.path.insert(0, str(Path(__file__).parent.parent / "support"))
import cbor_decoder

_FIX = Path(__file__).parent.parent / "fixtures"
_GOLDEN = json.loads((_FIX / "index_parity.json").read_text(encoding="utf-8"))


def _recipe_items():
    items = []
    for i, p in enumerate(sorted(glob.glob(str(_FIX / "recipes" / "*.html")))):
        html = Path(p).read_text(encoding="utf-8")
        title = re.search(r"<title>(.*?)</title>", html, re.S).group(1)
        url = re.search(r'data-pagefind-meta="url:([^"]*)"', html).group(1)
        items.append(ContentItem(str(i + 1), title, html, url, "2024-01-01", "Recipes", "en"))
    return items


def _decode_structure(build_dir: str) -> dict:
    bd = Path(build_dir)
    words = {}
    for f in glob.glob(str(bd / "index" / "*.pf_index")):
        chunk = cbor_decoder.decode_pf_file(f)
        for word, pages, variants in chunk[0]:
            words[word] = {"pages": pages, "variants": variants}
    words = dict(sorted(words.items()))

    fragments = {}
    for f in glob.glob(str(bd / "fragment" / "*.pf_fragment")):
        raw = gzip.decompress(Path(f).read_bytes())
        if raw.startswith(b"pagefind_dcd"):
            raw = raw[12:]
        j = json.loads(raw.decode("utf-8"))
        fragments[j["url"]] = j
    fragments = dict(sorted(fragments.items()))

    filters = {}
    for f in glob.glob(str(bd / "filter" / "*.pf_filter")):
        d = cbor_decoder.decode_pf_file(f)
        vals = {}
        for value, pages in d[1]:
            vals[value] = sorted(pages)
        filters[d[0]] = dict(sorted(vals.items()))
    filters = dict(sorted(filters.items()))

    meta_file = glob.glob(str(bd / "pagefind.*.pf_meta"))[0]
    meta = cbor_decoder.decode_pf_file(meta_file)
    sorts = dict(meta[4])
    meta_out = {
        "version": meta[0],
        "pages": meta[1],
        "sorts": sorts,
        "metaFields": meta[5],
        "pageCount": len(meta[1]),
        "chunkCount": len(meta[2]),
    }
    entry = json.loads((bd / "pagefind-entry.json").read_text(encoding="utf-8"))
    return {
        "words": words,
        "fragments": fragments,
        "filters": filters,
        "meta": meta_out,
        "entry": entry,
    }


def _load_php_index():
    """Rebuild the PHP-built {index, pages} from golden.

    PHP json_encode renders contiguous-int-keyed arrays as JSON arrays and
    sparse/string-keyed arrays as objects, so entries arrive as either list or
    dict; normalize both back to the builder's dict shape.
    """
    raw = _GOLDEN["php_built"]

    def conv_entry(v):
        pos = v["positions"]
        pos = {} if isinstance(pos, list) else {int(w): [int(x) for x in p] for w, p in pos.items()}
        return {"positions": pos, "meta_positions": [int(x) for x in v["meta_positions"]]}

    index = {}
    for word, entries in raw["index"].items():
        ni = {}
        if isinstance(entries, list):
            for pn, v in enumerate(entries):
                ni[pn] = conv_entry(v)
        else:
            for k, v in entries.items():
                if k == "_variants":
                    ni["_variants"] = {orig: [int(p) for p in pages] for orig, pages in v.items()}
                else:
                    ni[int(k)] = conv_entry(v)
        index[word] = ni

    raw_pages = raw["pages"]
    page_items = (
        enumerate(raw_pages)
        if isinstance(raw_pages, list)
        else ((int(k), v) for k, v in raw_pages.items())
    )
    pages = {}
    for pn, page in page_items:
        for key in ("filters", "meta", "sortable"):
            if isinstance(page.get(key), list):
                page[key] = {}
        pages[pn] = page
    return index, pages


# -- Recipe corpus: writer-isolation structural parity ------------------------
# Feed the Python writers the IDENTICAL PHP-built index so any difference is the
# writer's (the stemmer divergence is asserted separately below).


def test_recipe_streaming_writer_parity(tmp_path):
    index, pages = _load_php_index()
    out = str(tmp_path / "s")
    w = StreamingFormatWriter()
    w.begin_write(out)
    for pn in sorted(pages):
        w.write_page(pn, pages[pn])
    for term in sorted(index):
        w.write_term(term, index[term])
    w.end_write()
    _assert_structure(_decode_structure(out + "/.scolta-building"), _GOLDEN["recipes_streaming"])


def test_recipe_buffered_writer_parity(tmp_path):
    index, pages = _load_php_index()
    out = str(tmp_path / "b")
    PagefindFormatWriter().write(index, dict(pages), out)
    _assert_structure(_decode_structure(out + "/.scolta-building"), _GOLDEN["recipes_buffered"])


def _assert_structure(got, golden):
    assert set(got["words"].keys()) == set(golden["words"].keys())
    for term in golden["words"]:
        assert got["words"][term] == golden["words"][term], f"posting mismatch for {term!r}"
    assert got["fragments"] == golden["fragments"]
    assert got["filters"] == golden["filters"]
    assert got["meta"]["version"] == golden["meta"]["version"]
    assert got["meta"]["metaFields"] == golden["meta"]["metaFields"]
    assert got["meta"]["sorts"] == golden["meta"]["sorts"]
    assert got["meta"]["pageCount"] == golden["meta"]["pageCount"]
    assert got["meta"]["pages"] == golden["meta"]["pages"]


def test_recipe_stemmer_divergence_is_documented():
    """The Python (snowballstemmer) recipe vocabulary matches PHP (wamania)
    EXCEPT for words where wamania diverges from canonical Snowball. Python
    follows the canonical reference corpus (Phase 4, 0/177k) and rust-stemmers
    (the shared WASM), so Python is the correct side here:
        adding -> add  (wamania: ad)
        paste  -> paste (wamania: past); pasted -> paste (wamania: past)
    """
    golden_vocab = set(_GOLDEN["recipes_streaming"]["words"].keys())
    built = InvertedIndexBuilder(Tokenizer(), Stemmer("en")).build(_recipe_items())
    py_vocab = set(built["index"].keys())

    assert py_vocab - golden_vocab == {"paste"}
    assert golden_vocab - py_vocab == {"ad", "past"}
    st = Stemmer("en")
    assert st.stem("adding") == "add"
    assert st.stem("paste") == "paste"
    assert st.stem("pasted") == "paste"


# -- Controlled corpus: byte-exact parity -------------------------------------


def test_controlled_byte_parity(tmp_path):
    golden = _GOLDEN["controlled_streaming"]
    items = [
        ContentItem(
            i["id"],
            i["title"],
            i["body_html"],
            i["url"],
            i["date"],
            i["site_name"],
            i["language"],
            i["filters"],
            i["metadata"],
            i["sortable"],
        )
        for i in golden["items"]
    ]
    built = InvertedIndexBuilder(Tokenizer(), Stemmer("en")).build(items)
    out = str(tmp_path / "c")
    w = StreamingFormatWriter()
    w.begin_write(out)
    for pn in sorted(built["pages"]):
        w.write_page(pn, built["pages"][pn])
    for term in sorted(built["index"]):
        w.write_term(term, built["index"][term])
    w.end_write()

    bd = Path(out) / ".scolta-building"
    asset_files = {"pagefind.js", "pagefind-worker.js", "wasm.en.pagefind", "wasm.unknown.pagefind"}
    payloads = {}
    for f in bd.rglob("*"):
        if not f.is_file() or f.name in asset_files or f.name == "pagefind-entry.json":
            continue
        raw = gzip.decompress(f.read_bytes())
        if raw.startswith(b"pagefind_dcd"):
            raw = raw[12:]
        payloads[str(f.relative_to(bd))] = raw.hex()

    assert payloads == golden["payloads"]
    entry = json.loads((bd / "pagefind-entry.json").read_text(encoding="utf-8"))
    assert entry == golden["entry"]
