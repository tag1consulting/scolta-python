"""Build state-machine coordinator (port of ``BuildCoordinator``)."""

from __future__ import annotations

from .build_intent import BuildIntent
from .build_state import BuildState


class BuildCoordinator:
    def __init__(self, state_dir: str, hmac_secret: str | None = None) -> None:
        self.state_dir = state_dir
        self._state = BuildState(state_dir, hmac_secret)

    def prepare(self, intent: BuildIntent) -> dict:
        if intent.is_fresh():
            if self._state.is_running():
                raise RuntimeError(
                    "Another index build is already running. Wait for it to complete, "
                    "or kill the process and retry with --restart."
                )
            self._state.cleanup()
            manifest = {
                "total_pages": intent.total_pages or 0,
                "chunk_size": intent.memory_budget.chunk_size(),
                "language": intent.source_meta.get("language", "en"),
                "fingerprint": intent.source_meta.get("fingerprint", ""),
                **intent.source_meta,
            }
            if not self._state.initiate_build(manifest):
                raise RuntimeError(
                    "Failed to acquire build lock — another process may have just started."
                )
            return manifest

        manifest = self._state.should_resume()
        if manifest is None:
            raise RuntimeError(
                "No resumable build found in state directory. "
                "Run without --resume to start a fresh build."
            )
        if not self._state.initiate_build(manifest):
            raise RuntimeError("Failed to re-acquire build lock for resume.")
        return manifest

    def commit_chunk(self, chunk_number: int, partial: dict) -> None:
        self._state.record_chunk(chunk_number, partial)

    def chunk_files(self) -> list[str]:
        return self._state.get_chunk_files()

    def pages_processed(self) -> int:
        return self._state.get_pages_processed()

    def build_state(self) -> BuildState:
        return self._state

    def release(self) -> None:
        self._state.release_lock()
        self._state.cleanup()

    def release_lock_only(self) -> None:
        self._state.release_lock_only()
