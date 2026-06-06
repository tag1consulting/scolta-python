"""Ported from tests/Health/HealthCheckerTest.php + SetupCheck behaviour."""

from scolta.config import ScoltaConfig
from scolta.health import HealthChecker, SetupCheck


def test_check_returns_expected_structure(tmp_path):
    config = ScoltaConfig.from_dict({"ai_api_key": "sk-test"})
    result = HealthChecker(config, str(tmp_path), None, None).check()
    for key in ("status", "ai_configured", "ai_provider", "pagefind_available",
                "wasm_available", "index_exists", "pagefind", "wasm"):
        assert key in result


def test_healthy_system_with_index(tmp_path):
    (tmp_path / "pagefind.js").write_text("// pagefind")
    config = ScoltaConfig.from_dict({"ai_api_key": "sk-test-key"})
    result = HealthChecker(config, str(tmp_path), None, None).check()
    assert result["status"] == "ok"
    assert result["ai_configured"] is True
    assert result["index_exists"] is True


def test_degraded_without_index(tmp_path):
    config = ScoltaConfig.from_dict({"ai_api_key": "sk-test-key"})
    result = HealthChecker(config, str(tmp_path), None, None).check()
    assert result["status"] == "degraded"
    assert result["index_exists"] is False


def test_degraded_without_ai_key(tmp_path):
    (tmp_path / "pagefind.js").write_text("// pagefind")
    result = HealthChecker(ScoltaConfig(), str(tmp_path), None, None).check()
    assert result["status"] == "degraded"
    assert result["ai_configured"] is False


def test_pagefind_subdir_index_detected(tmp_path):
    (tmp_path / "pagefind").mkdir()
    (tmp_path / "pagefind" / "pagefind.js").write_text("// pagefind")
    config = ScoltaConfig.from_dict({"ai_api_key": "sk"})
    assert HealthChecker(config, str(tmp_path), None, None).check()["index_exists"] is True


def test_binary_indexer_upgrade_message_when_unavailable(tmp_path):
    config = ScoltaConfig.from_dict({"ai_api_key": "sk", "indexer": "binary"})
    result = HealthChecker(config, str(tmp_path), "/nonexistent/pagefind-xyz", "/nonexistent").check()
    if not result["pagefind_available"]:
        assert result["indexer_upgrade_available"] is True
        assert result["indexer_active"] == "python"
        assert "Pagefind binary not found" in result["indexer_upgrade_message"]


# -- SetupCheck ---------------------------------------------------------------


def test_setup_check_python_version_passes():
    results = SetupCheck.run(ai_api_key="sk")
    by_name = {r["name"]: r for r in results}
    assert by_name["Python version"]["status"] == "pass"
    assert by_name["AI API key"]["status"] == "pass"
    # Browser WASM assets are vendored, so this passes.
    assert by_name["Browser WASM"]["status"] == "pass"


def test_setup_check_no_ai_key_warns():
    by_name = {r["name"]: r for r in SetupCheck.run()}
    assert by_name["AI API key"]["status"] == "warn"


def test_run_all_and_exit_code(tmp_path):
    results = SetupCheck.run_all(str(tmp_path))
    assert any(r["message"] for r in results)
    assert SetupCheck.exit_code(results) == 0


def test_exit_code_nonzero_on_error():
    assert SetupCheck.exit_code([{"level": "error", "message": "x"}]) == 1
    assert SetupCheck.exit_code([{"status": "fail", "message": "x"}]) == 1
