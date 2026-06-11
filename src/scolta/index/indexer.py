"""Python indexer facade (port of ``PhpIndexer`` -> ``PythonIndexer``).

Thin orchestration over BuildCoordinator / InvertedIndexBuilder / IndexMerger /
PageWordCache with the per-chunk processing API the queue-based adapters use
(process_chunk + finalize). New code should prefer IndexBuildOrchestrator.build.
"""

from __future__ import annotations

import glob
import logging
import os
import time
from collections.abc import Iterator

from ..storage import FilesystemDriver, StorageDriver
from .build_intent import BuildIntent
from .build_result import BuildResult
from .cbor import CborEncoder
from .coordinator import BuildCoordinator
from .fingerprint import compute_fingerprint, content_hash
from .inverted_index_builder import InvertedIndexBuilder
from .memory_budget import MemoryBudget
from .merger import IndexMerger
from .orchestrator import IndexBuildOrchestrator, _proxy, atomic_swap
from .page_word_cache import PageWordCache
from .stemmer import Stemmer
from .streaming_format_writer import StreamingFormatWriter
from .tokenizer import Tokenizer

_CACHE_SUBDIR = "cache"
_LOGGER = logging.getLogger("scolta.index")


class PythonIndexer:
    def __init__(
        self,
        state_dir: str,
        output_dir: str,
        hmac_secret: str | None = None,
        language: str = "en",
        storage: StorageDriver | None = None,
        budget: MemoryBudget | None = None,
    ) -> None:
        self.state_dir = state_dir
        self.output_dir = output_dir
        self.language = language
        self.storage = storage or FilesystemDriver()
        self.coordinator = BuildCoordinator(state_dir, hmac_secret)
        self.budget = budget or MemoryBudget.default()
        self.builder = InvertedIndexBuilder(Tokenizer(), Stemmer(language))
        self.merger = IndexMerger()
        self.cache = PageWordCache(
            os.path.join(state_dir, _CACHE_SUBDIR),
            self.storage,
            chunk_size=self.budget.chunk_size(),
            max_write_buffer_bytes=self.budget.token_cache_chunk_bytes(),
        )
        self._current_page_offset = 0
        self._prepared = False

    @staticmethod
    def content_hash(item) -> str:
        return content_hash(item)

    @staticmethod
    def compute_fingerprint(items) -> str:
        return compute_fingerprint(items)

    def process_chunk(
        self, items, chunk_number: int, total_pages: int | None = None, force: bool = False
    ) -> int:
        if not self._prepared:
            intent = BuildIntent.fresh(
                total_pages if total_pages is not None else len(items),
                self.budget,
                {"language": self.language},
            )
            self.coordinator.prepare(intent)
            self._prepared = True
        partial = self.builder.build_from_token_data(
            self._tokenize_items(items, force), self._current_page_offset
        )
        self._current_page_offset += len(partial["pages"])
        self.coordinator.commit_chunk(chunk_number, partial)
        return len(partial["pages"])

    def _tokenize_items(self, items, force: bool) -> Iterator[dict]:
        for item in items:
            h = content_hash(item)
            token_data = self.cache.get(h) if not force else None
            if token_data is None:
                token_data = self.builder.tokenize_item(item)
                if token_data is not None:
                    self.cache.put(h, token_data)
            if token_data is not None:
                yield {"item": _proxy(item), "tokenData": token_data}

    def finalize(self) -> BuildResult:
        start_time = time.monotonic()
        try:
            chunk_files = self.coordinator.chunk_files()
            if not chunk_files:
                return BuildResult(
                    False,
                    "No chunks to merge",
                    0,
                    0,
                    0.0,
                    error="No chunk files found in state directory",
                )
            writer = StreamingFormatWriter(
                CborEncoder(), flush_bytes=self.budget.fragment_flush_bytes()
            )
            writer.begin_write(self.output_dir)
            self.merger.merge_streaming(chunk_files, writer, self.budget)
            writer.end_write()
            page_count = self.coordinator.pages_processed()
            self._atomic_swap()
            IndexBuildOrchestrator.verify_index_complete(self.output_dir)
            file_count = self._count_files(os.path.join(self.output_dir, "pagefind"))
            self.coordinator.release()
            self._prepared = False
            self.cache.prune_and_save()
            return BuildResult(
                True,
                f"Built index for {page_count} pages ({file_count} files)",
                page_count,
                file_count,
                round(time.monotonic() - start_time, 3),
            )
        except Exception as exc:  # noqa: BLE001
            # The result flattens the failure to str(exc); keep the traceback
            # in the log so build failures stay diagnosable.
            _LOGGER.exception("[scolta] Index finalize failed: %s", exc)
            self.coordinator.release_lock_only()
            return BuildResult(
                False, "Build failed", 0, 0, round(time.monotonic() - start_time, 3), error=str(exc)
            )

    def should_build(self, items) -> str | None:
        fingerprint = compute_fingerprint(items)
        state_file = os.path.join(self.output_dir, ".scolta-state")
        if self.storage.exists(state_file):
            if self.storage.get(state_file).strip() == fingerprint:
                return None
        return fingerprint

    def _atomic_swap(self) -> None:
        atomic_swap(self.storage, self.output_dir)

    @staticmethod
    def _count_files(directory: str) -> int:
        if not os.path.isdir(directory):
            return 0
        return sum(
            1
            for f in glob.glob(os.path.join(directory, "**", "*"), recursive=True)
            if os.path.isfile(f)
        )
