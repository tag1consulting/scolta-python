"""Tests for MemoryBudget (ported behaviours from MemoryBudgetTest.php)."""

from scolta.index.memory_budget import MemoryBudget


def test_profiles():
    assert MemoryBudget.conservative().profile == "conservative"
    assert MemoryBudget.conservative().chunk_size() == 50
    assert MemoryBudget.balanced().chunk_size() == 200
    assert MemoryBudget.aggressive().chunk_size() == 500


def test_default_is_conservative():
    assert MemoryBudget.default().profile == "conservative"


def test_from_bytes_thresholds():
    assert MemoryBudget.from_bytes(768 * 1024 * 1024).profile == "aggressive"
    assert MemoryBudget.from_bytes(192 * 1024 * 1024).profile == "balanced"
    assert MemoryBudget.from_bytes(96 * 1024 * 1024).profile == "conservative"


def test_from_string_named():
    assert MemoryBudget.from_string("balanced").profile == "balanced"
    assert MemoryBudget.from_string("AGGRESSIVE").profile == "aggressive"


def test_from_string_byte_value():
    assert MemoryBudget.from_string("256M").profile == "balanced"
    assert MemoryBudget.from_string("1G").profile == "aggressive"


def test_from_string_unknown_falls_back_to_conservative():
    assert MemoryBudget.from_string("nonsense").profile == "conservative"


def test_with_chunk_size():
    b = MemoryBudget.conservative().with_chunk_size(123)
    assert b.chunk_size() == 123
    assert b.profile == "conservative"
    assert b.merge_open_file_handles() >= 123


def test_from_options_chunk_override():
    assert MemoryBudget.from_options("balanced", 100).chunk_size() == 100
    assert MemoryBudget.from_options("balanced").chunk_size() == 200


def test_token_cache_chunk_bytes_per_profile():
    assert MemoryBudget.conservative().token_cache_chunk_bytes() == 4 * 1024 * 1024
    assert MemoryBudget.aggressive().token_cache_chunk_bytes() == 64 * 1024 * 1024
