"""Tests for BuildState (ported from BuildStateTest.php / BuildStateAtomicWriteTest.php)."""

import json
import os

from scolta.index.build_state import BuildState


def test_initiate_and_lock(tmp_path):
    s = BuildState(str(tmp_path))
    assert s.initiate_build({"total_pages": 10}) is True
    assert s.is_running() is True
    # A second BuildState cannot acquire the lock while the first holds it.
    s2 = BuildState(str(tmp_path))
    assert s2.initiate_build({"total_pages": 10}) is False
    s.release_lock()
    assert s.is_running() is False


def test_record_and_read_chunk(tmp_path):
    s = BuildState(str(tmp_path))
    s.initiate_build({"total_pages": 2})
    partial = {"pages": {0: {"url": "/a", "wordCount": 1}},
               "index": {"x": {0: {"positions": {25: [0]}, "meta_positions": []}}}}
    s.record_chunk(0, partial)
    assert s.get_pages_processed() == 1
    assert len(s.get_chunk_files()) == 1
    back = s.read_chunk(0)
    assert back["pages"][0]["url"] == "/a"
    assert back["index"]["x"][0]["positions"][25] == [0]
    s.release_lock()


def test_resume_detects_building_state(tmp_path):
    s = BuildState(str(tmp_path))
    s.initiate_build({"total_pages": 5})
    s.record_chunk(0, {"pages": {0: {}}, "index": {}})
    s.release_lock_only()  # leaves status 'building' and chunk files
    s2 = BuildState(str(tmp_path))
    manifest = s2.should_resume()
    assert manifest is not None
    assert manifest["chunks_written"] == 1


def test_release_lock_sets_idle_not_resumable(tmp_path):
    s = BuildState(str(tmp_path))
    s.initiate_build({"total_pages": 5})
    s.release_lock()
    assert BuildState(str(tmp_path)).should_resume() is None


def test_cleanup_removes_transient_files_but_not_subdirs(tmp_path):
    s = BuildState(str(tmp_path))
    s.initiate_build({"total_pages": 1})
    s.record_chunk(0, {"pages": {0: {}}, "index": {}})
    # Simulate the cross-build cache subdir.
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    (cache_dir / "manifest.msgpack").write_bytes(b"keep me")
    s.release_lock_only()
    s.cleanup()
    assert not list(tmp_path.glob("chunk-*.dat"))
    assert not (tmp_path / "manifest.json").exists()
    # The cache subdir and its contents survive the cleanup.
    assert (cache_dir / "manifest.msgpack").read_bytes() == b"keep me"


def test_manifest_atomic_write_is_valid_json(tmp_path):
    s = BuildState(str(tmp_path))
    s.initiate_build({"total_pages": 7, "fingerprint": "abc"})
    data = json.loads((tmp_path / "manifest.json").read_text())
    assert data["total_pages"] == 7
    assert data["status"] == "building"
    assert not os.path.exists(str(tmp_path / "manifest.json.tmp"))
    s.release_lock()
