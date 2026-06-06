"""Minimal CBOR decoder for reading Pagefind index files in tests.

Port of scolta-php's tests/Support/CborDecoder.php. Handles the CBOR types
Pagefind uses (major 0-5). Test-only.
"""

from __future__ import annotations

import gzip
import struct


class _Decoder:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.offset = 0

    def decode_item(self):
        byte = self.data[self.offset]
        self.offset += 1
        major = (byte >> 5) & 0x07
        additional = byte & 0x1F
        value = self._decode_additional(additional)
        if major == 0:
            return value
        if major == 1:
            return -1 - value
        if major in (2, 3):
            return self._read_bytes(value, text=(major == 3))
        if major == 4:
            return [self.decode_item() for _ in range(value)]
        if major == 5:
            return {self.decode_item(): self.decode_item() for _ in range(value)}
        raise ValueError(f"Unsupported CBOR major type: {major}")

    def _decode_additional(self, additional: int) -> int:
        if additional <= 23:
            return additional
        if additional == 24:
            v = self.data[self.offset]
            self.offset += 1
            return v
        if additional == 25:
            v = struct.unpack(">H", self.data[self.offset:self.offset + 2])[0]
            self.offset += 2
            return v
        if additional == 26:
            v = struct.unpack(">I", self.data[self.offset:self.offset + 4])[0]
            self.offset += 4
            return v
        if additional == 27:
            v = struct.unpack(">Q", self.data[self.offset:self.offset + 8])[0]
            self.offset += 8
            return v
        raise ValueError(f"Unsupported CBOR additional info: {additional}")

    def _read_bytes(self, length: int, text: bool):
        b = self.data[self.offset:self.offset + length]
        self.offset += length
        return b.decode("utf-8") if text else b


def decode(data: bytes):
    return _Decoder(data).decode_item()


def decode_pf_file(filepath: str):
    """Decode a Pagefind .pf file (gzipped, with pagefind_dcd delimiter)."""
    with open(filepath, "rb") as fh:
        compressed = fh.read()
    decompressed = gzip.decompress(compressed)
    if decompressed.startswith(b"pagefind_dcd"):
        decompressed = decompressed[12:]
    return decode(decompressed)
