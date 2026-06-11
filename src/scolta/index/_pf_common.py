"""Shared helpers for the Pagefind format writers.

Encapsulates the byte-level encoding shared by PagefindFormatWriter and
StreamingFormatWriter: word-entry CBOR, filter/sort/meta CBOR, the
``pagefind_dcd`` gzip framing, hash-naming, and PHP-faithful JSON.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import re

from .cbor import CborEncoder
from .delta_encoder import DeltaEncoder

DELIMITER = b"pagefind_dcd"

_NUMERIC = re.compile(r"^\s*[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?\s*$")


def is_numeric(s: str) -> bool:
    """Approximate PHP is_numeric for sort-field values."""
    return bool(_NUMERIC.match(s))


def php_json(obj) -> bytes:
    """json_encode(JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES) equivalent."""
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def hash10(data: bytes) -> str:
    return "en_" + hashlib.sha256(data).hexdigest()[:10]


def write_gz(path: str, payload: bytes) -> None:
    compressed = gzip.compress(DELIMITER + payload, compresslevel=9, mtime=0)
    with open(path, "wb") as fh:
        fh.write(compressed)


def ensure_dir(directory: str) -> None:
    os.makedirs(directory, exist_ok=True)


def fragment_json(page: dict) -> bytes:
    """Build a fragment JSON payload (empty filters/meta serialize as {})."""
    return php_json(
        {
            "url": page["url"],
            "content": page.get("content", ""),
            "word_count": page["wordCount"],
            "filters": page["filters"] if page.get("filters") else {},
            "meta": page["meta"] if page.get("meta") else {},
            "anchors": [],
        }
    )


def encode_word_entry(cbor: CborEncoder, word: str, page_entries: dict) -> bytes:
    """Encode one inverted-index word entry as CBOR.

    Page numbers delta-encoded; body positions carry the -25 weight marker;
    title meta positions carry the -1 field marker (title = field index 0).
    """
    variants = page_entries.get("_variants", {})
    page_entries = {k: v for k, v in page_entries.items() if k != "_variants"}

    page_nums = sorted(page_entries.keys())
    delta_pages = DeltaEncoder.delta_encode(page_nums)

    encoded_pages = []
    for idx, page_num in enumerate(page_nums):
        entry = page_entries[page_num]
        page_items = [cbor.encode_uint(delta_pages[idx])]

        all_body: list[int] = []
        for positions in entry["positions"].values():
            all_body.extend(sorted(positions))
        all_body.sort()

        pos_items = []
        if all_body:
            pos_items.append(cbor.encode_neg_int(-25))
            for dp in DeltaEncoder.delta_encode(all_body):
                pos_items.append(cbor.encode_uint(dp) if dp >= 0 else cbor.encode_neg_int(dp))
        page_items.append(cbor.encode_array(pos_items))

        meta_positions = entry.get("meta_positions", [])
        meta_items = []
        if meta_positions:
            mp_sorted = sorted(meta_positions)
            meta_items.append(cbor.encode_neg_int(-1))
            for mp in DeltaEncoder.delta_encode(mp_sorted):
                meta_items.append(cbor.encode_uint(mp) if mp >= 0 else cbor.encode_neg_int(mp))
        page_items.append(cbor.encode_array(meta_items))

        encoded_pages.append(cbor.encode_array(page_items))

    encoded_variants = []
    for form, variant_pages in variants.items():
        variant_page_entries = []
        for vp in variant_pages:
            variant_page_entries.append(
                cbor.encode_array(
                    [cbor.encode_uint(vp), cbor.encode_array([]), cbor.encode_array([])]
                )
            )
        encoded_variants.append(
            cbor.encode_array(
                [cbor.encode_string(str(form)), cbor.encode_array(variant_page_entries)]
            )
        )

    return cbor.encode_array(
        [
            cbor.encode_string(word),
            cbor.encode_array(encoded_pages),
            cbor.encode_array(encoded_variants),
        ]
    )


def build_filter_index(cbor: CborEncoder, filter_data: dict) -> dict[str, bytes]:
    """filter_data: {name: {value: [pageNums]}} -> {name: cbor bytes}."""
    result = {}
    for name, values in filter_data.items():
        value_tuples = []
        for value, page_nums in values.items():
            value_tuples.append(
                cbor.encode_array(
                    [
                        cbor.encode_string(str(value)),
                        cbor.encode_array([cbor.encode_uint(p) for p in page_nums]),
                    ]
                )
            )
        result[name] = cbor.encode_array(
            [cbor.encode_string(name), cbor.encode_array(value_tuples)]
        )
    return result


def build_sorts_array(cbor: CborEncoder, sort_fields: dict) -> bytes:
    """sort_fields: {field: {pageNum: value_str}} -> CBOR for pf_meta[4]."""
    if not sort_fields:
        return cbor.encode_array([])

    sort_items = []
    for field, page_values in sort_fields.items():
        all_numeric = all(is_numeric(v) for v in page_values.values())
        items = list(page_values.items())
        if all_numeric:
            items.sort(key=lambda kv: float(kv[1]))
        else:
            items.sort(key=lambda kv: kv[1])
        sorted_indices = [cbor.encode_uint(p) for p, _ in items]
        sort_items.append(
            cbor.encode_array([cbor.encode_string(field), cbor.encode_array(sorted_indices)])
        )
    return cbor.encode_array(sort_items)


def build_metadata(
    cbor: CborEncoder,
    version: str,
    pages_meta: list[tuple[str, int]],
    chunk_meta: list[dict],
    filter_hashes: dict[str, str],
    sorts_cbor: bytes,
    meta_fields: list[str],
) -> bytes:
    """Build pf_meta CBOR: [version, pages, index_chunks, filters, sorts, meta_fields]."""
    page_items = [
        cbor.encode_array([cbor.encode_string(h), cbor.encode_uint(wc)]) for h, wc in pages_meta
    ]
    chunk_items = [
        cbor.encode_array(
            [
                cbor.encode_string(c["from"]),
                cbor.encode_string(c["to"]),
                cbor.encode_string(c["hash"]),
            ]
        )
        for c in chunk_meta
    ]
    filter_items = [
        cbor.encode_array([cbor.encode_string(name), cbor.encode_string(h)])
        for name, h in filter_hashes.items()
    ]
    meta_field_items = [cbor.encode_string(f) for f in meta_fields]

    return cbor.encode_array(
        [
            cbor.encode_string(version),
            cbor.encode_array(page_items),
            cbor.encode_array(chunk_items),
            cbor.encode_array(filter_items),
            sorts_cbor,
            cbor.encode_array(meta_field_items),
        ]
    )


def copy_assets(build_dir: str) -> None:
    """Copy bundled pagefind runtime assets into the build dir if vendored."""
    import shutil
    from pathlib import Path

    assets_dir = Path(__file__).resolve().parents[1] / "assets" / "pagefind"
    for asset in ("pagefind.js", "pagefind-worker.js", "wasm.en.pagefind", "wasm.unknown.pagefind"):
        src = assets_dir / asset
        if src.exists():
            shutil.copy(src, os.path.join(build_dir, asset))


def write_entry_json(build_dir: str, version: str, meta_hash: str, page_count: int) -> None:
    entry = {
        "version": version,
        "languages": {
            "en": {"hash": meta_hash, "wasm": "en", "page_count": page_count},
        },
        "include_characters": [],
    }
    path = os.path.join(build_dir, "pagefind-entry.json")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, indent=4))
