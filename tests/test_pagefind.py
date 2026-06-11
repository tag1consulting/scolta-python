"""PagefindBinary command handling.

Regression: configured binary paths were naively str.split() before being
passed to subprocess, so a path containing spaces shattered into garbage argv
and the binary was reported as unavailable.
"""

import stat
import sys

import pytest

from scolta.pagefind import PagefindBinary


@pytest.fixture
def spaced_binary(tmp_path):
    if sys.platform == "win32":
        pytest.skip("POSIX shell stub")
    bin_dir = tmp_path / "dir with spaces"
    bin_dir.mkdir()
    path = bin_dir / "pagefind"
    path.write_text("#!/bin/sh\necho 'pagefind 1.5.0'\n")
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return str(path)


def test_configured_path_with_spaces_resolves(spaced_binary):
    binary = PagefindBinary(configured_path=spaced_binary)
    assert binary.resolve() == spaced_binary
    assert binary.resolved_via() == "configured"


def test_configured_path_with_spaces_reports_version(spaced_binary):
    binary = PagefindBinary(configured_path=spaced_binary)
    assert binary.version() == "pagefind 1.5.0"


def test_project_local_path_with_spaces_resolves(tmp_path):
    if sys.platform == "win32":
        pytest.skip("POSIX shell stub")
    project = tmp_path / "my project"
    bin_dir = project / ".scolta" / "bin"
    bin_dir.mkdir(parents=True)
    path = bin_dir / "pagefind"
    path.write_text("#!/bin/sh\necho 'pagefind 1.5.0'\n")
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    binary = PagefindBinary(project_dir=str(project))
    assert binary.resolve() == str(path)
    assert binary.resolved_via() == "local"
    assert binary.version() == "pagefind 1.5.0"


def test_resolved_argv_is_a_list_not_a_split_string(spaced_binary):
    binary = PagefindBinary(configured_path=spaced_binary)
    assert binary.resolved_argv() == [spaced_binary]
