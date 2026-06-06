"""Minimal canonical CBOR encoder (port of ``Tag1\\Scolta\\Index\\CborEncoder``).

RFC 8949 major types 0-4 only (uint, negint, text string, array), always
canonical (smallest) encoding. String lengths are UTF-8 *byte* lengths, matching
PHP's strlen — important for non-ASCII (CJK) terms.
"""

from __future__ import annotations

import struct


class CborEncoder:
    @staticmethod
    def _head(major: int, val: int) -> bytes:
        m = major << 5
        if val <= 23:
            return bytes([m | val])
        if val <= 0xFF:
            return bytes([m | 24, val])
        if val <= 0xFFFF:
            return bytes([m | 25]) + struct.pack(">H", val)
        if val <= 0xFFFFFFFF:
            return bytes([m | 26]) + struct.pack(">I", val)
        return bytes([m | 27]) + struct.pack(">Q", val)

    def encode_uint(self, n: int) -> bytes:
        if n < 0:
            raise ValueError("encode_uint requires non-negative integer")
        return self._head(0, n)

    def encode_neg_int(self, n: int) -> bytes:
        if n >= 0:
            raise ValueError("encode_neg_int requires negative integer")
        return self._head(1, -1 - n)

    def encode_string(self, s: str) -> bytes:
        b = s.encode("utf-8")
        return self._head(3, len(b)) + b

    def encode_array(self, items: list[bytes]) -> bytes:
        return self._head(4, len(items)) + b"".join(items)
