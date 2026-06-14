#!/usr/bin/env python3
"""Validate the built PyPI artifacts (wheel + sdist) before they ship.

Publishing scolta to PyPI is manual, and nothing else in CI builds the
distribution artifacts, so packaging breakage or cruft used to surface only at
`twine upload` time. Two specific failure modes motivate this gate:

  1. The wheel silently shipping WITHOUT the vendored browser runtime assets
     (e.g. ``scripts/vendor_assets.py`` was never run, or hatch quietly dropped
     the data files) — a wheel that imports fine but renders no search UI.
  2. The sdist ballooning with local-only build dirs. The Python sdist defaults
     to "everything on disk minus VCS-ignored", which pulled in
     ``tests/js/node_modules`` (61 MB) and ``tools/stemmer-golden/target``
     (Rust artifacts) — the same class of bloat as the scolta-wp 13 MB plugin
     zip and the WP.org dist-cruft flags.

This runs the asserts against a REAL build so they hold locally and in CI:
    uv build && uv run python scripts/validate-dist.py

The fail-closed lists below are OURS to enumerate. If an assert fires, the
message says WHAT leaked/is missing and WHERE the filter that controls it lives
(pyproject.toml's hatch targets, or scripts/vendor_assets.py).
"""

from __future__ import annotations

import sys
import tarfile
import zipfile
from pathlib import Path

# --- size caps (shared pattern: ~2x the measured good artifact) --------------
# Measured 2026-06-14 against a clean `uv build` on main + this PR:
#   wheel  = 729_525 bytes (~712 KiB; dominated by scolta_core_bg.wasm ~1.2 MB
#            uncompressed, the vendored js, and pagefind .pagefind blobs)
#   sdist  = 2_349_924 bytes (~2.24 MiB; src + the full ported test corpus and
#            stemmer fixtures, with node_modules/target excluded)
# Caps are ~2x those measured values, leaving headroom for asset growth while
# still catching a node_modules/target/cruft regression an order of magnitude
# bigger.
WHEEL_MAX_BYTES = 1_500_000  # ~2x of 729_525
SDIST_MAX_BYTES = 4_700_000  # ~2x of 2_349_924

# --- vendored runtime assets that MUST be in the wheel -----------------------
# Enumerated from `scripts/vendor_assets.py` (_SUBDIRS x allowed extensions) and
# the assets/ tree. These are the browser-side runtime: missing any of them
# yields an importable-but-non-functional package. The filter that produces
# them lives in scripts/vendor_assets.py (re-vendoring) and
# [tool.hatch.build.targets.wheel] packages = ["src/scolta"] (inclusion).
REQUIRED_WHEEL_ASSETS = (
    "scolta/assets/css/scolta.css",
    "scolta/assets/js/scolta.js",
    "scolta/assets/pagefind/pagefind-worker.js",
    "scolta/assets/pagefind/pagefind.js",
    "scolta/assets/pagefind/wasm.en.pagefind",
    "scolta/assets/pagefind/wasm.unknown.pagefind",
    "scolta/assets/wasm/scolta_core.js",
    "scolta/assets/wasm/scolta_core_bg.wasm",
)

# Sidecar/checksum files vendor_assets.py is fail-closed against — they must
# never reach the wheel even if they appear in the source asset tree.
FORBIDDEN_ASSET_SUFFIXES = (".sha256", ".d.ts", ".map", ".log")


def _fail(msg: str) -> None:
    print(f"  FAIL: {msg}", file=sys.stderr)


def validate_wheel(path: Path) -> list[str]:
    errors: list[str] = []
    size = path.stat().st_size
    print(f"wheel: {path.name} ({size:,} bytes)")
    if size > WHEEL_MAX_BYTES:
        errors.append(
            f"wheel is {size:,} bytes, over the {WHEEL_MAX_BYTES:,} cap "
            "(raise it in scripts/validate-dist.py only if the asset growth is "
            "intentional)"
        )

    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()

    dist_info = next((n.split("/", 1)[0] for n in names if n.endswith(".dist-info/RECORD")), None)

    # (a) every vendored runtime asset is present
    present = set(names)
    for asset in REQUIRED_WHEEL_ASSETS:
        if asset not in present:
            errors.append(
                f"vendored asset MISSING from wheel: {asset} -- run "
                "`python scripts/vendor_assets.py` and confirm "
                "[tool.hatch.build.targets.wheel] in pyproject.toml ships it"
            )

    # (b) nothing outside the scolta package or the dist-info lives in the wheel
    for name in names:
        if name.endswith("/"):
            continue
        top = name.split("/", 1)[0]
        if top == "scolta" or (dist_info and top == dist_info):
            continue
        errors.append(
            f"unexpected file in wheel outside the scolta package/dist-info: {name} "
            "-- tighten [tool.hatch.build.targets.wheel] in pyproject.toml"
        )

    # (c) no tests, caches, pyc, or sidecar/checksum cruft
    for name in names:
        low = name.lower()
        if name.startswith("scolta/tests/") or "/tests/" in name:
            errors.append(f"tests/ leaked into wheel: {name} -- exclude in hatch wheel target")
        if "__pycache__" in name or low.endswith(".pyc"):
            errors.append(f"bytecode/pycache leaked into wheel: {name}")
        if ".pytest_cache" in name or ".ruff_cache" in name:
            errors.append(f"tool cache leaked into wheel: {name}")
        if any(low.endswith(suffix) for suffix in FORBIDDEN_ASSET_SUFFIXES):
            errors.append(
                f"sidecar/checksum file leaked into wheel: {name} -- "
                "scripts/vendor_assets.py allowlist should have blocked it"
            )
    return errors


def validate_sdist(path: Path) -> list[str]:
    errors: list[str] = []
    size = path.stat().st_size
    print(f"sdist: {path.name} ({size:,} bytes)")
    if size > SDIST_MAX_BYTES:
        errors.append(
            f"sdist is {size:,} bytes, over the {SDIST_MAX_BYTES:,} cap -- the "
            "usual cause is a local build dir (node_modules / cargo target) "
            "leaking; tighten [tool.hatch.build.targets.sdist].exclude in "
            "pyproject.toml"
        )

    with tarfile.open(path, "r:gz") as tf:
        names = tf.getnames()

    # strip the leading "scolta-<version>/" prefix for clearer matching
    rel = []
    for name in names:
        parts = name.split("/", 1)
        rel.append(parts[1] if len(parts) == 2 else parts[0])

    # buildable source set must be present
    must_have = ("pyproject.toml", "src/scolta/__init__.py", "PKG-INFO")
    for needed in must_have:
        if needed not in rel:
            errors.append(f"sdist is not buildable: missing {needed}")
    if not any(r.startswith("src/scolta/assets/") for r in rel):
        errors.append("sdist carries no src/scolta/assets/ — vendored assets missing from source")

    # no junk: local build dirs, caches, IDE files
    for name, r in zip(names, rel, strict=True):
        low = r.lower()
        if "node_modules" in r:
            errors.append(
                f"node_modules leaked into sdist: {name} -- exclude in "
                "[tool.hatch.build.targets.sdist] in pyproject.toml"
            )
        if r.startswith("tools/") and "/target/" in r:
            errors.append(
                f"cargo build target leaked into sdist: {name} -- exclude "
                "tools/**/target in the hatch sdist target"
            )
        if "__pycache__" in r or low.endswith(".pyc"):
            errors.append(f"bytecode/pycache leaked into sdist: {name}")
        if ".pytest_cache" in r or ".ruff_cache" in r:
            errors.append(f"tool cache leaked into sdist: {name}")
        if "/.idea/" in f"/{r}" or "/.vscode/" in f"/{r}":
            errors.append(f"IDE config leaked into sdist: {name}")
        if low.endswith(".ds_store"):
            errors.append(f".DS_Store leaked into sdist: {name}")
    return errors


def main() -> int:
    dist = Path(__file__).resolve().parent.parent / "dist"
    wheels = sorted(dist.glob("*.whl"))
    sdists = sorted(dist.glob("*.tar.gz"))

    if not wheels:
        print(f"no wheel found in {dist} -- run `uv build` first", file=sys.stderr)
        return 1
    if not sdists:
        print(f"no sdist found in {dist} -- run `uv build` first", file=sys.stderr)
        return 1

    errors: list[str] = []
    for wheel in wheels:
        errors.extend(validate_wheel(wheel))
    for sdist in sdists:
        errors.extend(validate_sdist(sdist))

    if errors:
        print(f"\nDistribution validation FAILED ({len(errors)} problem(s)):", file=sys.stderr)
        for err in errors:
            _fail(err)
        return 1

    print("\nDistribution validation passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
