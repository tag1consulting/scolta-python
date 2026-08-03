"""Ported from tests/Health/HealthCheckerTest.php + SetupCheck behaviour."""

import time

from scolta.ai.amazee import KeyExpiryRecovery
from scolta.cache import InMemoryCacheDriver
from scolta.config import ScoltaConfig
from scolta.health import HealthChecker, SetupCheck


def test_check_returns_expected_structure(tmp_path):
    config = ScoltaConfig.from_dict({"ai_provider": "anthropic", "ai_api_key": "sk-test"})
    result = HealthChecker(config, str(tmp_path), None, None).check()
    for key in (
        "status",
        "ai_configured",
        "ai_usable",
        "ai_auth_failing",
        "ai_provider",
        "pagefind_available",
        "wasm_available",
        "index_exists",
        "pagefind",
        "wasm",
    ):
        assert key in result


def test_healthy_system_with_index(tmp_path):
    (tmp_path / "pagefind.js").write_text("// pagefind")
    config = ScoltaConfig.from_dict({"ai_provider": "anthropic", "ai_api_key": "sk-test-key"})
    result = HealthChecker(config, str(tmp_path), None, None).check()
    assert result["status"] == "ok"
    assert result["ai_configured"] is True
    assert result["index_exists"] is True


def test_degraded_without_index(tmp_path):
    config = ScoltaConfig.from_dict({"ai_provider": "anthropic", "ai_api_key": "sk-test-key"})
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
    config = ScoltaConfig.from_dict({"ai_provider": "anthropic", "ai_api_key": "sk"})
    assert HealthChecker(config, str(tmp_path), None, None).check()["index_exists"] is True


def test_binary_indexer_upgrade_message_when_unavailable(tmp_path):
    config = ScoltaConfig.from_dict(
        {"ai_provider": "anthropic", "ai_api_key": "sk", "indexer": "binary"}
    )
    result = HealthChecker(
        config, str(tmp_path), "/nonexistent/pagefind-xyz", "/nonexistent"
    ).check()
    if not result["pagefind_available"]:
        assert result["indexer_upgrade_available"] is True
        assert result["indexer_active"] == "python"
        assert "Pagefind binary not found" in result["indexer_upgrade_message"]


# -- AI usability: "configured" must not imply "usable" ------------------------
#
# Regression (django demo, 2026-06-09): an expired Amazee trial key kept
# health reporting ai_configured: true for ~24h while every AI call
# returned 400 expired_key.


def test_stored_but_auth_failing_credentials_report_ai_not_usable(tmp_path):
    (tmp_path / "pagefind.js").write_text("// pagefind")
    cache = InMemoryCacheDriver()
    cache.set(KeyExpiryRecovery.CACHE_KEY_AUTH_FAILURE, time.time(), 3600)

    config = ScoltaConfig.from_dict(
        {"ai_provider": "anthropic", "ai_api_key": "sk-stored-but-expired"}
    )
    result = HealthChecker(config, str(tmp_path), None, None, cache).check()

    assert result["ai_configured"] is True, "Credentials ARE present — configured stays true"
    assert result["ai_auth_failing"] is True
    assert result["ai_usable"] is False, "Known-expired credentials must not report AI as usable"
    assert result["status"] == "degraded"


def test_configured_and_not_auth_failing_reports_usable(tmp_path):
    (tmp_path / "pagefind.js").write_text("// pagefind")

    config = ScoltaConfig.from_dict({"ai_provider": "anthropic", "ai_api_key": "sk-good"})
    result = HealthChecker(config, str(tmp_path), None, None, InMemoryCacheDriver()).check()

    assert result["ai_usable"] is True
    assert result["ai_auth_failing"] is False
    assert result["status"] == "ok"


def test_without_cache_ai_usable_mirrors_configured(tmp_path):
    # Callers that have not wired recovery yet pass no cache; behavior is
    # unchanged from before the ai_usable field existed.
    (tmp_path / "pagefind.js").write_text("// pagefind")

    config = ScoltaConfig.from_dict({"ai_provider": "anthropic", "ai_api_key": "sk-good"})
    result = HealthChecker(config, str(tmp_path), None, None).check()

    assert result["ai_usable"] is True
    assert result["ai_auth_failing"] is False
    assert result["status"] == "ok"


def test_cleared_auth_failure_marker_restores_usable(tmp_path):
    (tmp_path / "pagefind.js").write_text("// pagefind")
    cache = InMemoryCacheDriver()
    # KeyExpiryRecovery clears the marker by overwriting it with False.
    cache.set(KeyExpiryRecovery.CACHE_KEY_AUTH_FAILURE, False, 1)

    config = ScoltaConfig.from_dict({"ai_provider": "anthropic", "ai_api_key": "sk-recovered"})
    result = HealthChecker(config, str(tmp_path), None, None, cache).check()

    assert result["ai_usable"] is True
    assert result["status"] == "ok"


def test_stale_auth_failure_marker_ages_out(tmp_path):
    # Python adaptation: markers carry their timestamp and age out on read,
    # because the in-process cache driver does not enforce TTL eviction.
    (tmp_path / "pagefind.js").write_text("// pagefind")
    cache = InMemoryCacheDriver()
    cache.set(
        KeyExpiryRecovery.CACHE_KEY_AUTH_FAILURE,
        time.time() - KeyExpiryRecovery.AUTH_FAILURE_TTL - 1,
        3600,
    )

    config = ScoltaConfig.from_dict({"ai_provider": "anthropic", "ai_api_key": "sk-good"})
    result = HealthChecker(config, str(tmp_path), None, None, cache).check()

    assert result["ai_usable"] is True
    assert result["ai_auth_failing"] is False


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
