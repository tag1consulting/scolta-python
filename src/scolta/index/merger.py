"""Merge partial index chunks into one inverted index (port of IndexMerger).

merge() does a buffered full merge; merge_streaming() does the memory-bounded
N-way heap merge used by the pipeline: stream pages from every chunk, then
heap-merge the alphabetically-sorted term streams (with a recursive pre-merge
pass when chunk count exceeds the open-file budget). Page numbers are globally
sequential across chunks, so only _variants lists need unioning.
"""

from __future__ import annotations

import heapq
import json
import os
import secrets
import struct
import tempfile
import zlib

from .chunk_io import ChunkReader, _pack

_SENTINEL = b"\x00\x00\x00\x00"


class IndexMerger:
    def merge(self, partials: list[dict]) -> dict:
        merged_index: dict = {}
        merged_pages: dict = {}

        for partial in partials:
            if "index" not in partial or "pages" not in partial:
                continue
            for page_num, page_data in partial["pages"].items():
                merged_pages[page_num] = page_data
            for word, page_entries in partial["index"].items():
                entry = merged_index.setdefault(word, {})
                for page_num, data in page_entries.items():
                    if page_num == "_variants":
                        variants = entry.setdefault("_variants", {})
                        for variant, variant_pages in data.items():
                            existing = variants.setdefault(variant, [])
                            variants[variant] = list(dict.fromkeys(existing + variant_pages))
                        continue
                    if page_num not in entry:
                        entry[page_num] = data
                    else:
                        for weight, positions in data["positions"].items():
                            bucket = entry[page_num]["positions"].setdefault(weight, [])
                            entry[page_num]["positions"][weight] = sorted(set(bucket + positions))
                        if data.get("meta_positions"):
                            mp = entry[page_num].setdefault("meta_positions", [])
                            entry[page_num]["meta_positions"] = sorted(set(mp + data["meta_positions"]))

        for word in merged_index:
            merged_index[word] = self._sort_entry(merged_index[word])

        return {"index": merged_index, "pages": merged_pages}

    def merge_streaming(self, chunk_paths: list[str], writer, budget=None) -> None:
        # Phase 1: stream pages from all chunks (sequential, one handle).
        for path in chunk_paths:
            for page_num, page_data in ChunkReader(path).open_pages():
                writer.write_page(page_num, page_data)

        # Phase 2: N-way term merge, with pre-merge fan-in reduction.
        cap = budget.merge_open_file_handles() if budget is not None else None
        if cap is not None and len(chunk_paths) > cap:
            term_paths = self._pre_merge_terms(chunk_paths, cap)
        else:
            term_paths = chunk_paths
        self._n_way_term_merge(term_paths, writer.write_term)

    # -- helpers --

    @staticmethod
    def _sort_entry(entry: dict) -> dict:
        variants = entry.pop("_variants", None)
        ordered = {k: entry[k] for k in sorted(entry.keys())}
        if variants is not None:
            ordered["_variants"] = variants
        return ordered

    def _merge_entries(self, all_entries: list[dict]) -> dict:
        merged: dict = {}
        for entries in all_entries:
            for key, data in entries.items():
                if key == "_variants":
                    variants = merged.setdefault("_variants", {})
                    for variant, variant_pages in data.items():
                        existing = variants.setdefault(variant, [])
                        variants[variant] = list(dict.fromkeys(existing + variant_pages))
                else:
                    merged[key] = data  # globally-unique page numbers, no collision
        return self._sort_entry(merged)

    def _n_way_term_merge(self, chunk_paths: list[str], write_term) -> None:
        iters: dict[int, list] = {}
        heap: list[tuple[str, int]] = []
        for idx, path in enumerate(chunk_paths):
            it = ChunkReader(path).open_index()
            first = next(it, None)
            if first is not None:
                iters[idx] = [it, first]
                heapq.heappush(heap, (first[0], idx))

        while heap:
            min_term = heap[0][0]
            all_entries = []
            while heap and heap[0][0] == min_term:
                _, idx = heapq.heappop(heap)
                it, cur = iters[idx]
                all_entries.append(cur[1])
                nxt = next(it, None)
                if nxt is not None:
                    iters[idx][1] = nxt
                    heapq.heappush(heap, (nxt[0], idx))
            write_term(min_term, self._merge_entries(all_entries))

    def _pre_merge_terms(self, chunk_paths: list[str], cap: int) -> list[str]:
        if len(chunk_paths) <= cap:
            return chunk_paths
        tmp_dir = os.path.join(tempfile.gettempdir(), "scolta-premerge-" + secrets.token_hex(8))
        os.makedirs(tmp_dir, exist_ok=True)
        out_paths = []
        batches = [chunk_paths[i:i + cap] for i in range(0, len(chunk_paths), cap)]
        for i, batch in enumerate(batches):
            if len(batch) == 1:
                out_paths.append(batch[0])
                continue
            tmp_path = os.path.join(tmp_dir, f"premerge-{i:03d}.dat")
            self._stream_merge_terms_to_file(batch, tmp_path)
            out_paths.append(tmp_path)
        return self._pre_merge_terms(out_paths, cap)

    def _stream_merge_terms_to_file(self, batch: list[str], output_path: str) -> None:
        records: list[tuple[str, dict]] = []

        def collect(term, merged):
            records.append((term, merged))

        self._n_way_term_merge(batch, collect)

        with open(output_path, "wb") as fp:
            fp.write(json.dumps({"v": 2, "page_count": 0, "term_count": 0}).encode("utf-8") + b"\n")
            crc = 0
            for term, merged in records:
                payload = _pack([term, merged])
                length = struct.pack("<I", len(payload))
                fp.write(length)
                fp.write(payload)
                crc = zlib.crc32(length, crc)
                crc = zlib.crc32(payload, crc)
            fp.write(_SENTINEL)
            fp.write(json.dumps({"hmac": "", "crc32": format(crc & 0xFFFFFFFF, "08x")}).encode("utf-8") + b"\n")
