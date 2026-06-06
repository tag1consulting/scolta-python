"""Ported from tests/Config/MemoryBudgetConfigTest.php (deferred from Phase 1;
ports now that MemoryBudget exists)."""

from scolta.index.memory_budget import MemoryBudget
from scolta.memory_budget_config import MemoryBudgetConfig


def test_defaults_returns_conservative():
    cfg = MemoryBudgetConfig.defaults()
    assert cfg.profile() == "conservative"
    assert cfg.custom_bytes() is None


def test_load_valid_profile():
    assert MemoryBudgetConfig.load({"profile": "balanced"}).profile() == "balanced"


def test_load_invalid_profile_falls_back_to_conservative():
    assert MemoryBudgetConfig.load({"profile": "turbo"}).profile() == "conservative"


def test_load_custom_bytes():
    cfg = MemoryBudgetConfig.load({"profile": "conservative", "custom_bytes": 512 * 1024 * 1024})
    assert cfg.custom_bytes() == 512 * 1024 * 1024


def test_load_zero_custom_bytes_normalised_to_null():
    cfg = MemoryBudgetConfig.load({"profile": "conservative", "custom_bytes": 0})
    assert cfg.custom_bytes() is None


def test_to_memory_budget_named_profile():
    budget = MemoryBudgetConfig.load({"profile": "aggressive"}).to_memory_budget()
    assert isinstance(budget, MemoryBudget)
    assert budget.profile == "aggressive"


def test_to_memory_budget_custom_bytes():
    budget = MemoryBudgetConfig.load({"profile": "conservative", "custom_bytes": 768 * 1024 * 1024}).to_memory_budget()
    assert budget.profile == "aggressive"


def test_validate_passes_for_valid_profiles():
    for profile in ("conservative", "balanced", "aggressive"):
        assert MemoryBudgetConfig.load({"profile": profile}).validate() == []


def test_load_byte_string_profile():
    assert MemoryBudgetConfig.load({"profile": "256M"}).profile() == "256M"


def test_load_byte_string_not_normalised():
    assert MemoryBudgetConfig.load({"profile": "512M"}).profile() == "512M"


def test_load_chunk_size():
    assert MemoryBudgetConfig.load({"profile": "conservative", "chunk_size": 75}).chunk_size() == 75


def test_load_zero_chunk_size_normalised_to_null():
    assert MemoryBudgetConfig.load({"profile": "conservative", "chunk_size": 0}).chunk_size() is None


def test_load_null_chunk_size_is_null():
    assert MemoryBudgetConfig.load({"profile": "conservative"}).chunk_size() is None


def test_to_memory_budget_applies_chunk_size():
    budget = MemoryBudgetConfig.load({"profile": "conservative", "chunk_size": 75}).to_memory_budget()
    assert budget.chunk_size() == 75
    assert budget.total_budget_bytes() == MemoryBudget.conservative().total_budget_bytes()


def test_to_memory_budget_byte_string_with_chunk_size():
    budget = MemoryBudgetConfig.load({"profile": "256M", "chunk_size": 100}).to_memory_budget()
    assert budget.chunk_size() == 100


def test_to_array_includes_chunk_size():
    arr = MemoryBudgetConfig.load({"profile": "balanced", "chunk_size": 150}).to_array()
    assert arr["chunk_size"] == 150


def test_validate_accepts_named_and_byte_strings():
    for p in ("conservative", "balanced", "aggressive", "256M", "1G"):
        assert MemoryBudgetConfig.load({"profile": p}).validate() == []


def test_validate_rejects_nonsense_after_load_normalises():
    assert MemoryBudgetConfig.load({"profile": "turbo"}).validate() == []


def test_suggest_returns_dict():
    hint = MemoryBudgetConfig.defaults().suggest()
    assert "profile" in hint
    assert "reason" in hint
    assert "confidence" in hint
    assert hint["profile"] in ("conservative", "balanced", "aggressive")


def test_to_array():
    arr = MemoryBudgetConfig.load({"profile": "balanced", "custom_bytes": None}).to_array()
    assert arr["profile"] == "balanced"
    assert arr["custom_bytes"] is None


def test_from_cli_and_config_uses_cli_when_both_present():
    budget = MemoryBudgetConfig.from_cli_and_config("aggressive", "75", lambda: {"profile": "conservative", "chunk_size": 50})
    assert budget.profile == "aggressive"
    assert budget.chunk_size() == 75


def test_from_cli_and_config_falls_back_to_saved_profile():
    budget = MemoryBudgetConfig.from_cli_and_config(None, None, lambda: {"profile": "balanced", "chunk_size": None})
    assert budget.profile == "balanced"


def test_from_cli_and_config_falls_back_to_conservative_when_empty():
    assert MemoryBudgetConfig.from_cli_and_config(None, None, lambda: {}).profile == "conservative"


def test_from_cli_and_config_cli_chunk_overrides_saved():
    budget = MemoryBudgetConfig.from_cli_and_config(None, "200", lambda: {"profile": "conservative", "chunk_size": 50})
    assert budget.chunk_size() == 200


def test_from_cli_and_config_zero_chunk_uses_profile_default():
    budget = MemoryBudgetConfig.from_cli_and_config(None, "0", lambda: {})
    assert budget.chunk_size() == 50


def test_from_cli_and_config_accepts_byte_string_budget():
    assert isinstance(MemoryBudgetConfig.from_cli_and_config("256M", None, lambda: {}), MemoryBudget)
