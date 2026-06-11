"""The chunk-loop indexing pipeline (port of ``IndexBuildOrchestrator``).

prepare -> chunk-loop -> merge -> write -> atomic-swap -> verify, with
memory-yield exits (``memory_abort`` mid-loop, ``index_only_complete`` after
indexing) and resume. The token cache makes rebuilds cheap; cross-build caches
live in their own subdir so a fresh-build cleanup never eats them.
"""

from __future__ import annotations

import gc
import glob
import json
import logging
import os
import time
from collections.abc import Callable, Iterable
from types import SimpleNamespace

from ..storage import FilesystemDriver, StorageDriver
from .build_intent import BuildIntent
from .build_result import StatusReport
from .cached_reference import CachedContentReference
from .cbor import CborEncoder
from .coordinator import BuildCoordinator
from .fingerprint import content_hash
from .inverted_index_builder import InvertedIndexBuilder
from .memory_budget import MemoryBudget
from .memory_telemetry import MemoryTelemetry
from .merger import IndexMerger
from .page_word_cache import PageWordCache
from .progress import NullProgressReporter, ProgressReporter
from .stemmer import Stemmer
from .streaming_format_writer import StreamingFormatWriter
from .supported_versions import SupportedVersions
from .timestamp_manifest import TimestampManifest
from .tokenizer import Tokenizer

_VERSION = "1.0.0"
_NULL_LOGGER = logging.getLogger("scolta.index")
_CACHE_SUBDIR = "cache"


def _proxy(page) -> SimpleNamespace:
    return SimpleNamespace(
        id=page.id,
        url=page.url,
        date=page.date,
        site_name=page.site_name,
        language=page.language,
        filters=page.filters,
        sortable=page.sortable,
    )


def atomic_swap(storage, output_dir: str) -> None:
    """Swap the freshly built index into place, keeping the previous index
    recoverable: if the final move fails, the old index is restored instead of
    leaving the site with no ``pagefind/`` directory at all."""
    build_dir = os.path.join(output_dir, ".scolta-building")
    final_dir = os.path.join(output_dir, "pagefind")
    old_dir = os.path.join(output_dir, ".scolta-old")
    new_dir = os.path.join(output_dir, ".scolta-new")

    if not storage.exists(build_dir):
        raise RuntimeError("Build directory does not exist: " + build_dir)
    storage.move(build_dir, new_dir)
    had_previous = storage.exists(final_dir)
    if had_previous:
        storage.move(final_dir, old_dir)
    try:
        storage.move(new_dir, final_dir)
    except Exception:
        if had_previous:
            storage.move(old_dir, final_dir)
        raise
    if storage.exists(old_dir):
        storage.delete_directory(old_dir)


class IndexBuildOrchestrator:
    def __init__(
        self,
        state_dir: str,
        output_dir: str,
        hmac_secret: str | None = None,
        language: str = "en",
        storage: StorageDriver | None = None,
        memory_pressure_probe: Callable[[], bool] | None = None,
    ) -> None:
        normalized = output_dir.rstrip("/")
        if normalized.endswith("/pagefind"):
            normalized = normalized[: -len("/pagefind")]
            self._output_dir_warning = (
                "[scolta] output_dir already ends with '/pagefind'. The '/pagefind' suffix is "
                "appended automatically — set output_dir to the parent directory to silence this warning."
            )
        else:
            self._output_dir_warning = None
        self.output_dir = normalized

        self._hmac_secret = hmac_secret
        self._memory_pressure_probe = memory_pressure_probe
        self.coordinator = BuildCoordinator(state_dir, hmac_secret)
        self.builder = InvertedIndexBuilder(Tokenizer(), Stemmer(language))
        self.merger = IndexMerger()
        self.storage = storage or FilesystemDriver()
        cache_dir = os.path.join(state_dir, _CACHE_SUBDIR)
        self.cache = PageWordCache(
            cache_dir,
            self.storage,
            max_write_buffer_bytes=MemoryBudget.default().token_cache_chunk_bytes(),
        )
        self.ts_manifest = TimestampManifest(cache_dir, self.storage)

    def get_timestamp_manifest(self) -> TimestampManifest:
        return self.ts_manifest

    def build(
        self,
        intent: BuildIntent,
        pages: Iterable,
        logger=None,
        progress: ProgressReporter | None = None,
        force: bool = False,
    ) -> StatusReport:
        logger = logger if logger is not None else _NULL_LOGGER
        progress = progress or NullProgressReporter()
        if self._output_dir_warning is not None:
            logger.warning(self._output_dir_warning)
        logger.info("[scolta] Using Python indexer.")
        start_time = time.monotonic()
        telemetry = MemoryTelemetry(logger, intent.memory_budget)

        try:
            manifest = self.coordinator.prepare(intent)
            telemetry.emit("build_start", {"mode": intent.mode})

            budget = intent.memory_budget
            chunk_size = budget.chunk_size()
            total_pages = (
                intent.total_pages
                if intent.total_pages is not None
                else int(manifest.get("total_pages", 0))
            )

            start_chunk = 0
            current_offset = 0
            if intent.mode == "resume":
                start_chunk = int(manifest.get("chunks_written", 0))
                current_offset = int(manifest.get("pages_processed", 0))
                logger.info(
                    "[scolta] Resuming from chunk %d, page offset %d.", start_chunk, current_offset
                )

            total_chunks = -(-total_pages // chunk_size) if total_pages > 0 else 1
            progress.start(total_chunks, "Indexing")

            chunk: list = []
            chunk_num = start_chunk
            pages_in_run = 0

            for page in pages:
                if isinstance(page, CachedContentReference):
                    token_data = self.cache.get(page.content_hash)
                    if token_data is not None:
                        self.ts_manifest.mark_seen(page.entity_key)
                        chunk.append({"item": _proxy(page), "tokenData": token_data})
                else:
                    h = content_hash(page)
                    token_data = self.cache.get(h) if not force else None
                    if token_data is None:
                        token_data = self.builder.tokenize_item(page)
                        if token_data is not None:
                            self.cache.put(h, token_data)
                    if token_data is not None:
                        chunk.append({"item": _proxy(page), "tokenData": token_data})

                if len(chunk) >= chunk_size:
                    partial = self.builder.build_from_token_data(chunk, current_offset)
                    current_offset += len(partial["pages"])
                    pages_in_run += len(partial["pages"])
                    self.coordinator.commit_chunk(chunk_num, partial)
                    progress.advance(1, f"Chunk {chunk_num} ({pages_in_run} pages)")
                    chunk_num += 1
                    chunk = []
                    del partial
                    gc.collect()

                    if self._under_memory_pressure(telemetry):
                        committed_chunks = len(self.coordinator.chunk_files())
                        committed_pages = self.coordinator.build_state().get_pages_processed()
                        self.cache.prune_and_save()
                        self.ts_manifest.prune_and_save()
                        self.coordinator.release_lock_only()
                        logger.info(
                            "[scolta] Memory pressure after chunk %d — yielding for restart (%d pages committed).",
                            chunk_num - 1,
                            committed_pages,
                        )
                        return self._report(
                            telemetry,
                            budget,
                            committed_pages,
                            committed_chunks,
                            start_time,
                            success=False,
                            error="memory_abort",
                        )

            if chunk:
                partial = self.builder.build_from_token_data(chunk, current_offset)
                pages_in_run += len(partial["pages"])
                self.coordinator.commit_chunk(chunk_num, partial)
                progress.advance(1, f"Chunk {chunk_num} ({pages_in_run} pages)")
                del partial, chunk
                gc.collect()

            progress.finish(f"{pages_in_run} pages indexed")

            limit_bytes = telemetry.effective_limit_bytes()
            segment_bytes = telemetry.get_current_rss_bytes()
            if limit_bytes > 0 and segment_bytes >= int(limit_bytes * 0.75):
                self.cache.prune_and_save()
                self.ts_manifest.prune_and_save()
                self.coordinator.release_lock_only()
                logger.warning(
                    "[scolta] RSS high after indexing. Merge deferred — run finalize to complete."
                )
                return self._report(
                    telemetry,
                    budget,
                    pages_in_run,
                    chunk_num,
                    start_time,
                    success=False,
                    error="index_only_complete",
                )

            chunk_files = self.coordinator.chunk_files()
            stream_writer = StreamingFormatWriter(
                CborEncoder(), flush_bytes=budget.fragment_flush_bytes()
            )
            stream_writer.begin_write(self.output_dir)
            self.merger.merge_streaming(chunk_files, stream_writer, budget)
            stream_writer.end_write()

            self._atomic_swap()

            total_processed = self.coordinator.pages_processed()
            pages_for_report = total_processed if total_processed > 0 else pages_in_run
            chunks_written = len(chunk_files)

            self._verify_output_has_fragments(pages_for_report)
            self.coordinator.release()
            self.cache.prune_and_save()
            self.ts_manifest.prune_and_save()

            return self._report(
                telemetry, budget, pages_for_report, chunks_written, start_time, success=True
            )

        except Exception as exc:  # noqa: BLE001 - mirror PHP catch-all
            # The report flattens the failure to str(exc); keep the traceback
            # in the log so build failures stay diagnosable.
            logger.exception("[scolta] Index build failed: %s", exc)
            try:
                self.coordinator.release_lock_only()
            except Exception:
                pass
            is_memory_abort = isinstance(exc, RuntimeError) and "exceeds safe threshold" in str(exc)
            committed_chunks = 0
            committed_pages = 0
            if is_memory_abort:
                try:
                    committed_chunks = len(self.coordinator.chunk_files())
                    committed_pages = self.coordinator.build_state().get_pages_processed()
                except Exception:
                    pass
            return self._report(
                telemetry,
                intent.memory_budget,
                committed_pages,
                committed_chunks,
                start_time,
                success=False,
                error="memory_abort" if is_memory_abort else str(exc),
            )

    def finalize(self, budget: MemoryBudget, logger=None) -> StatusReport:
        logger = logger if logger is not None else _NULL_LOGGER
        if self._output_dir_warning is not None:
            logger.warning(self._output_dir_warning)
        telemetry = MemoryTelemetry(logger, budget)
        start_time = time.monotonic()
        try:
            chunk_files = self.coordinator.chunk_files()
            if not chunk_files:
                return self._report(
                    telemetry,
                    budget,
                    0,
                    0,
                    start_time,
                    success=False,
                    error="No chunk files found in state directory.",
                )
            stream_writer = StreamingFormatWriter(
                CborEncoder(), flush_bytes=budget.fragment_flush_bytes()
            )
            stream_writer.begin_write(self.output_dir)
            self.merger.merge_streaming(chunk_files, stream_writer, budget)
            stream_writer.end_write()
            self._atomic_swap()
            pages_processed = self.coordinator.pages_processed()
            self._verify_output_has_fragments(pages_processed)
            self.coordinator.release()
            return self._report(
                telemetry, budget, pages_processed, len(chunk_files), start_time, success=True
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("[scolta] Index finalize failed: %s", exc)
            try:
                self.coordinator.release_lock_only()
            except Exception:
                pass
            return self._report(telemetry, budget, 0, 0, start_time, success=False, error=str(exc))

    # -- helpers --

    def _report(
        self, telemetry, budget, pages, chunks, start_time, success, error=None
    ) -> StatusReport:
        return StatusReport(
            version=_VERSION,
            pagefind_version=SupportedVersions.get_version_for_metadata(),
            resolved_indexer="python",
            pages_processed=pages,
            chunks_written=chunks,
            peak_memory_bytes=telemetry.get_peak_rss_bytes(),
            memory_budget_bytes=budget.total_budget_bytes(),
            duration_seconds=round(time.monotonic() - start_time, 3),
            output_dir=self.output_dir,
            success=success,
            error=error,
        )

    def _atomic_swap(self) -> None:
        atomic_swap(self.storage, self.output_dir)

    def _under_memory_pressure(self, telemetry: MemoryTelemetry) -> bool:
        if self._memory_pressure_probe is not None:
            return self._memory_pressure_probe()
        limit = telemetry.effective_limit_bytes()
        if limit <= 0:
            return False
        return telemetry.get_current_rss_bytes() >= int(limit * 0.75)

    def _verify_output_has_fragments(self, pages_processed: int) -> None:
        if pages_processed == 0:
            return
        fragment_dir = os.path.join(self.output_dir, "pagefind", "fragment")
        count = (
            len(glob.glob(os.path.join(fragment_dir, "*.pf_fragment")))
            if os.path.isdir(fragment_dir)
            else 0
        )
        if count == 0:
            raise RuntimeError(
                f"Build processed {pages_processed} pages but the output index contains zero fragment files. "
                "The write may have failed silently. Check filesystem permissions and available space."
            )
        self.verify_index_complete(self.output_dir)

    @staticmethod
    def verify_index_complete(output_dir: str) -> None:
        entry_path = os.path.join(output_dir, "pagefind", "pagefind-entry.json")
        if not os.path.exists(entry_path):
            raise RuntimeError(
                f"Index verification failed: pagefind-entry.json not found at {entry_path}. Do not exit 0."
            )
        try:
            with open(entry_path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError) as exc:
            raise RuntimeError(
                f"Index verification failed: cannot read/parse {entry_path}."
            ) from exc
        if not isinstance(data, dict) or "version" not in data or "languages" not in data:
            raise RuntimeError(
                "Index verification failed: pagefind-entry.json is malformed "
                "(missing 'version' or 'languages')."
            )
