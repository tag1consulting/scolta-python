"""Stemmer ⇄ Pagefind parity guard (modern Snowball).

Pagefind stems *queries* at runtime with its bundled WASM. For the Pagefind
version this project targets (1.5.0), that WASM is the crate ``pagefind_stem``
1.0.0 — published 2026-03-23, after the Snowball 3.0 / 2024 revision — so it
emits the *modern* Porter2 algorithm. A Python-built index is only searchable
if its build-time stems match those runtime query stems exactly.

The tells below were read straight out of a ``pagefind 1.5.0`` build (the
production binary stores ``added``→``add``, ``organic``→``organic``,
``geologist``→``geolog``, ``organize``→``organiz`` for these words) and are the
exact stems ``pagefind_stem`` 1.0.0 produces. They all DIFFER from the pre-3.0
``snowballstemmer`` 2.x output (``ad`` / ``organ`` / ``geologist`` / ``organ``),
so if the dependency floor is ever lowered below 3 this guard turns red rather
than silently shipping an index that misses those queries.
"""

from scolta.index.stemmer import Stemmer

# word -> modern (Snowball >=3.0 / pagefind_stem 1.0.0 / Pagefind 1.5.0) stem.
# Every pair differs from the old 2.x output, so a downgrade fails loudly.
_PAGEFIND_MODERN = {
    "added": "add",  # old 2.x: "ad"
    "adding": "add",  # old: "ad"
    "organic": "organic",  # old: "organ"
    "organically": "organic",  # old: "organ"
    "organize": "organiz",  # old: "organ"
    "organized": "organiz",  # old: "organ"
    "geologist": "geolog",  # old: "geologist"
    "geologists": "geolog",  # old: "geologist"
    "evening": "evening",  # old: "even"
    "lateral": "lateral",  # old: "later"
    "paste": "paste",  # old: "past"
    "pasted": "paste",  # old: "past"
    "universities": "universiti",  # old: "univers"
    "vying": "vie",  # old: "vy"
}

# Control words: identical under old and modern Porter2. They prove the stemmer
# is still doing real work (not just echoing the input) on the pinned version.
_CONTROL = {
    "running": "run",
    "fruitlessly": "fruitless",
    "generously": "generous",
    "national": "nation",
    "communism": "communism",
}


def test_pagefind_tells_use_modern_porter2():
    stemmer = Stemmer("en")
    mismatches = {
        word: stemmer.stem(word)
        for word, expected in _PAGEFIND_MODERN.items()
        if stemmer.stem(word) != expected
    }
    assert not mismatches, (
        "Stemmer drifted off the modern Porter2 Pagefind 1.5.0 uses — is "
        f"snowballstemmer>=3 still installed? Got: {mismatches}"
    )


def test_control_words_stem_identically_in_both_algorithms():
    stemmer = Stemmer("en")
    for word, expected in _CONTROL.items():
        assert stemmer.stem(word) == expected


def test_added_stems_to_add_not_ad():
    # The canonical tell: modern Porter2 -> 'add', old snowballstemmer 2.x -> 'ad'.
    assert Stemmer("en").stem("added") == "add"


def test_organic_stems_to_organic_not_organ():
    # Modern Porter2 leaves 'organic'; old 2.x reduces it to 'organ'.
    assert Stemmer("en").stem("organic") == "organic"
