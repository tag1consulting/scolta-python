"""Streaming Pagefind format writer (port of ``StreamingFormatWriter``).

The writer actually used in build/finalize — the primary parity target. Accepts
pages and terms one at a time (terms MUST arrive in ascending order, as produced
by the N-way streaming merge), flushing fragments immediately and index chunks
at ~40 KB to bound memory.
"""

from __future__ import annotations

import os

from . import _pf_common as pf
from .cbor import CborEncoder
from .supported_versions import SupportedVersions

_DEFAULT_FLUSH_BYTES = 40_000


class StreamingFormatWriter:
    def __init__(
        self,
        cbor: CborEncoder | None = None,
        pagefind_version: str = "",
        flush_bytes: int | None = None,
    ) -> None:
        self.cbor = cbor or CborEncoder()
        self.pagefind_version = pagefind_version
        self.flush_bytes = flush_bytes or _DEFAULT_FLUSH_BYTES

        self.output_dir = ""
        self.build_dir = ""
        self.page_meta: dict[int, dict] = {}
        self.filter_data: dict = {}
        self.collected_meta_fields: dict[str, bool] = {"title": True}
        self.sort_fields: dict = {}
        self._chunk_items: list[bytes] = []
        self._chunk_words: list[str] = []
        self._chunk_size = 0
        self._index_chunk_meta: list[dict] = []

    def _version(self) -> str:
        return self.pagefind_version or SupportedVersions.get_version_for_metadata()

    def begin_write(self, output_dir: str) -> None:
        self.output_dir = output_dir
        self.build_dir = os.path.join(output_dir, ".scolta-building")
        self.page_meta = {}
        self.filter_data = {}
        self.sort_fields = {}
        self.collected_meta_fields = {"title": True}
        self._chunk_items = []
        self._chunk_words = []
        self._chunk_size = 0
        self._index_chunk_meta = []
        pf.ensure_dir(self.build_dir)
        pf.ensure_dir(os.path.join(self.build_dir, "index"))
        pf.ensure_dir(os.path.join(self.build_dir, "fragment"))

    def write_page(self, page_num: int, page_data: dict) -> None:
        fragment = pf.fragment_json(page_data)
        h = pf.hash10((str(page_num) + page_data["url"]).encode("utf-8"))
        pf.write_gz(os.path.join(self.build_dir, "fragment", f"{h}.pf_fragment"), fragment)

        self.page_meta[page_num] = {"fragmentHash": h, "wordCount": int(page_data["wordCount"])}

        for name, value in (page_data.get("filters") or {}).items():
            values = value if isinstance(value, list) else [value]
            for v in values:
                self.filter_data.setdefault(name, {}).setdefault(str(v), []).append(page_num)

        sortable_data = dict(page_data.get("sortable") or {})
        if page_data.get("date") and "date" not in sortable_data:
            sortable_data["date"] = page_data["date"]
        for field, value in sortable_data.items():
            self.sort_fields.setdefault(field, {})[page_num] = str(value)

        for key in (page_data.get("meta") or {}):
            if key != "url":
                self.collected_meta_fields[key] = True

    def write_term(self, term: str, term_data: dict) -> None:
        encoded = pf.encode_word_entry(self.cbor, term, term_data)
        page_count = len(term_data) - (1 if "_variants" in term_data else 0)
        estimated = len(term) * 2 + page_count * 20

        if self._chunk_size + estimated > self.flush_bytes and self._chunk_items:
            self._flush_index_chunk()

        self._chunk_words.append(term)
        self._chunk_items.append(encoded)
        self._chunk_size += estimated

    def end_write(self) -> None:
        self._flush_index_chunk()

        filter_cbor = pf.build_filter_index(self.cbor, self.filter_data)
        filter_hashes = {}
        if filter_cbor:
            pf.ensure_dir(os.path.join(self.build_dir, "filter"))
            for name, data in filter_cbor.items():
                h = pf.hash10(data)
                pf.write_gz(os.path.join(self.build_dir, "filter", f"{h}.pf_filter"), data)
                filter_hashes[name] = h

        meta_fields = list(self.collected_meta_fields.keys())
        sorts_cbor = pf.build_sorts_array(self.cbor, self.sort_fields)
        pages_meta = [
            (m["fragmentHash"], m["wordCount"]) for m in self.page_meta.values()
        ]

        meta_cbor = pf.build_metadata(
            self.cbor, self._version(), pages_meta, self._index_chunk_meta,
            filter_hashes, sorts_cbor, meta_fields,
        )
        meta_hash = pf.hash10(meta_cbor)
        pf.write_gz(os.path.join(self.build_dir, f"pagefind.{meta_hash}.pf_meta"), meta_cbor)

        pf.write_entry_json(self.build_dir, self._version(), meta_hash, len(self.page_meta))
        pf.copy_assets(self.build_dir)

    def _flush_index_chunk(self) -> None:
        if not self._chunk_items:
            return
        inner = self.cbor.encode_array(self._chunk_items)
        cbor_data = self.cbor.encode_array([inner])
        h = pf.hash10(",".join(self._chunk_words).encode("utf-8"))
        pf.write_gz(os.path.join(self.build_dir, "index", f"{h}.pf_index"), cbor_data)
        self._index_chunk_meta.append(
            {"from": self._chunk_words[0], "to": self._chunk_words[-1], "hash": h}
        )
        self._chunk_items = []
        self._chunk_words = []
        self._chunk_size = 0
