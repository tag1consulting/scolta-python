"""Snowball stemmer (port of ``Tag1\\Scolta\\Index\\Stemmer``).

Wraps ``snowballstemmer`` for 14 languages. The build-time stems must match what
Pagefind stems *queries* with at runtime, or an index silently misses those
queries. Pagefind 1.5.0's bundled WASM is the crate ``pagefind_stem`` 1.0.0
(published 2026-03-23, after the Snowball 3.0 / 2024 revision), so it emits the
*modern* Porter2 stems — ``added``→``add``, ``organic``→``organic``,
``geologist``→``geolog``, ``organize``→``organiz``, ``evening``→``evening``.

``snowballstemmer>=3`` reproduces that crate's output byte-for-byte across the
full stemmer corpus (177,500 words, en/fr/de/es/ru; verified against a golden
generated from ``pagefind_stem`` 1.0.0 itself — see
``tests/fixtures/stemmer-corpus/PROVENANCE.md``). The pre-3.0 ``snowballstemmer``
2.x line implements the *old* algorithm (``added``→``ad`` …) and diverges from
Pagefind 1.5.0 on dozens-to-thousands of words per language, which is why the
dependency floor is ``>=3``. Unsupported languages return words unchanged.
"""

from __future__ import annotations

import snowballstemmer

# Language code -> snowballstemmer algorithm name.
_LANGUAGE_MAP = {
    "ca": "catalan",
    "da": "danish",
    "de": "german",
    "en": "english",
    "es": "spanish",
    "fi": "finnish",
    "fr": "french",
    "it": "italian",
    "nl": "dutch",
    "no": "norwegian",
    "pt": "portuguese",
    "ro": "romanian",
    "ru": "russian",
    "sv": "swedish",
}

_CACHE_MAX_ENTRIES = 100_000


class Stemmer:
    def __init__(self, language: str = "en") -> None:
        algo = _LANGUAGE_MAP.get(language)
        self._stemmer = snowballstemmer.stemmer(algo) if algo is not None else None
        self._cache: dict[str, str] = {}

    def stem(self, word: str) -> str:
        """Stem a word to its root form (unchanged for unsupported languages)."""
        cached = self._cache.get(word)
        if cached is not None:
            return cached

        result = word if self._stemmer is None else self._stemmer.stemWord(word)

        if len(self._cache) < _CACHE_MAX_ENTRIES:
            self._cache[word] = result

        return result

    @staticmethod
    def get_supported_languages() -> list[str]:
        return list(_LANGUAGE_MAP.keys())
