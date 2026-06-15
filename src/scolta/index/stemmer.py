"""Snowball stemmer (port of ``Tag1\\Scolta\\Index\\Stemmer``).

Stems words for 14 languages. The build-time stems must match what Pagefind
stems *queries* with at runtime, or an index silently misses those queries.
Pagefind 1.5.0's bundled WASM is the crate ``pagefind_stem`` 1.0.0 (published
2026-03-23, after the Snowball 3.0 / 2024 revision), so it emits the *modern*
Porter2 stems — ``added``→``add``, ``organic``→``organic``,
``geologist``→``geolog``, ``organize``→``organiz``, ``evening``→``evening``.

The stemmers are **vendored** from the Snowball compiler at the exact mainline
commit ``pagefind_stem`` 1.0.0 was generated from (see
``snowball/PROVENANCE.md``), not taken from the ``snowballstemmer`` PyPI
package. No published ``snowballstemmer`` release reproduces that crate
byte-for-byte across all 14 languages: the 3.0.x line predates the
``english.sbl`` fixes the crate has (18 English divergences), and the 3.1.x
line postdates apostrophe/elision changes the crate does not have (2,103
divergences across da/fi/it/no). The vendored backend matches ``pagefind_stem``
1.0.0 byte-for-byte over the full 14-language corpus (589,069 words, 0
divergences); the stemmer parity tests guard it. Unsupported languages return
words unchanged.
"""

from __future__ import annotations

from .snowball.catalan_stemmer import CatalanStemmer
from .snowball.danish_stemmer import DanishStemmer
from .snowball.dutch_stemmer import DutchStemmer
from .snowball.english_stemmer import EnglishStemmer
from .snowball.finnish_stemmer import FinnishStemmer
from .snowball.french_stemmer import FrenchStemmer
from .snowball.german_stemmer import GermanStemmer
from .snowball.italian_stemmer import ItalianStemmer
from .snowball.norwegian_stemmer import NorwegianStemmer
from .snowball.portuguese_stemmer import PortugueseStemmer
from .snowball.romanian_stemmer import RomanianStemmer
from .snowball.russian_stemmer import RussianStemmer
from .snowball.spanish_stemmer import SpanishStemmer
from .snowball.swedish_stemmer import SwedishStemmer

# Language code -> vendored Snowball stemmer class. The set mirrors Pagefind
# 1.5.0's own code->algorithm feature map; in particular ``nl`` is the modern
# ``dutch`` algorithm, not ``dutch_porter``.
_LANGUAGE_MAP = {
    "ca": CatalanStemmer,
    "da": DanishStemmer,
    "de": GermanStemmer,
    "en": EnglishStemmer,
    "es": SpanishStemmer,
    "fi": FinnishStemmer,
    "fr": FrenchStemmer,
    "it": ItalianStemmer,
    "nl": DutchStemmer,
    "no": NorwegianStemmer,
    "pt": PortugueseStemmer,
    "ro": RomanianStemmer,
    "ru": RussianStemmer,
    "sv": SwedishStemmer,
}

_CACHE_MAX_ENTRIES = 100_000


class Stemmer:
    def __init__(self, language: str = "en") -> None:
        cls = _LANGUAGE_MAP.get(language)
        self._stemmer = cls() if cls is not None else None
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
