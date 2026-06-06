"""Buffered Pagefind format writer (port of ``PagefindFormatWriter``).

Serializes a merged inverted index + pages to the Pagefind on-disk format in a
single buffered pass (remap to 0-based page numbers, chunk, write fragments /
index / filter / meta / entry.json).

Word order: lexicographic (canonical Rust-Pagefind / WASM order). PHP uses
``sort()`` (SORT_REGULAR), which is non-transitive on numeric tokens and
algorithm-dependent; lexicographic is the canonical order and matches PHP on
non-numeric vocabularies. See the Phase 5 parity notes.
"""

from __future__ import annotations

import os

from . import _pf_common as pf
from .cbor import CborEncoder
from .supported_versions import SupportedVersions

_MAX_CHUNK_SIZE = 40000


class PagefindFormatWriter:
    def __init__(self, cbor: CborEncoder | None = None, pagefind_version: str = "") -> None:
        self.cbor = cbor or CborEncoder()
        self.pagefind_version = pagefind_version

    def _version(self) -> str:
        return self.pagefind_version or SupportedVersions.get_version_for_metadata()

    def write(self, merged_index: dict, pages: dict, output_dir: str) -> None:
        pages_list, index = self._remap_page_numbers(pages, merged_index)

        build_dir = os.path.join(output_dir, ".scolta-building")
        pf.ensure_dir(build_dir)
        pf.ensure_dir(os.path.join(build_dir, "index"))
        pf.ensure_dir(os.path.join(build_dir, "fragment"))

        # Fragments.
        for page_num, page in enumerate(pages_list):
            fragment = pf.fragment_json(page)
            h = pf.hash10((str(page_num) + page["url"]).encode("utf-8"))
            page["fragmentHash"] = h
            pf.write_gz(os.path.join(build_dir, "fragment", f"{h}.pf_fragment"), fragment)

        # Index chunks.
        word_list = sorted(str(w) for w in index)
        chunks = self._chunk_words(word_list, index)
        chunk_meta = []
        for chunk_words in chunks:
            cbor_items = [pf.encode_word_entry(self.cbor, w, index[w]) for w in chunk_words]
            inner = self.cbor.encode_array(cbor_items)
            cbor_data = self.cbor.encode_array([inner])
            h = pf.hash10(",".join(chunk_words).encode("utf-8"))
            pf.write_gz(os.path.join(build_dir, "index", f"{h}.pf_index"), cbor_data)
            chunk_meta.append({"from": chunk_words[0], "to": chunk_words[-1], "hash": h})

        # Filter index.
        filter_data = self._collect_filters(pages_list)
        filter_cbor = pf.build_filter_index(self.cbor, filter_data)
        filter_hashes = {}
        if filter_cbor:
            pf.ensure_dir(os.path.join(build_dir, "filter"))
            for name, data in filter_cbor.items():
                h = pf.hash10(data)
                pf.write_gz(os.path.join(build_dir, "filter", f"{h}.pf_filter"), data)
                filter_hashes[name] = h

        meta_fields = self._collect_meta_fields(pages_list)
        sorts_cbor = pf.build_sorts_array(self.cbor, self._collect_sorts(pages_list))
        pages_meta = [(p.get("fragmentHash", p["hash"]), p["wordCount"]) for p in pages_list]

        meta_cbor = pf.build_metadata(
            self.cbor, self._version(), pages_meta, chunk_meta, filter_hashes, sorts_cbor, meta_fields
        )
        meta_hash = pf.hash10(meta_cbor)
        pf.write_gz(os.path.join(build_dir, f"pagefind.{meta_hash}.pf_meta"), meta_cbor)

        pf.write_entry_json(build_dir, self._version(), meta_hash, len(pages_list))
        pf.copy_assets(build_dir)

    # -- helpers --

    @staticmethod
    def _remap_page_numbers(pages: dict, merged_index: dict):
        original_keys = list(pages.keys())
        mapping = {}
        for i, key in enumerate(original_keys):
            mapping[int(key)] = i
        new_pages = list(pages.values())

        new_index: dict = {}
        for word, entries in merged_index.items():
            ni: dict = {}
            if "_variants" in entries:
                ni["_variants"] = {
                    variant: [mapping.get(p, p) for p in vpages]
                    for variant, vpages in entries["_variants"].items()
                }
            for page_num, data in entries.items():
                if page_num == "_variants":
                    continue
                ni[mapping.get(int(page_num), int(page_num))] = data
            new_index[word] = ni
        return new_pages, new_index

    @staticmethod
    def _chunk_words(word_list: list[str], index: dict) -> list[list[str]]:
        if not word_list:
            return []
        chunks = []
        current: list[str] = []
        size = 0
        for word in word_list:
            page_count = len(index[word]) - (1 if "_variants" in index[word] else 0)
            estimated = len(word) * 2 + page_count * 20
            if size + estimated > _MAX_CHUNK_SIZE and current:
                chunks.append(current)
                current = []
                size = 0
            current.append(word)
            size += estimated
        if current:
            chunks.append(current)
        return chunks

    @staticmethod
    def _collect_filters(pages_list: list) -> dict:
        filters: dict = {}
        for page_num, page in enumerate(pages_list):
            for name, value in (page.get("filters") or {}).items():
                filters.setdefault(name, {}).setdefault(value, []).append(page_num)
        return filters

    @staticmethod
    def _collect_meta_fields(pages_list: list) -> list[str]:
        fields = {"title": True}
        for page in pages_list:
            for key in (page.get("meta") or {}):
                if key != "url":
                    fields[key] = True
        return list(fields.keys())

    @staticmethod
    def _collect_sorts(pages_list: list) -> dict:
        sort_fields: dict = {}
        for page_num, page in enumerate(pages_list):
            for field, value in (page.get("sortable") or {}).items():
                sort_fields.setdefault(field, {})[page_num] = str(value)
        return sort_fields
