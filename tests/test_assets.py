"""Asset vendoring: the runtime bundle is present and no sidecar/checksum files
leaked. The vendoring is fail-closed by extension allowlist."""

import sys
from pathlib import Path

_ASSETS = Path(__file__).resolve().parent.parent / "src" / "scolta" / "assets"

_EXPECTED_RUNTIME = {
    "css/scolta.css",
    "js/scolta.js",
    "wasm/scolta_core.js",
    "wasm/scolta_core_bg.wasm",
    "pagefind/pagefind.js",
    "pagefind/pagefind-worker.js",
    "pagefind/wasm.en.pagefind",
    "pagefind/wasm.unknown.pagefind",
}

_FORBIDDEN_EXT = {".sha256", ".d.ts", ".ts", ".map", ".log"}


def test_runtime_assets_present():
    for rel in _EXPECTED_RUNTIME:
        assert (_ASSETS / rel).is_file(), f"missing runtime asset: {rel}"


def test_no_sidecar_or_checksum_files_leaked():
    leaked = []
    for f in _ASSETS.rglob("*"):
        if not f.is_file():
            continue
        name = f.name
        if name.endswith(".sha256") or name.endswith(".d.ts") or name.endswith(".map") or name.endswith(".log"):
            leaked.append(str(f.relative_to(_ASSETS)))
    assert leaked == [], f"sidecar/checksum files leaked into the package: {leaked}"


def test_only_allowed_extensions_present():
    allowed = {".css", ".js", ".wasm", ".pagefind"}
    for f in _ASSETS.rglob("*"):
        if f.is_file():
            assert f.suffix in allowed, f"unexpected asset extension: {f.name}"


def test_vendoring_allowlist_is_fail_closed(tmp_path, monkeypatch):
    # Drive the real vendoring function over a synthetic source dir containing
    # sidecars; assert they are never copied.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import vendor_assets

    src = tmp_path / "assets"
    (src / "js").mkdir(parents=True)
    (src / "wasm").mkdir(parents=True)
    (src / "js" / "scolta.js").write_text("ok")
    (src / "js" / "scolta.js.sha256").write_text("deadbeef")
    (src / "wasm" / "core.wasm").write_bytes(b"\x00")
    (src / "wasm" / "core.d.ts").write_text("types")
    (src / "wasm" / "core.js.map").write_text("map")
    dst = tmp_path / "out"

    monkeypatch.setattr(vendor_assets, "_SRC", str(src))
    monkeypatch.setattr(vendor_assets, "_DST", str(dst))
    copied = vendor_assets.vendor()

    assert set(copied) == {"js/scolta.js", "wasm/core.wasm"}
    assert not list(dst.rglob("*.sha256"))
    assert not list(dst.rglob("*.d.ts"))
    assert not list(dst.rglob("*.map"))
