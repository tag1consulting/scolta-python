#!/usr/bin/env python3
"""Vendor the shared WASM/JS/CSS asset bundle from scolta-php into scolta-python.

The asset bundle (scolta-core compiled to WASM, plus scolta.js/css and the
Pagefind runtime) is language-independent and reused verbatim — never
regenerated here. Copying is **fail-closed by extension allowlist**: only files
whose extension is explicitly allowed ship. Sidecar/checksum files
(``.sha256``, ``.d.ts``, ``.map``, ``.log``) can never match, so they never leak
into the package.

Run from the package root after the scolta-php assets change:
    python scripts/vendor_assets.py
"""

from __future__ import annotations

import os
import shutil
import sys

# Only these extensions are ever copied from the asset subdirectories.
_ALLOWED_EXTENSIONS = {".wasm", ".js", ".css", ".pagefind"}
# Subdirectories of assets/ to vendor.
_SUBDIRS = ("css", "js", "wasm", "pagefind")

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.normpath(os.path.join(_HERE, "..", "..", "scolta-php", "assets"))
_DST = os.path.normpath(os.path.join(_HERE, "..", "src", "scolta", "assets"))


def is_allowed(filename: str) -> bool:
    return os.path.splitext(filename)[1] in _ALLOWED_EXTENSIONS


def vendor() -> list[str]:
    if not os.path.isdir(_SRC):
        sys.exit(f"Source asset dir not found: {_SRC} (need a sibling scolta-php checkout)")
    copied = []
    for subdir in _SUBDIRS:
        src_dir = os.path.join(_SRC, subdir)
        if not os.path.isdir(src_dir):
            continue
        dst_dir = os.path.join(_DST, subdir)
        os.makedirs(dst_dir, exist_ok=True)
        for name in sorted(os.listdir(src_dir)):
            src_file = os.path.join(src_dir, name)
            if not os.path.isfile(src_file) or not is_allowed(name):
                continue  # fail-closed: anything not explicitly allowed is skipped
            shutil.copy2(src_file, os.path.join(dst_dir, name))
            copied.append(f"{subdir}/{name}")
    return copied


if __name__ == "__main__":
    files = vendor()
    print(f"Vendored {len(files)} asset files:")
    for f in files:
        print(f"  {f}")
