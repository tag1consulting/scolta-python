"""Ported from tests/Index/IndexerResolverTest.php.

PHP uses 'php'/'binary'/'auto'; the Python port uses 'python'/'binary'/'auto'
with the same design rule: auto/unknown -> python; binary -> binary if present
else fall back to python with a logged notice.
"""

import os
import stat
import sys
from pathlib import Path

import pytest

from scolta.index.resolver import IndexerResolver
from scolta.pagefind import PagefindBinary


class SpyLogger:
    def __init__(self):
        self.records = []

    def info(self, msg, *args):
        self.records.append(msg % args if args else msg)


class UnavailableBinary(PagefindBinary):
    def resolve(self):
        return None

    def status(self):
        return {
            "available": False,
            "binary": None,
            "version": None,
            "via": "none",
            "message": "Pagefind binary not found (stub).",
        }


@pytest.fixture
def fake_binary(tmp_path):
    if sys.platform == "win32":
        pytest.skip("POSIX shell stub")
    path = tmp_path / "pagefind"
    path.write_text("#!/bin/sh\necho 'pagefind 1.5.0'\n")
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return str(path)


def test_python_mode_returns_python():
    log = SpyLogger()
    assert IndexerResolver(PagefindBinary(), log).resolve("python") == "python"
    assert "Using Python indexer" in log.records[0]


def test_binary_mode_with_available_binary(fake_binary):
    log = SpyLogger()
    result = IndexerResolver(PagefindBinary(configured_path=fake_binary), log).resolve("binary")
    assert result == "binary"
    assert "Using binary indexer" in log.records[0]


def test_binary_mode_missing_falls_back_to_python():
    log = SpyLogger()
    result = IndexerResolver(UnavailableBinary(), log).resolve("binary")
    assert result == "python"
    assert "Falling back to Python indexer" in log.records[0]
    assert "binary not available" in log.records[0]


def test_auto_mode_returns_python():
    assert IndexerResolver(PagefindBinary(), SpyLogger()).resolve("auto") == "python"


def test_auto_mode_with_available_binary_still_python(fake_binary):
    log = SpyLogger()
    assert (
        IndexerResolver(PagefindBinary(configured_path=fake_binary), log).resolve("auto")
        == "python"
    )
    assert "Using Python indexer" in log.records[0]


def test_unknown_mode_returns_python():
    assert IndexerResolver(PagefindBinary(), SpyLogger()).resolve("nonsense") == "python"


# -- PagefindBinary resolution ------------------------------------------------


def test_binary_resolves_configured_path(fake_binary):
    b = PagefindBinary(configured_path=fake_binary)
    assert b.resolve() == fake_binary
    assert b.resolved_via() == "configured"
    assert "1.5.0" in (b.version() or "")
    assert b.status()["available"] is True


def test_binary_resolves_project_local(tmp_path):
    if sys.platform == "win32":
        pytest.skip("POSIX shell stub")
    bindir = tmp_path / ".scolta" / "bin"
    bindir.mkdir(parents=True)
    bin_path = bindir / "pagefind"
    bin_path.write_text("#!/bin/sh\necho 'pagefind 1.5.0'\n")
    bin_path.chmod(bin_path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    b = PagefindBinary(project_dir=str(tmp_path))
    assert b.resolve() == str(bin_path)
    assert b.resolved_via() == "local"


def test_binary_status_unavailable_message(monkeypatch, tmp_path):
    # Hermetic: point PATH at an empty dir so neither `npx` nor a system
    # `pagefind` can resolve. Without this, the fallback chain reaches the
    # `npx pagefind` probe, whose result depends on the runner (whether npx is
    # present and how its npm auto-installs/caches pagefind). status() and
    # resolved_via() each call resolve() independently, and that probe is
    # stateful across the two calls, so resolved_via() flipped from "none" to
    # "npx" under the setup-node v6 to v7 bump and the run went red. Forcing an
    # empty PATH makes the "binary unavailable" path deterministic everywhere.
    monkeypatch.setenv("PATH", str(tmp_path))
    b = PagefindBinary(configured_path="/nonexistent/pagefind-xyz", project_dir="/nonexistent")
    status = b.status()
    assert status["available"] is False
    assert "not found" in status["message"]
    assert b.resolved_via() == "none"


def test_download_target_dir_creates_project_local(tmp_path):
    d = PagefindBinary(project_dir=str(tmp_path)).download_target_dir()
    assert d == os.path.join(str(tmp_path), ".scolta", "bin")
    assert Path(d).is_dir()
