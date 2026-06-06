"""Config-reference drift guard (port of tests/Documentation/ConfigReferenceDocTest.php).

Asserts docs/CONFIG_REFERENCE.md never silently diverges from ScoltaConfig:
every scalar default and every preset's combine-mode documented there must equal
the live class. (ArchitectureAccuracyTest is N/A — it guards a PHP-specific
architecture doc.)
"""

import re
from dataclasses import fields
from pathlib import Path

from scolta.config import ScoltaConfig

_DOC = (Path(__file__).parent.parent / "docs" / "CONFIG_REFERENCE.md").read_text(encoding="utf-8")
_SCALAR_TYPES = {"string", "int", "float", "bool"}


def _slice(start: str, end: str | None) -> str:
    i = _DOC.index(start)
    return _DOC[i:_DOC.index(end, i)] if end else _DOC[i:]


def _parse_properties() -> dict:
    section = _slice("## Configuration Properties", "## Presets")
    rows = {}
    for line in section.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().split("|")]
        if len(cells) < 5:
            continue
        m = re.match(r"^`([a-z][a-z0-9_]*)`$", cells[1])
        if not m or cells[2] not in (_SCALAR_TYPES | {"array"}):
            continue
        rows[m.group(1)] = {"raw": cells[3].strip("`"), "scalar": cells[2] in _SCALAR_TYPES}
    return rows


def _scalar_field_names() -> set[str]:
    out = set()
    for f in fields(ScoltaConfig):
        t = f.type if isinstance(f.type, str) else getattr(f.type, "__name__", "")
        if t in ("str", "int", "float", "bool") and f.name != "preset":
            out.add(f.name)
    return out


def _values_match(live, token: str) -> bool:
    token = token.strip(" `")
    if isinstance(live, bool):
        return token == ("true" if live else "false")
    if isinstance(live, (int, float)):
        try:
            return abs(float(token) - float(live)) < 1e-9
        except ValueError:
            return False
    if live == "":
        return token == "(empty)"
    return live == token.strip("'\"")


def test_parser_finds_enough_rows():
    assert len(_parse_properties()) >= 30


def test_documented_defaults_match_live():
    cfg = ScoltaConfig()
    for name, info in _parse_properties().items():
        if not info["scalar"]:
            continue
        assert hasattr(cfg, name), f"documented `{name}` not on ScoltaConfig"
        live = getattr(cfg, name)
        assert _values_match(live, info["raw"]), (
            f"default drift for `{name}`: doc=`{info['raw']}` vs live=`{live!r}`"
        )


def test_every_scalar_field_is_documented():
    documented = set(_parse_properties().keys())
    for name in _scalar_field_names():
        assert name in documented, f"`{name}` is not documented in CONFIG_REFERENCE.md"


def test_required_scalar_fields_present():
    documented = _parse_properties()
    for name in ("title_match_boost", "recency_boost_max", "expand_primary_weight",
                 "expand_subword_max_frequency", "max_pagefind_results", "results_per_page"):
        assert name in documented


def test_presets_documented_and_combine_mode_resolves():
    section = _slice("Available presets:", None)
    expected_mode = {
        "none": "relevance_union", "reference": "relevance_union",
        "content_catalog": "round_robin", "ecommerce": "round_robin", "blog": "round_robin",
    }
    documented = {}
    for line in section.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().split("|")]
        m = re.match(r"^`([a-z_]+)`$", cells[1]) if len(cells) > 1 else None
        if not m or m.group(1) not in ScoltaConfig.PRESETS:
            continue
        pairs = dict(re.findall(r"`([a-z_]+): ([^`]+)`", line))
        documented[m.group(1)] = pairs

    for name in ScoltaConfig.PRESETS:
        assert name in documented, f"preset `{name}` not documented"
    for name, mode in expected_mode.items():
        if name == "none":
            continue  # 'none' has no row (it's the default), skip the doc-row check
        assert documented.get(name, {}).get("expansion_combine_mode") == mode, (
            f"preset `{name}` combine-mode doc mismatch"
        )
        # The doc must agree with the live preset resolution.
        assert ScoltaConfig.from_dict({"preset": name}).expansion_combine_mode == mode
