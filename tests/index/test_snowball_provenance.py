"""Vendored Snowball backend drift guard.

The Python stemmers in ``src/scolta/index/snowball/`` are generated code pinned
to the exact snowball revision ``pagefind_stem`` 1.0.0 was generated from (see
``src/scolta/index/snowball/PROVENANCE.md``). This test pins every vendored file
to the sha256 manifest recorded there, so a silent regeneration — wrong snowball
revision, stray hand edit — fails CI until the manifest is consciously
re-baselined in the same commit. The corpus parity test proves the code behaves
like Pagefind; this one proves the code itself has not moved without a paper
trail. It is the cheap counterpart that catches edits the parity corpus might
not exercise.
"""

import hashlib
import re
from pathlib import Path

import pytest

_SNOWBALL = Path(__file__).parent.parent.parent / "src" / "scolta" / "index" / "snowball"
_PROVENANCE = _SNOWBALL / "PROVENANCE.md"


def _manifest() -> dict[str, str]:
    """Parse the ``| file | sha256 |`` rows from PROVENANCE.md."""
    rows: dict[str, str] = {}
    for line in _PROVENANCE.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\|\s*([A-Za-z0-9_]+\.py|LICENSE)\s*\|\s*`([0-9a-f]{64})`\s*\|", line)
        if m:
            rows[m.group(1)] = m.group(2)
    return rows


def _vendored_files() -> list[str]:
    return sorted(p.name for p in [*_SNOWBALL.glob("*.py"), *_SNOWBALL.glob("LICENSE")])


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_manifest_covers_every_vendored_file():
    manifest = _manifest()
    assert manifest, "no sha256 manifest rows found in src/scolta/index/snowball/PROVENANCE.md"
    assert sorted(manifest) == _vendored_files(), (
        "src/scolta/index/snowball contents must match the PROVENANCE.md manifest exactly"
    )


@pytest.mark.parametrize("name", _vendored_files())
def test_vendored_file_hashes_match_provenance(name):
    expected = _manifest().get(name)
    assert expected is not None, f"no manifest row for {name} in PROVENANCE.md"
    assert _sha256(_SNOWBALL / name) == expected, (
        f"{name} changed without re-baselining src/scolta/index/snowball/PROVENANCE.md — "
        "vendored stemmers must only change via scripts/generate-stemmers.sh"
    )
