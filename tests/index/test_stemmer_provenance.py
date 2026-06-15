"""Stemmer corpus drift guard.

The stemmer corpus is the Pagefind query-stemmer oracle (generated from
``pagefind_stem`` — see ``tests/fixtures/stemmer-corpus/PROVENANCE.md``). This
test pins the fixtures to the sha256 manifest recorded in PROVENANCE.md, so a
silent re-baseline (e.g. regenerating against a different Pagefind stemmer
revision) fails CI until the manifest and the targeted-version table are updated
in the same commit. It is the cheap counterpart to the full-corpus parity test:
that one proves *the binding* still matches the oracle; this one proves *the
oracle fixtures themselves* have not moved without a paper trail.
"""

import hashlib
import re
from pathlib import Path

import pytest

_CORPUS = Path(__file__).parent.parent / "fixtures" / "stemmer-corpus"
_PROVENANCE = _CORPUS / "PROVENANCE.md"
_LANGS = ["ca", "da", "de", "en", "es", "fi", "fr", "it", "nl", "no", "pt", "ro", "ru", "sv"]


def _manifest() -> dict[str, dict[str, str]]:
    """Parse the sha256 table rows ``| lang | words | stems |`` from PROVENANCE.md."""
    rows: dict[str, dict[str, str]] = {}
    langs = "|".join(_LANGS)
    for line in _PROVENANCE.read_text(encoding="utf-8").splitlines():
        m = re.match(
            rf"\|\s*({langs})\s*\|\s*`([0-9a-f]{{64}})`\s*\|\s*`([0-9a-f]{{64}})`\s*\|",
            line,
        )
        if m:
            rows[m.group(1)] = {"words": m.group(2), "stems": m.group(3)}
    return rows


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_manifest_lists_every_language():
    assert set(_manifest()) == set(_LANGS)


@pytest.mark.parametrize("lang", _LANGS)
def test_fixture_hashes_match_provenance(lang):
    expected = _manifest()[lang]
    assert _sha256(_CORPUS / lang / "words.txt") == expected["words"], (
        f"{lang}/words.txt changed without updating PROVENANCE.md"
    )
    assert _sha256(_CORPUS / lang / "expected-stems.txt") == expected["stems"], (
        f"{lang}/expected-stems.txt changed without updating PROVENANCE.md — "
        "if you re-targeted a new Pagefind stemmer, update the version table too"
    )
