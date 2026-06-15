"""Stemmer tests — Parity Gate #2 (stemmer half).

Ports tests/Index/StemmerTest.php (1:1) plus a full-corpus parity test: the
Python Stemmer must reproduce the Pagefind query-stemmer (`pagefind_stem` 1.0.0)
stems for every word in the stemmer corpus, byte-for-byte, across all 14
shipped languages — the same corpus scolta-php's StemmerConcordanceTest uses.
This is what makes a multilingual index searchable: the build-time stems must
match the stems Pagefind produces from queries at runtime.
"""

from pathlib import Path

import pytest

from scolta.index.stemmer import Stemmer

_CORPUS = Path(__file__).parent.parent / "fixtures" / "stemmer-corpus"
_LANGS = ["ca", "da", "de", "en", "es", "fi", "fr", "it", "nl", "no", "pt", "ro", "ru", "sv"]


# -- Full corpus parity (Python Stemmer == committed wamania stems) -----------


@pytest.mark.parametrize("lang", _LANGS)
def test_corpus_parity(lang):
    words = (_CORPUS / lang / "words.txt").read_text(encoding="utf-8").split("\n")
    expected = (_CORPUS / lang / "expected-stems.txt").read_text(encoding="utf-8").split("\n")
    assert len(words) == len(expected)
    stemmer = Stemmer(lang)
    mismatches = []
    for word, exp in zip(words, expected, strict=True):
        got = stemmer.stem(word)
        if got != exp:
            mismatches.append((word, exp, got))
    assert not mismatches, f"{lang}: {len(mismatches)} mismatches e.g. {mismatches[:8]}"


# -- StemmerTest.php (1:1) ----------------------------------------------------


def test_english_stem_running():
    assert Stemmer("en").stem("running") == "run"


def test_english_stem_walks():
    assert Stemmer("en").stem("walks") == "walk"


def test_english_stem_cats():
    assert Stemmer("en").stem("cats") == "cat"


def test_english_stem_computing():
    assert Stemmer("en").stem("computing") == "comput"


def test_unsupported_language_fallback():
    assert Stemmer("xx").stem("hello") == "hello"


def test_french_stemmer():
    result = Stemmer("fr").stem("maisons")
    assert isinstance(result, str)
    assert result


def test_german_stemmer():
    assert isinstance(Stemmer("de").stem("Häuser"), str)


def test_stem_idempotent():
    s = Stemmer("en")
    stemmed = s.stem("running")
    assert s.stem(stemmed) == stemmed


def test_catalan_stemmer():
    result = Stemmer("ca").stem("casals")
    assert isinstance(result, str)
    assert result


def test_unsupported_arabic_fallback():
    assert Stemmer("ar").stem("hello") == "hello"


def test_unsupported_polish_fallback():
    assert Stemmer("pl").stem("test") == "test"


def test_get_supported_languages():
    langs = Stemmer.get_supported_languages()
    assert "en" in langs
    assert "fr" in langs
    assert "ca" in langs
    assert len(langs) == 14


def test_stem_is_consistent_whether_cached_or_recomputed():
    s = Stemmer("en")
    for word in ("running", "cats", "computing", "walks", "testing", "indexing"):
        assert s.stem(word) == s.stem(word)
