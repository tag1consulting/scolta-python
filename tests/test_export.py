"""Tests for ContentExporter (ported behaviour from Export/ContentExporter.php)."""

import os

import pytest

from scolta.content import ContentItem
from scolta.export import ContentExporter


def _item(**kw):
    base = dict(id="1", title="T", body_html="<p>" + "word " * 40 + "</p>",
                url="/recipe/x", date="2024-01-01")
    base.update(kw)
    return ContentItem(**base)


@pytest.mark.parametrize("url,expected", [
    ("/recipe/chocolate-cake/", "recipe/chocolate-cake/index.html"),
    ("/recipe/chocolate-cake", "recipe/chocolate-cake/index.html"),
    ("/about", "about/index.html"),
    ("/", "index.html"),
    ("", "index.html"),
    ("/p?q=1", "p/index.html"),
    ("/p#frag", "p/index.html"),
    ("/a/b/c/", "a/b/c/index.html"),
])
def test_url_to_export_path(url, expected):
    assert ContentExporter.url_to_export_path(url) == expected


def test_export_writes_nested_file(tmp_path):
    exp = ContentExporter(str(tmp_path))
    exp.prepare_output_dir()
    assert exp.export(_item(url="/recipe/cake")) is True
    written = tmp_path / "recipe" / "cake" / "index.html"
    assert written.exists()
    assert "data-pagefind-body" in written.read_text(encoding="utf-8")
    assert exp.get_stats() == {"exported": 1, "skipped": 0}


def test_export_skips_short_content(tmp_path):
    exp = ContentExporter(str(tmp_path), min_content_length=50)
    exp.prepare_output_dir()
    assert exp.export(_item(body_html="<p>tiny</p>")) is False
    assert exp.get_stats() == {"exported": 0, "skipped": 1}


def test_export_path_collision_raises(tmp_path):
    exp = ContentExporter(str(tmp_path))
    exp.prepare_output_dir()
    exp.export(_item(id="1", url="/recipe/x"))
    with pytest.raises(RuntimeError, match="collision"):
        exp.export(_item(id="2", url="/recipe/x"))


def test_filter_items_passes_through_non_content_items(tmp_path):
    exp = ContentExporter(str(tmp_path))
    marker = object()
    items = [_item(id="1"), marker, _item(id="2", body_html="<p>too short</p>")]
    out = list(exp.filter_items(items))
    # The long item and the marker pass; the short ContentItem is filtered out.
    assert out[0].id == "1"
    assert marker in out
    assert all(getattr(i, "id", None) != "2" for i in out)


def test_count_html_files(tmp_path):
    exp = ContentExporter(str(tmp_path))
    exp.prepare_output_dir()
    exp.export(_item(id="1", url="/a"))
    exp.export(_item(id="2", url="/b"))
    assert ContentExporter.count_html_files(str(tmp_path)) == 2


def test_manifest_round_trip_and_delete(tmp_path):
    exp = ContentExporter(str(tmp_path))
    exp.prepare_output_dir()
    exp.export(_item(id="42", url="/recipe/cake"))
    exp.write_manifest()
    manifest = ContentExporter.read_manifest(str(tmp_path))
    assert manifest["42"] == "recipe/cake/index.html"
    assert exp.delete_by_id("42") is True
    assert not (tmp_path / "recipe" / "cake" / "index.html").exists()


def test_delete_by_url(tmp_path):
    exp = ContentExporter(str(tmp_path))
    exp.prepare_output_dir()
    exp.export(_item(url="/recipe/cake"))
    assert exp.delete_by_url("/recipe/cake") is True
    assert exp.delete_by_url("/recipe/cake") is False


def test_prepare_output_dir_clears_existing(tmp_path):
    d = tmp_path / "out"
    d.mkdir()
    (d / "stale.html").write_text("old")
    exp = ContentExporter(str(d))
    exp.prepare_output_dir()
    assert not (d / "stale.html").exists()
    assert os.path.isdir(d)
