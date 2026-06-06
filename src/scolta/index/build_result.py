"""BuildResult + StatusReport DTOs (ported 1:1)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BuildResult:
    success: bool
    message: str
    page_count: int
    file_count: int
    elapsed_seconds: float
    error: str | None = None


@dataclass(frozen=True)
class StatusReport:
    version: str
    pagefind_version: str
    resolved_indexer: str
    pages_processed: int
    chunks_written: int
    peak_memory_bytes: int
    memory_budget_bytes: int
    duration_seconds: float
    output_dir: str
    warnings: str | None = None
    success: bool = True
    error: str | None = None

    def to_build_result(self) -> BuildResult:
        peak_mb = round(self.peak_memory_bytes / 1_048_576, 1)
        message = (
            f"Built index for {self.pages_processed} pages "
            f"({self.chunks_written} chunks, peak {peak_mb} MB)"
            if self.success
            else (self.error or "Build failed")
        )
        return BuildResult(
            success=self.success,
            message=message,
            page_count=self.pages_processed,
            file_count=self.chunks_written,
            elapsed_seconds=self.duration_seconds,
            error=self.error,
        )

    def peak_memory_mb(self) -> str:
        return f"{round(self.peak_memory_bytes / 1_048_576, 1)} MB"
