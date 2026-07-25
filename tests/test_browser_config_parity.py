"""Browser-config parity guard (port of tests/Config/BrowserConfigParityTest.php).

The vendored ``src/scolta/assets/js/scolta.js`` is the canonical browser bundle,
byte-identical to scolta-php's copy. Every config value it consumes is read off
the instance config object that ``to_browser_config()`` produces, so the two are
a contract: a key the bundle reads but no config layer emits is a feature that is
dead on arrival, and a key this package emits but the bundle never reads is dead
weight. Eight scoring keys shipped readable-but-unsettable here for exactly that
reason: nothing asserted the emitted config covered what the browser reads.

This test parses the bundle for the keys it reads and diffs them against
``to_browser_config()``, in both directions, recursing one level into the
``scoring`` and ``endpoints`` sub-objects (a top-level-only check passes while a
scoring sub-key is missing, which is how those eight hid).

Two deliberate design choices, shared with the other four implementations:

- **Comments are NOT stripped before matching.** Naively cutting ``//`` to end of
  line would corrupt every line containing a URL such as ``https://`` and could
  silently drop a real key. Today exactly one comment names a config key
  (``instanceConfig.currentLanguage``) and that key is real, so comment noise
  produces zero phantoms. If a future comment does introduce a phantom, this test
  fails loudly and the maintainer either emits the key or adds it to an allowlist
  with a written justification. Loud and occasionally wrong beats silent and
  blind.
- **The reverse assertion uses strict set membership, not a substring search of
  the bundle.** A substring search over 3,300 lines matches almost any plausible
  camelCase name and would make the assertion worthless.

The parse is deliberately strict: the tripwire assertions run BEFORE any diff, so
a reformat of scolta.js that stops the extraction matching fails loudly instead
of passing while asserting nothing.
"""

import re
from pathlib import Path

from scolta.config import ScoltaConfig

_BUNDLE = (
    Path(__file__).parent.parent / "src" / "scolta" / "assets" / "js" / "scolta.js"
).read_text(encoding="utf-8")

# Keys scolta.js reads that to_browser_config() deliberately does not emit.
# Subtracts from the extracted set, so it may only ever contain keys the bundle
# actually reads.
_FORWARD_ALLOWLIST = {
    # Supplied by the platform's language layer, not by the config object.
    "currentLanguage",
    # Has no config field. Adapters pass an empty list; a direct caller supplies
    # it through create_instance().
    "allowedLinkDomains",
    # Same as allowedLinkDomains: caller-supplied, no config field.
    "disclaimer",
    # Emitted by no adapter at all; caller-supplied through the create_instance()
    # public API only. Note the snake_case name, unlike every other top-level key.
    "priority_pages",
}

# Keys to_browser_config() emits that scolta.js does not read off the instance
# config. Subtracts from the emitted set, so it may only ever contain keys this
# package actually emits. Empty: scolta-python emits nothing the browser does not
# read.
_REVERSE_ALLOWLIST: set[str] = set()


def _extract_top_level_keys() -> set[str]:
    """Distinct top-level keys read as ``instanceConfig.<key>``."""
    keys = set(re.findall(r"instanceConfig\.([A-Za-z_][A-Za-z0-9_]*)", _BUNDLE))
    assert len(keys) >= 11, (
        "Parsed too few top-level config reads from src/scolta/assets/js/scolta.js: the "
        "bundle may have been reformatted so `instanceConfig.<key>` no longer matches. "
        "Update the parser in tests/test_browser_config_parity.py so the guard keeps working."
    )
    return keys


def _extract_scoring_keys() -> set[str]:
    """Distinct scoring keys read as ``KEY: s.KEY ??`` in the config return literals.

    The regex matches two return literals, the module-level ``getConfig()`` block
    and the ``getInstanceConfig()`` block, and their union is the full set only
    because the former's keys are a strict subset of the latter's. That holds
    today; if it ever stops holding, the tripwire count below moves and whoever
    hits it reads this note.

    Parsing the literals rather than grepping consumption sites is deliberate:
    several keys are forwarded to WASM wholesale and never named at a use site,
    so a consumption-site grep would silently miss them.
    """
    keys = set(re.findall(r"^[ \t]*([A-Z][A-Z0-9_]*):[ \t]*s\.\1[ \t]*\?\?", _BUNDLE, re.M))
    assert len(keys) >= 40, (
        "Parsed too few scoring keys from src/scolta/assets/js/scolta.js: the "
        "getInstanceConfig() return literal may have been reformatted so `KEY: s.KEY ??` no "
        "longer matches. Update the parser in tests/test_browser_config_parity.py so the "
        "guard keeps working."
    )
    return keys


def _extract_endpoint_keys() -> set[str]:
    """Distinct endpoint keys read as ``key: e.key ||``."""
    keys = set(re.findall(r"^[ \t]*([a-z]+):[ \t]*e\.\1[ \t]*\|\|", _BUNDLE, re.M))
    assert len(keys) == 3, (
        "Expected exactly 3 endpoint keys in src/scolta/assets/js/scolta.js (expand, "
        f"summarize, followup) but parsed {len(keys)}. Either an endpoint was added or the "
        "bundle was reformatted so `key: e.key ||` no longer matches. Update the parser in "
        "tests/test_browser_config_parity.py so the guard keeps working."
    )
    return keys


def test_emits_every_top_level_key_the_browser_reads():
    read = _extract_top_level_keys()
    emitted = set(ScoltaConfig().to_browser_config())
    missing = read - _FORWARD_ALLOWLIST - emitted
    assert not missing, (
        f"scolta.js reads {sorted(missing)} off the instance config but to_browser_config() "
        "does not emit them, so the features behind them are unreachable. Either emit the "
        "keys or add them to _FORWARD_ALLOWLIST in tests/test_browser_config_parity.py with a "
        "written justification."
    )


def test_emits_every_scoring_key_the_browser_reads():
    read = _extract_scoring_keys()
    emitted = set(ScoltaConfig().to_browser_config()["scoring"])
    missing = read - emitted
    assert not missing, (
        f"scolta.js reads scoring keys {sorted(missing)} but to_js_scoring_config() does not "
        "emit them, so they can only ever take their hardcoded JS fallbacks. Add a dataclass "
        "field for each."
    )


def test_emits_every_endpoint_key_the_browser_reads():
    read = _extract_endpoint_keys()
    emitted = set(ScoltaConfig().to_browser_config()["endpoints"])
    missing = read - emitted
    assert not missing, (
        f"scolta.js reads endpoints {sorted(missing)} but to_browser_config() does not emit "
        "them in `endpoints`."
    )


def test_emits_no_top_level_key_the_browser_never_reads():
    """Reverse direction, separate so it can be allowlisted independently.

    Semantics are strict set membership against the extracted key set, not a
    substring search of the bundle (see the module docstring).
    """
    read = _extract_top_level_keys()
    emitted = set(ScoltaConfig().to_browser_config())
    dead = emitted - _REVERSE_ALLOWLIST - read
    assert not dead, (
        f"to_browser_config() emits {sorted(dead)} but scolta.js never reads them off the "
        "instance config, so they are dead weight in every page payload. Either drop them or "
        "add them to _REVERSE_ALLOWLIST in tests/test_browser_config_parity.py with a written "
        "justification."
    )
