"""Tests for ContentItem / TrackerRecord (ported from Export/ContentItem.php
constructor + cloneWith semantics)."""

from datetime import datetime

from scolta.content import ContentItem, TrackerRecord


def _item(**overrides):
    base = {
        "id": "1",
        "title": "Title",
        "body_html": "<p>body</p>",
        "url": "/page",
        "date": "2024-01-01",
    }
    base.update(overrides)
    return ContentItem(**base)


def test_relative_url_unchanged():
    assert _item(url="/foo/bar").url == "/foo/bar"


def test_absolute_url_stripped_to_path():
    item = _item(url="https://myapp.ddev.site/foo/bar")
    assert item.url == "/foo/bar"


def test_absolute_url_keeps_query_and_fragment():
    item = _item(url="https://example.com/p?q=1#frag")
    assert item.url == "/p?q=1#frag"


def test_absolute_url_root_path():
    item = _item(url="https://example.com")
    assert item.url == "/"


def test_clone_with_carries_all_fields_forward():
    item = _item(metadata={"price": "9.99"}, sortable={"rating": "4.5"})
    cloned = item.clone_with(body_html="<p>new</p>")
    assert cloned.body_html == "<p>new</p>"
    # Fields not overridden are preserved.
    assert cloned.metadata == {"price": "9.99"}
    assert cloned.sortable == {"rating": "4.5"}
    assert cloned.id == "1"


def test_clone_with_overrides_url_is_renormalized():
    item = _item()
    cloned = item.clone_with(url="https://example.com/new")
    assert cloned.url == "/new"


def test_tracker_record_defaults():
    rec = TrackerRecord(content_id="42", content_type="post")
    assert rec.action == TrackerRecord.ACTION_INDEX
    assert rec.changed_at is None


def test_tracker_record_delete_action():
    now = datetime(2024, 6, 1)
    rec = TrackerRecord(
        content_id="42",
        content_type="post",
        action=TrackerRecord.ACTION_DELETE,
        changed_at=now,
    )
    assert rec.action == "delete"
    assert rec.changed_at == now
