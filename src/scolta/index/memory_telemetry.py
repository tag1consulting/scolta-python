"""Memory telemetry + budget suggestion.

Ports ``MemoryTelemetry`` and ``MemoryBudgetSuggestion``. Behaviour-matched
rather than byte-translated (Python's memory model differs): RSS via psutil,
peak via resource/VmHWM, cgroup-aware effective limit, warn at 75% / abort at
90%. Memory closures are injectable for tests (the orchestrator's yield/abort
paths rely on this).
"""

from __future__ import annotations

import logging
import resource
import sys
import time
from collections.abc import Callable

_MIB = 1024 * 1024
_DEFAULT_LOGGER = logging.getLogger("scolta.index")


def _read_proc_rss() -> int | None:
    try:
        with open("/proc/self/status") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) * 1024
    except OSError:
        return None
    return None


def _read_proc_peak_rss() -> int | None:
    try:
        with open("/proc/self/status") as fh:
            for line in fh:
                if line.startswith("VmHWM:"):
                    return int(line.split()[1]) * 1024
    except OSError:
        return None
    return None


def _current_rss() -> int:
    rss = _read_proc_rss()
    if rss is not None:
        return rss
    try:
        import psutil

        return psutil.Process().memory_info().rss
    except Exception:
        # ru_maxrss: bytes on macOS, KB on Linux.
        maxrss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return maxrss if sys.platform == "darwin" else maxrss * 1024


def _peak_rss() -> int:
    peak = _read_proc_peak_rss()
    if peak is not None:
        return peak
    maxrss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return maxrss if sys.platform == "darwin" else maxrss * 1024


def _read_cgroup_limit() -> int:
    try:
        with open("/sys/fs/cgroup/memory.max") as fh:
            v = fh.read().strip()
        if v != "max" and v.isdigit():
            return int(v)
        return 0
    except OSError:
        pass
    try:
        with open("/sys/fs/cgroup/memory/memory.limit_in_bytes") as fh:
            val = int(fh.read().strip())
        if 0 < val < 1_099_511_627_776:
            return val
    except (OSError, ValueError):
        pass
    return 0


class MemoryTelemetry:
    def __init__(
        self,
        logger=None,
        budget=None,
        get_current_memory: Callable[[], int] | None = None,
        get_peak_memory: Callable[[], int] | None = None,
        limit_bytes: int | None = None,
    ) -> None:
        self.logger = logger if logger is not None else _DEFAULT_LOGGER
        self.budget = budget
        self.limit_bytes = limit_bytes if limit_bytes is not None else _read_cgroup_limit()
        self._build_start = time.monotonic()
        self._get_current = get_current_memory or _current_rss
        self._get_peak = get_peak_memory or _peak_rss

    def emit(self, phase: str, extra: dict | None = None) -> None:
        current = self._get_current()
        pct = round(current / self.limit_bytes * 100, 1) if self.limit_bytes > 0 else 0.0
        if pct >= 90.0 and self.limit_bytes > 0:
            limit_mb = round(self.limit_bytes / _MIB, 1)
            self.logger.error(
                "[scolta] Memory at %s%% of limit (%.1f MB) at phase %s. Aborting.",
                pct, current / _MIB, phase,
            )
            raise RuntimeError(
                f"Memory usage ({pct}% of {limit_mb} MB limit) exceeds safe threshold "
                f"at phase '{phase}'. Use --memory-budget=conservative or reduce chunk size."
            )
        if pct >= 75.0 and self.limit_bytes > 0:
            self.logger.warning("[scolta] Memory at %s%% of limit at phase %s.", pct, phase)
        else:
            self.logger.info("[scolta] Phase %s (%s%% of limit).", phase, pct)

    def get_current_rss_bytes(self) -> int:
        return self._get_current()

    def get_peak_rss_bytes(self) -> int:
        return self._get_peak()

    def effective_limit_bytes(self) -> int:
        return self.limit_bytes


class MemoryBudgetSuggestion:
    """Advisory profile recommendation. Without a PHP-style memory_limit, this
    reads the cgroup limit (containers) and otherwise recommends conservative."""

    @staticmethod
    def suggest(limit_bytes: int | None = None) -> dict:
        bytes_ = limit_bytes if limit_bytes is not None else (_read_cgroup_limit() or None)
        if bytes_ is None:
            return {
                "profile": "conservative",
                "reason": "Memory limit could not be determined. The conservative profile is the safe default.",
                "detected_limit_bytes": None,
                "confidence": "low",
            }
        if bytes_ < 0:
            return {
                "profile": "aggressive",
                "reason": "Memory limit is unlimited. The aggressive profile maximises throughput.",
                "detected_limit_bytes": None,
                "confidence": "medium",
            }
        mb = round(bytes_ / _MIB)
        if bytes_ >= 768 * _MIB:
            return {"profile": "aggressive", "reason": f"Memory limit is {mb}MB. The aggressive profile will maximise throughput.", "detected_limit_bytes": bytes_, "confidence": "high"}
        if bytes_ >= 192 * _MIB:
            return {"profile": "balanced", "reason": f"Memory limit is {mb}MB. The balanced profile is recommended.", "detected_limit_bytes": bytes_, "confidence": "high"}
        confidence = "low" if bytes_ < 64 * _MIB else "high"
        return {"profile": "conservative", "reason": f"Memory limit is {mb}MB. The conservative profile is recommended.", "detected_limit_bytes": bytes_, "confidence": confidence}

    @staticmethod
    def check_profile_fit(profile: str, limit_bytes: int | None = None) -> dict:
        from .memory_budget import MemoryBudget

        budget = MemoryBudget.from_string(profile).total_budget_bytes()
        resolved = limit_bytes if limit_bytes is not None else (_read_cgroup_limit() or None)
        if resolved is None or resolved < 0:
            return {"status": "safe", "warning": None, "profile_budget_bytes": budget, "limit_bytes": resolved}
        if budget <= 0.70 * resolved:
            return {"status": "safe", "warning": None, "profile_budget_bytes": budget, "limit_bytes": resolved}
        budget_mb = round(budget / _MIB)
        limit_mb = round(resolved / _MIB)
        warning = (
            f"Scolta's internal allocation budget for this profile is approximately {budget_mb} MB, "
            f"but the memory limit is only {limit_mb} MB. Choose a smaller profile or raise the limit."
        )
        return {"status": "warn", "warning": warning, "profile_budget_bytes": budget, "limit_bytes": resolved}

    @staticmethod
    def get_memory_limit_text(limit_bytes: int | None = None) -> str:
        resolved = limit_bytes if limit_bytes is not None else (_read_cgroup_limit() or None)
        if resolved is None:
            return "unknown (could not read limit)"
        if resolved < 0:
            return "unlimited"
        return f"{round(resolved / _MIB)} MB"
