"""Tests for TimestampManifest (ported from TimestampManifestTest.php)."""

from scolta.index.timestamp_manifest import TimestampManifest
from scolta.storage import FilesystemDriver


def test_put_get(tmp_path):
    m = TimestampManifest(str(tmp_path), FilesystemDriver())
    m.put("e1", 100, [{"hash": "h", "id": "1"}])
    assert m.get("e1") == {"ts": 100, "items": [{"hash": "h", "id": "1"}]}
    assert m.get("missing") is None


def test_persists_across_reopen(tmp_path):
    d = str(tmp_path)
    m = TimestampManifest(d, FilesystemDriver())
    m.put("e1", 100, [{"id": "1"}])
    m.prune_and_save()
    assert TimestampManifest(d, FilesystemDriver()).get("e1") == {"ts": 100, "items": [{"id": "1"}]}


def test_prune_removes_unseen(tmp_path):
    d = str(tmp_path)
    m = TimestampManifest(d, FilesystemDriver())
    m.put("keep", 1, [])
    m.put("drop", 2, [])
    m.prune_and_save()

    m2 = TimestampManifest(d, FilesystemDriver())
    m2.mark_seen("keep")
    m2.prune_and_save()

    m3 = TimestampManifest(d, FilesystemDriver())
    assert m3.get("keep") is not None
    assert m3.get("drop") is None


def test_count_and_is_empty(tmp_path):
    m = TimestampManifest(str(tmp_path), FilesystemDriver())
    assert m.is_empty() is True
    m.put("e1", 1, [])
    assert m.is_empty() is False
    assert m.count() == 1
