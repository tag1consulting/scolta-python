"""Tests for the cache drivers (ported from Cache/NullCacheDriver.php behaviour)."""

from scolta.cache import InMemoryCacheDriver, NullCacheDriver


def test_null_driver_get_returns_none():
    d = NullCacheDriver()
    d.set("k", "v", 60)
    assert d.get("k") is None


def test_in_memory_driver_roundtrip():
    d = InMemoryCacheDriver()
    assert d.get("missing") is None
    d.set("k", {"a": 1}, 60)
    assert d.get("k") == {"a": 1}
