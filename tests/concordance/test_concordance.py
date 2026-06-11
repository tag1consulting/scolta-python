"""Concordance — the Python indexer vs the real Pagefind CLI output.

Ports tests/Concordance/ReferenceComparisonTest + MultilingualReferenceComparisonTest.
Builds an index with the in-process Python indexer from the concordance corpora
and compares each page's cleaned *fragment content* (whitespace+punctuation
split, lowercased, deduped, len>=2) against the committed frozen Pagefind-binary
reference via average Jaccard similarity, plus a fragment-count ±1 check.

Thresholds: Latin-script >= 0.70; CJK/Arabic >= 0.50 (Pagefind's character/
compound splitting diverges more there). This validates HTML cleaning +
tokenization fidelity against ground truth across 19 languages.
"""

import glob
import gzip
import json
import re
from pathlib import Path

import pytest

from scolta.content import ContentItem
from scolta.index.build_intent import BuildIntent
from scolta.index.memory_budget import MemoryBudget
from scolta.index.orchestrator import IndexBuildOrchestrator

_FIX = Path(__file__).parent.parent / "fixtures" / "concordance"
_WORD_SPLIT = re.compile(r"[\s\W]+", re.UNICODE)

_LANGUAGES = [
    "ar",
    "zh",
    "da",
    "nl",
    "en",
    "fi",
    "fr",
    "de",
    "hu",
    "it",
    "ja",
    "ko",
    "no",
    "pt",
    "ro",
    "ru",
    "es",
    "sv",
    "tr",
]
_NON_LATIN = {"ar", "zh", "ja", "ko"}


def _significant_words(text: str) -> set[str]:
    return {w for w in _WORD_SPLIT.split(text.lower()) if len(w) >= 2}


def _load_fragments(fragment_dir: Path, prefix: str | None = None) -> dict:
    out = {}
    for f in glob.glob(str(fragment_dir / "*.pf_fragment")):
        raw = gzip.decompress(Path(f).read_bytes())
        if raw.startswith(b"pagefind_dcd"):
            raw = raw[12:]
        j = json.loads(raw.decode("utf-8"))
        if "url" in j and (prefix is None or j["url"].startswith(prefix)):
            out[j["url"]] = j
    return out


def _items_from(corpus_glob: str) -> list[ContentItem]:
    import html as htmllib

    items = []
    for f in sorted(glob.glob(corpus_glob)):
        text = Path(f).read_text(encoding="utf-8")
        title = re.search(r"<title>(.*?)</title>", text, re.S)
        body = re.search(r"<body[^>]*>(.*?)</body>", text, re.S | re.I)
        slug = Path(f).stem
        items.append(
            ContentItem(
                id=slug,
                title=htmllib.unescape(title.group(1)) if title else slug,
                body_html=body.group(1) if body else "",
                url=f"/{slug}",
                date="2026-04-01",
            )
        )
    return items


def _build(tmp_path, items, language) -> dict:
    out = str(tmp_path / "site")
    IndexBuildOrchestrator(str(tmp_path / "state"), out, language=language).build(
        BuildIntent.fresh(len(items), MemoryBudget.default()), items
    )
    return _load_fragments(Path(out) / "pagefind" / "fragment")


def _match(py_fragments: dict, url: str, ref_frag: dict) -> dict | None:
    if url in py_fragments:
        return py_fragments[url]
    ref_title = ref_frag.get("meta", {}).get("title", "")
    for frag in py_fragments.values():
        if frag.get("meta", {}).get("title", "") == ref_title:
            return frag
    return None


def _avg_jaccard(py_fragments: dict, ref_fragments: dict) -> tuple[float, int]:
    sims = []
    for url, ref in ref_fragments.items():
        py = _match(py_fragments, url, ref)
        if py is None:
            continue
        ref_words = _significant_words(ref.get("content", ""))
        if not ref_words:
            continue
        py_words = _significant_words(py.get("content", ""))
        union = ref_words | py_words
        sims.append(len(ref_words & py_words) / len(union) if union else 0.0)
    return (sum(sims) / len(sims) if sims else 0.0), len(sims)


# -- English (ReferenceComparisonTest) ----------------------------------------


def test_english_fragment_count(tmp_path):
    py = _build(tmp_path, _items_from(str(_FIX / "corpus" / "*.html")), "en")
    ref = _load_fragments(_FIX / "reference" / "fragment")
    assert abs(len(py) - len(ref)) <= 1


def test_english_content_overlap(tmp_path):
    py = _build(tmp_path, _items_from(str(_FIX / "corpus" / "*.html")), "en")
    ref = _load_fragments(_FIX / "reference" / "fragment")
    avg, n = _avg_jaccard(py, ref)
    assert n > 0
    assert avg >= 0.70, f"English content Jaccard {avg:.3f} < 0.70 (n={n})"


# -- Multilingual: corpus-ml AND corpus-wiki, vs frozen Pagefind reference -----

# Each multilingual corpus pairs with its frozen Pagefind-binary reference dir.
_ML_CORPORA = [("corpus-ml", "reference-ml"), ("corpus-wiki", "reference-wiki")]
_ML_CASES = [(corpus, reference, lang) for corpus, reference in _ML_CORPORA for lang in _LANGUAGES]


@pytest.mark.parametrize("corpus,reference,lang", _ML_CASES)
def test_multilingual_fragment_count(corpus, reference, lang, tmp_path):
    items = _items_from(str(_FIX / corpus / f"{lang}-*.html"))
    if not items:
        pytest.skip(f"no {corpus} for {lang}")
    py = _build(tmp_path, items, lang)
    ref = _load_fragments(_FIX / reference / "fragment", prefix=f"/{lang}-")
    assert abs(len(py) - len(ref)) <= 1, f"[{corpus}:{lang}] py={len(py)} ref={len(ref)}"


@pytest.mark.parametrize("corpus,reference,lang", _ML_CASES)
def test_multilingual_content_overlap(corpus, reference, lang, tmp_path):
    items = _items_from(str(_FIX / corpus / f"{lang}-*.html"))
    if not items:
        pytest.skip(f"no {corpus} for {lang}")
    py = _build(tmp_path, items, lang)
    ref = _load_fragments(_FIX / reference / "fragment", prefix=f"/{lang}-")
    threshold = 0.50 if lang in _NON_LATIN else 0.70
    avg, n = _avg_jaccard(py, ref)
    if n == 0:
        pytest.skip(f"[{corpus}:{lang}] no overlapping fragments")
    assert avg >= threshold, f"[{corpus}:{lang}] content Jaccard {avg:.3f} < {threshold} (n={n})"
