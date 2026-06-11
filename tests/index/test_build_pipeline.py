"""Tests for the build DTOs/coordinator (BuildIntent, BuildIntentFactory,
BuildResult, StatusReport, NullProgressReporter, BuildCoordinator)."""

import pytest

from scolta.index.build_intent import BuildIntent, BuildIntentFactory
from scolta.index.build_result import BuildResult, StatusReport
from scolta.index.coordinator import BuildCoordinator
from scolta.index.memory_budget import MemoryBudget
from scolta.index.progress import NullProgressReporter


def test_build_intent_modes():
    b = MemoryBudget.default()
    assert BuildIntent.fresh(10, b).mode == "fresh"
    assert BuildIntent.fresh(10, b).is_fresh() is True
    assert BuildIntent.restart(10, b).is_fresh() is True
    assert BuildIntent.resume(b).mode == "resume"
    assert BuildIntent.resume(b).is_fresh() is False
    assert BuildIntent.resume(b).total_pages is None


def test_build_intent_factory():
    b = MemoryBudget.default()
    assert BuildIntentFactory.from_flags(True, False, 5, b).mode == "resume"
    assert BuildIntentFactory.from_flags(False, True, 5, b).mode == "restart"
    assert BuildIntentFactory.from_flags(False, False, 5, b).mode == "fresh"


def test_status_report_to_build_result():
    sr = StatusReport(
        "1.0.0",
        "1.5.0",
        "python",
        42,
        3,
        50 * 1024 * 1024,
        96 * 1024 * 1024,
        1.5,
        "/out",
        success=True,
    )
    br = sr.to_build_result()
    assert isinstance(br, BuildResult)
    assert br.success is True
    assert br.page_count == 42
    assert "42 pages" in br.message


def test_status_report_failure_message():
    sr = StatusReport(
        "1.0.0", "1.5.0", "python", 0, 0, 0, 0, 0.1, "/out", success=False, error="boom"
    )
    assert sr.to_build_result().error == "boom"
    assert sr.to_build_result().message == "boom"


def test_null_progress_reporter_is_noop():
    r = NullProgressReporter()
    r.start(5, "x")
    r.advance(1, "y")
    r.finish("done")


def test_coordinator_prepare_fresh_then_resume(tmp_path):
    b = MemoryBudget.default()
    c = BuildCoordinator(str(tmp_path))
    c.prepare(BuildIntent.fresh(2, b))
    c.commit_chunk(0, {"pages": {0: {}}, "index": {}})
    c.release_lock_only()

    c2 = BuildCoordinator(str(tmp_path))
    manifest = c2.prepare(BuildIntent.resume(b))
    assert manifest["chunks_written"] == 1


def test_coordinator_resume_without_state_raises(tmp_path):
    with pytest.raises(RuntimeError, match="No resumable build"):
        BuildCoordinator(str(tmp_path)).prepare(BuildIntent.resume(MemoryBudget.default()))


def test_coordinator_fresh_rejected_when_running(tmp_path):
    b = MemoryBudget.default()
    c = BuildCoordinator(str(tmp_path))
    c.prepare(BuildIntent.fresh(1, b))  # holds the lock
    c2 = BuildCoordinator(str(tmp_path))
    with pytest.raises(RuntimeError, match="already running"):
        c2.prepare(BuildIntent.fresh(1, b))
