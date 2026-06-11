"""Tokenize text for search indexing.

Faithful port of ``Tag1\\Scolta\\Index\\Tokenizer``, which replicates
Pagefind's ``pagefind/src/fossick/splitting.rs``: Unicode-aware lowercasing,
diacritic normalization (NFD strip marks NFC), word-boundary splitting,
compound handling (hyphens, camelCase), and CJK character (bigram) splitting.

Python differences from the PHP source that do NOT affect output:
- The PHP byte/char offset bookkeeping and the ``textIsAscii`` fast-path are
  pure performance optimizations for PHP's byte strings. Python strings are
  sequences of code points, so the ``regex`` match offsets are already
  character offsets — the elaborate tracking is unnecessary and omitted; the
  emitted positions are identical.
- Diacritic normalization uses ``unicodedata`` (NFD -> strip Mn -> NFC), which
  matches PHP's ICU transliterator ``"NFD; [:Nonspacing Mark:] Remove; NFC"``
  (the PHP ext-intl path; the env's PHP has intl, so that is the reference).
"""

from __future__ import annotations

import re
import unicodedata

import regex

from .token import Token

# Word boundary: runs of letters/numbers/emoji, plus internal apostrophe
# contractions (don't, it's). Identical to the PHP PCRE /u pattern.
_WORD = regex.compile(r"[\p{L}\p{N}\p{Emoji_Presentation}]+(?:'[\p{L}]+)*")

# CJK / Hiragana / Katakana / Hangul ranges (same set as the PHP pattern).
_CJK = re.compile("[一-鿿㐀-䶿豈-﫿぀-ゟ゠-ヿ가-힯]")  # noqa: RUF001 - literal CJK ranges, PHP-pattern parity
_CAMEL_DETECT = re.compile("[a-z][A-Z]")
_CAMEL_SPLIT = re.compile("(?<=[a-z])(?=[A-Z])")

_PHP_TRIM = " \t\n\r\x00\x0b"


class Tokenizer:
    def tokenize(self, text: str, start_position: int = 0) -> list[Token]:
        """Tokenize text into a list of Token records."""
        if text.strip(_PHP_TRIM) == "":
            return []

        tokens: list[Token] = []
        lower_cache: dict[str, str] = {}
        normalize_cache: dict[str, str] = {}

        for m in _WORD.finditer(text):
            word = m.group()
            position = start_position + m.start()

            for part_offset, part in self._split_compound(word).items():
                if part == "":
                    continue
                lower = lower_cache.get(part)
                if lower is None:
                    lower = part.lower()
                    lower_cache[part] = lower
                normalized = normalize_cache.get(lower)
                if normalized is None:
                    normalized = self._normalize(lower)
                    normalize_cache[lower] = normalized
                if normalized == "":
                    continue
                tokens.append(Token(normalized, lower, position + part_offset))

        return tokens

    @staticmethod
    def _normalize(text: str) -> str:
        """Strip diacritics via NFD -> remove nonspacing marks -> NFC."""
        nfd = unicodedata.normalize("NFD", text)
        stripped = "".join(c for c in nfd if unicodedata.category(c) != "Mn")
        return unicodedata.normalize("NFC", stripped)

    def _split_compound(self, word: str) -> dict[int, str]:
        """Split compound words (hyphens, camelCase) and CJK into parts.

        Returns an ordered mapping of char offset -> part."""
        if _CJK.search(word):
            return self._tokenize_mixed_cjk(word)

        # Hyphen: "mother-in-law" -> mother, in, law, motherinlaw (parts + join).
        if "-" in word:
            parts: dict[int, str] = {}
            offset = 0
            for segment in word.split("-"):
                seg_len = len(segment)
                if seg_len >= 2:
                    parts[offset] = segment
                offset += seg_len + 1
            compound = word.replace("-", "")
            if len(compound) >= 3 and len(parts) > 1:
                parts[len(word) + 1] = compound
            return parts if parts else {0: word}

        # camelCase: "myPageTitle" -> my, page, title (lowercased here).
        if _CAMEL_DETECT.search(word):
            segments = _CAMEL_SPLIT.split(word)
            if len(segments) > 1:
                parts = {}
                offset = 0
                for segment in segments:
                    lower = segment.lower()
                    if len(lower) >= 2:
                        parts[offset] = lower
                    offset += len(segment)
                return parts if parts else {0: word}

        return {0: word}

    @staticmethod
    def _tokenize_mixed_cjk(word: str) -> dict[int, str]:
        """Bigram-tokenize a word with CJK characters.

        Non-CJK runs emit one token; CJK runs of length >= 2 emit overlapping
        bigrams; a single CJK character is emitted as-is."""
        chars = list(word)
        parts: dict[int, str] = {}

        def flush(start_offset: int, run_chars: list[str], is_cjk: bool) -> None:
            count = len(run_chars)
            if count == 0:
                return
            if not is_cjk:
                parts[start_offset] = "".join(run_chars)
            elif count == 1:
                parts[start_offset] = run_chars[0]
            else:
                for i in range(count - 1):
                    parts[start_offset + i] = run_chars[i] + run_chars[i + 1]

        run_start = 0
        run_chars: list[str] = []
        run_is_cjk: bool | None = None

        for i, char in enumerate(chars):
            is_cjk = _CJK.search(char) is not None
            if run_is_cjk is None:
                run_is_cjk = is_cjk
                run_start = i
            if is_cjk != run_is_cjk:
                flush(run_start, run_chars, run_is_cjk)
                run_start = i
                run_chars = []
                run_is_cjk = is_cjk
            run_chars.append(char)

        flush(run_start, run_chars, run_is_cjk if run_is_cjk is not None else False)
        return parts
