"""Prompt-text identity gate (ported from scolta-php
tests/Prompt/PromptTextIdentityTest.php and scolta-node
tests/ai/prompt-identity.test.ts).

The three AI prompt templates exist as hand-maintained copies in
scolta-core/src/prompts.rs (the Rust/WASM source), scolta-php, scolta-node, and
here. scolta-php and scolta-node each had a gate that fails loudly when their
copy drifts from the canonical Rust base text; this package did not, so its
copy could silently diverge while every other test stayed green. That is the
gap this module closes.

Two documented, intentional differences are normalized out:

 1. The ``{DYNAMIC_ANCHORS}`` line exists ONLY in the Rust copy — it is the
    WASM-path injection token, filled by scolta-core's resolve_template().
    Server-side bindings inject per-site context through their own enricher /
    prompt-override mechanism instead, so the token is deliberately absent
    here. It is stripped from the Rust side before comparison.
 2. Language-specific string escaping. We compare the runtime template strings
    (``get_template``), which carry no source-level escaping, against the Rust
    raw-string bodies (which also have none).

Path resolution mirrors the other two gates: the SCOLTA_CORE_PROMPTS env
override (set by CI), else the umbrella-checkout sibling path.
  - env set but file missing  → FAIL (a typo must not silently disable the gate)
  - env unset and sibling missing → FAIL under CI, SKIP otherwise. A gate that
    skips itself is worse than no gate, because the job still reports green
    while the copy drifts; off CI the skip is legitimate, because a
    published-package checkout has no scolta-core sibling to compare against.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from scolta.ai import prompts

# Python template name -> Rust const name in scolta-core/src/prompts.rs.
TEMPLATE_TO_CONST = {
    "expand_query": "EXPAND_QUERY",
    "summarize": "SUMMARIZE",
    "follow_up": "FOLLOW_UP",
}


def _core_prompts_path() -> Path:
    override = os.environ.get("SCOLTA_CORE_PROMPTS")
    if override:
        return Path(override)
    # tests/ai/ -> tests/ -> scolta-python/ -> packages/ -> packages/scolta-core/...
    return Path(__file__).resolve().parents[2].parent / "scolta-core" / "src" / "prompts.rs"


def _strip_dynamic_anchors_line(text: str) -> str:
    """Remove any line consisting solely of ``{DYNAMIC_ANCHORS}``."""
    return re.sub(r"^\{DYNAMIC_ANCHORS\}\n", "", text, flags=re.MULTILINE)


def _extract_rust_raw_const(source: str, const_name: str) -> str:
    """Extract the verbatim body of a Rust raw-string constant.

    Raw strings contain no escape sequences, so the body is the literal text
    between the delimiters. The hash count is detected per-constant rather than
    assumed: EXPAND_QUERY/SUMMARIZE use ``r#"..."#`` while FOLLOW_UP uses
    ``r##"..."##`` because its body contains the literal sequence ``"#``.
    """
    decl = source.find(f"pub const {const_name}:")
    if decl == -1:
        raise AssertionError(
            f"Could not find `pub const {const_name}:` in scolta-core/src/prompts.rs"
        )
    eq = source.find("=", decl)
    if eq == -1:
        raise AssertionError(f"Malformed const {const_name}: no `=` after declaration")

    opener = re.search(r'r(#+)"', source[eq:])
    if opener is None:
        raise AssertionError(f"Could not find raw-string opener for const {const_name}")

    hashes = opener.group(1)
    open_end = eq + opener.end()
    closer = '"' + hashes
    close_pos = source.find(closer, open_end)
    if close_pos == -1:
        raise AssertionError(f"Could not find raw-string closer `{closer}` for const {const_name}")

    return source[open_end:close_pos]


@pytest.mark.parametrize(("py_name", "rust_const"), sorted(TEMPLATE_TO_CONST.items()))
def test_shared_base_text_matches_scolta_core(py_name: str, rust_const: str) -> None:
    explicit = bool(os.environ.get("SCOLTA_CORE_PROMPTS"))
    path = _core_prompts_path()

    if not path.is_file():
        if explicit:
            pytest.fail(f"SCOLTA_CORE_PROMPTS is set but no file exists at {path}")
        if os.environ.get("CI"):
            # Under CI the canonical source must be reachable. Skipping here
            # would report the parity gate green while the copy drifts.
            pytest.fail(
                f"scolta-core prompts not found at {path}. CI must check out "
                "tag1consulting/scolta-core and set SCOLTA_CORE_PROMPTS; this "
                "gate must never skip in CI."
            )
        pytest.skip(f"scolta-core source not checked out ({path})")

    source = path.read_text(encoding="utf-8")
    core_base = _strip_dynamic_anchors_line(_extract_rust_raw_const(source, rust_const))

    assert prompts.get_template(py_name) == core_base, (
        f"Shared base text for template '{py_name}' diverged from scolta-core const "
        f"{rust_const} (after normalizing the {{DYNAMIC_ANCHORS}} injection line). "
        "Reconcile the two copies; the resolution direction is a reviewer decision."
    )
