"""Transient build-chunk v2 I/O (port of ChunkWriter / ChunkReader).

Format:
    {JSON header}\\n
    [page records:  4-byte LE length + msgpack payload] x page_count
    [term records:  4-byte LE length + msgpack payload] x term_count (sorted)
    \\x00\\x00\\x00\\x00  (end-of-records sentinel)
    {JSON footer with crc32 (+ optional hmac)}\\n

Records use msgpack (not PHP serialize) — internal only, no parity constraint;
msgpack preserves the integer page/weight keys through the round-trip. Terms
are written in alphabetical order so the N-way streaming merge can consume them.
"""

from __future__ import annotations

import hmac as _hmac
import json
import struct
import zlib
from collections.abc import Iterator

import msgpack

_SENTINEL = b"\x00\x00\x00\x00"


def _pack(obj) -> bytes:
    return msgpack.packb(obj, use_bin_type=True)


def _unpack(data: bytes):
    return msgpack.unpackb(data, raw=False, strict_map_key=False)


class ChunkWriter:
    def write(self, path: str, partial: dict, hmac_secret: str | None = None) -> None:
        pages = partial.get("pages", {})
        index = partial.get("index", {})
        terms = sorted(index.keys())

        with open(path, "wb") as fp:
            header = json.dumps({"v": 2, "page_count": len(pages), "term_count": len(terms)})
            fp.write(header.encode("utf-8") + b"\n")

            hmac_ctx = _hmac.new(hmac_secret.encode("utf-8"), digestmod="sha256") if hmac_secret else None
            crc = 0

            def emit(payload: bytes) -> None:
                nonlocal crc
                length = struct.pack("<I", len(payload))
                fp.write(length)
                fp.write(payload)
                if hmac_ctx is not None:
                    hmac_ctx.update(length)
                    hmac_ctx.update(payload)
                crc = zlib.crc32(length, crc)
                crc = zlib.crc32(payload, crc)

            for page_num, page_data in pages.items():
                emit(_pack([page_num, page_data]))
            for term in terms:
                emit(_pack([term, index[term]]))

            fp.write(_SENTINEL)

            footer = {
                "hmac": hmac_ctx.hexdigest() if hmac_ctx is not None else "",
                "crc32": format(crc & 0xFFFFFFFF, "08x"),
            }
            fp.write(json.dumps(footer).encode("utf-8") + b"\n")


class ChunkReader:
    def __init__(self, path: str) -> None:
        self.path = path

    def _read_header(self, fp) -> dict:
        line = fp.readline()
        if not line:
            raise RuntimeError(f"Cannot read chunk header: {self.path}")
        if line[:1] != b"{":
            raise RuntimeError(
                "Chunk is not in v2 streaming format (first byte is not '{'). "
                f"Delete the state directory and re-run a fresh build: {self.path}"
            )
        header = json.loads(line.decode("utf-8"))
        if int(header.get("v", 0)) != 2:
            raise RuntimeError(f"Malformed or unsupported chunk header in: {self.path}")
        return {"page_count": int(header.get("page_count", 0)), "term_count": int(header.get("term_count", 0))}

    def open_pages(self) -> Iterator[tuple[int, dict]]:
        with open(self.path, "rb") as fp:
            header = self._read_header(fp)
            for i in range(header["page_count"]):
                payload = self._read_record(fp, f"page #{i}")
                page_num, page_data = _unpack(payload)
                yield int(page_num), page_data

    def open_index(self) -> Iterator[tuple[str, dict]]:
        with open(self.path, "rb") as fp:
            header = self._read_header(fp)
            for i in range(header["page_count"]):
                len_raw = fp.read(4)
                if len(len_raw) < 4:
                    raise RuntimeError(f"Unexpected EOF skipping page #{i} in: {self.path}")
                fp.seek(struct.unpack("<I", len_raw)[0], 1)
            while True:
                len_raw = fp.read(4)
                if len(len_raw) < 4:
                    break
                length = struct.unpack("<I", len_raw)[0]
                if length == 0:
                    break
                payload = fp.read(length)
                if len(payload) < length:
                    raise RuntimeError(f"Truncated term record in: {self.path}")
                record = _unpack(payload)
                yield str(record[0]), record[1]

    def _read_record(self, fp, label: str) -> bytes:
        len_raw = fp.read(4)
        if len(len_raw) < 4:
            raise RuntimeError(f"Unexpected EOF reading {label} in: {self.path}")
        length = struct.unpack("<I", len_raw)[0]
        payload = fp.read(length)
        if len(payload) < length:
            raise RuntimeError(f"Truncated {label} record in: {self.path}")
        return payload

    def verify_crc32(self) -> bool:
        try:
            with open(self.path, "rb") as fp:
                self._read_header(fp)
                crc = 0
                while True:
                    len_raw = fp.read(4)
                    if len(len_raw) < 4:
                        return False
                    length = struct.unpack("<I", len_raw)[0]
                    if length == 0:
                        break
                    payload = fp.read(length)
                    if len(payload) < length:
                        return False
                    crc = zlib.crc32(len_raw, crc)
                    crc = zlib.crc32(payload, crc)
                footer = json.loads(fp.readline().decode("utf-8"))
                if "crc32" not in footer:
                    return True
                return format(crc & 0xFFFFFFFF, "08x") == footer["crc32"]
        except (OSError, ValueError, RuntimeError):
            return False

    def verify_hmac(self, hmac_secret: str) -> bool:
        try:
            with open(self.path, "rb") as fp:
                self._read_header(fp)
                ctx = _hmac.new(hmac_secret.encode("utf-8"), digestmod="sha256")
                while True:
                    len_raw = fp.read(4)
                    if len(len_raw) < 4:
                        return False
                    length = struct.unpack("<I", len_raw)[0]
                    if length == 0:
                        break
                    payload = fp.read(length)
                    if len(payload) < length:
                        return False
                    ctx.update(len_raw)
                    ctx.update(payload)
                footer = json.loads(fp.readline().decode("utf-8"))
                return "hmac" in footer and _hmac.compare_digest(ctx.hexdigest(), footer["hmac"])
        except (OSError, ValueError, RuntimeError):
            return False
