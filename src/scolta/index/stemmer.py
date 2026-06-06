"""Snowball stemmer (port of ``Tag1\\Scolta\\Index\\Stemmer``).

Wraps ``snowballstemmer`` for 14 languages. Verified to match the PHP binding's
``wamania/php-stemmer`` output exactly across the full stemmer corpus
(0 mismatches in 177,505 words over en/fr/de/es/ru — both are ports of the same
canonical Snowball algorithms). Unsupported languages return words unchanged.
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
