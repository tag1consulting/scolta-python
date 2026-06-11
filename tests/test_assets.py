"""Asset vendoring: the runtime bundle is present and no sidecar/checksum files
leaked. The vendoring is fail-closed by extension allowlist."""

import shutil
import sys
from pathlib import Path

import pytest

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
        if (
            name.endswith(".sha256")
            or name.endswith(".d.ts")
            or name.endswith(".map")
            or name.endswith(".log")
        ):
            leaked.append(str(f.relative_to(_ASSETS)))
    assert leaked == [], f"sidecar/checksum files leaked into the package: {leaked}"


def test_only_allowed_extensions_present():
    allowed = {".css", ".js", ".wasm", ".pagefind"}
    for f in _ASSETS.rglob("*"):
        if f.is_file():
            assert f.suffix in allowed, f"unexpected asset extension: {f.name}"


def _vendor_assets_module():
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import vendor_assets

    return vendor_assets


def _make_source(tmp_path):
    """A complete synthetic source tree: one allowed file per vendored subdir."""
    src = tmp_path / "assets"
    for subdir, name, payload in (
        ("css", "scolta.css", "ok"),
        ("js", "scolta.js", "ok"),
        ("wasm", "core.wasm", "ok"),
        ("pagefind", "wasm.en.pagefind", "ok"),
    ):
        (src / subdir).mkdir(parents=True)
        (src / subdir / name).write_text(payload)
    return src


def test_vendoring_allowlist_is_fail_closed(tmp_path):
    # Drive the real vendoring function over a synthetic source dir containing
    # sidecars; assert they are never copied.
    vendor_assets = _vendor_assets_module()
    src = _make_source(tmp_path)
    (src / "js" / "scolta.js.sha256").write_text("deadbeef")
    (src / "wasm" / "core.d.ts").write_text("types")
    (src / "wasm" / "core.js.map").write_text("map")
    dst = tmp_path / "out"

    copied = vendor_assets.vendor(str(src), str(dst))

    assert set(copied) == {
        "css/scolta.css",
        "js/scolta.js",
        "wasm/core.wasm",
        "pagefind/wasm.en.pagefind",
    }
    assert not list(dst.rglob("*.sha256"))
    assert not list(dst.rglob("*.d.ts"))
    assert not list(dst.rglob("*.map"))


def test_vendoring_rejects_partial_source_tree(tmp_path):
    # A missing source subdir must abort non-zero, not exit 0 with a partial
    # bundle.
    vendor_assets = _vendor_assets_module()
    src = _make_source(tmp_path)
    shutil.rmtree(src / "wasm")

    with pytest.raises(SystemExit) as excinfo:
        vendor_assets.vendor(str(src), str(tmp_path / "out"))
    assert "wasm" in str(excinfo.value)


def test_vendoring_rejects_empty_source_subdir(tmp_path):
    # A subdir with no allowlisted files is as broken as a missing one.
    vendor_assets = _vendor_assets_module()
    src = _make_source(tmp_path)
    (src / "js" / "scolta.js").unlink()
    (src / "js" / "scolta.js.sha256").write_text("deadbeef")  # only a sidecar left

    with pytest.raises(SystemExit) as excinfo:
        vendor_assets.vendor(str(src), str(tmp_path / "out"))
    assert "js" in str(excinfo.value)


def test_vendoring_removes_stale_destination_files(tmp_path):
    # Files deleted upstream must not stay vendored forever.
    vendor_assets = _vendor_assets_module()
    src = _make_source(tmp_path)
    dst = tmp_path / "out"
    (dst / "js").mkdir(parents=True)
    (dst / "js" / "deleted-upstream.js").write_text("stale")

    vendor_assets.vendor(str(src), str(dst))

    assert not (dst / "js" / "deleted-upstream.js").exists()
    assert (dst / "js" / "scolta.js").is_file()
