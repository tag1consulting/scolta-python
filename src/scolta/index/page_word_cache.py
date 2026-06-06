"""Chunked forward token cache (port of ``PageWordCache``).

Content-hash -> token-data forward index so unchanged pages skip HTML cleaning
and tokenization on rebuilds — the "maintain the index efficiently" layer.

Architecture: an in-memory manifest (hash -> chunk number), one loaded data
chunk at a time, and a write buffer flushed at chunk_size entries or a byte cap.
``prune_and_save()`` drops unseen hashes and deletes orphaned chunk files.

Stored with msgpack (Python-native; no parity constraint). Token objects are
flattened to [stem, original, position] tuples. Lives in its own cache
directory so a fresh-build cleanup never eats it.
"""

from __future__ import annotations

import glob
import os
import re

import msgpack

from ..storage import StorageDriver
from .token import Token

_MANIFEST_FILENAME = "token-cache-manifest.msgpack"
_CHUNK_DIR = "token-cache"


def _pack_token_data(td: dict) -> dict:
    return {
        "t": [[tk.stem, tk.original, tk.position] for tk in td["titleTokens"]],
        "b": [[tk.stem, tk.original, tk.position] for tk in td["bodyTokens"]],
        "u": [[tk.stem, tk.original, tk.position] for tk in td["urlTokens"]],
        "wc": td["wordCount"],
        "ct": td["cleanTitle"],
        "c": td["content"],
    }


def _unpack_token_data(d: dict) -> dict:
    return {
        "titleTokens": [Token(s, o, p) for s, o, p in d["t"]],
        "bodyTokens": [Token(s, o, p) for s, o, p in d["b"]],
        "urlTokens": [Token(s, o, p) for s, o, p in d["u"]],
        "wordCount": d["wc"],
        "cleanTitle": d["ct"],
        "content": d["c"],
    }


class PageWordCache:
    def __init__(
        self,
        cache_dir: str,
        storage: StorageDriver,
        chunk_size: int = 50,
        logger=None,
        max_write_buffer_bytes: int = 4 * 1024 * 1024,
    ) -> None:
        self.cache_dir = cache_dir
        self.storage = storage
        self.chunk_size = max(1, chunk_size)
        self.max_write_buffer_bytes = max(0, max_write_buffer_bytes)
        self._manifest: dict[str, int] = {}
        self._used_keys: dict[str, bool] = {}
        self._loaded_chunk: dict | None = None
        self._write_buffer: dict[str, dict] = {}
        self._write_buffer_bytes = 0
        self._next_chunk_number = 0
        self._load_manifest()

    def get(self, content_hash: str) -> dict | None:
        self._used_keys[content_hash] = True
        if content_hash in self._write_buffer:
            return self._write_buffer[content_hash]
        if content_hash not in self._manifest:
            return None
        chunk_number = self._manifest[content_hash]
        if self._loaded_chunk is None or self._loaded_chunk["number"] != chunk_number:
            self._loaded_chunk = None
            entries = self._load_chunk_file(chunk_number)
            if entries is None:
                self._remove_chunk_from_manifest(chunk_number)
                return None
            self._loaded_chunk = {"number": chunk_number, "entries": entries}
        return self._loaded_chunk["entries"].get(content_hash)

    def put(self, content_hash: str, token_data: dict) -> None:
        self._used_keys[content_hash] = True
        self._write_buffer[content_hash] = token_data
        if self.max_write_buffer_bytes > 0:
            self._write_buffer_bytes += self._estimate_bytes(token_data)
        if len(self._write_buffer) >= self.chunk_size or (
            self.max_write_buffer_bytes > 0 and self._write_buffer_bytes >= self.max_write_buffer_bytes
        ):
            self._flush_write_buffer()

    def prune_and_save(self) -> None:
        if self._write_buffer:
            self._flush_write_buffer()
        self._loaded_chunk = None
        if self._used_keys:
            self._manifest = {k: v for k, v in self._manifest.items() if k in self._used_keys}
        live_chunks = set(self._manifest.values())
        chunk_dir = os.path.join(self.cache_dir, _CHUNK_DIR)
        if self.storage.exists(chunk_dir):
            for f in glob.glob(os.path.join(chunk_dir, "chunk-*.msgpack")):
                m = re.search(r"chunk-(\d+)\.msgpack$", os.path.basename(f))
                if m and int(m.group(1)) not in live_chunks:
                    self.storage.delete(f)
        self._save_manifest()

    # -- internal --

    def _load_manifest(self) -> None:
        path = os.path.join(self.cache_dir, _MANIFEST_FILENAME)
        if not self.storage.exists(path):
            return
        try:
            with open(path, "rb") as fh:
                data = msgpack.unpackb(fh.read(), raw=False, strict_map_key=False)
        except (OSError, ValueError):
            return
        if isinstance(data, dict):
            self._manifest = data
            if self._manifest:
                self._next_chunk_number = max(self._manifest.values()) + 1

    def _load_chunk_file(self, chunk_number: int) -> dict | None:
        path = self._chunk_file_path(chunk_number)
        if not self.storage.exists(path):
            return None
        try:
            with open(path, "rb") as fh:
                data = msgpack.unpackb(fh.read(), raw=False, strict_map_key=False)
        except (OSError, ValueError):
            return None
        if not isinstance(data, dict):
            return None
        return {h: _unpack_token_data(d) for h, d in data.items()}

    def _write_chunk_file(self, chunk_number: int, entries: dict) -> None:
        chunk_dir = os.path.join(self.cache_dir, _CHUNK_DIR)
        self.storage.make_directory(chunk_dir)
        path = self._chunk_file_path(chunk_number)
        tmp = f"{path}.tmp.{os.getpid()}"
        packed = {h: _pack_token_data(td) for h, td in entries.items()}
        with open(tmp, "wb") as fh:
            fh.write(msgpack.packb(packed, use_bin_type=True))
        os.replace(tmp, path)

    def _chunk_file_path(self, chunk_number: int) -> str:
        return os.path.join(self.cache_dir, _CHUNK_DIR, f"chunk-{chunk_number:06d}.msgpack")

    def _flush_write_buffer(self) -> None:
        if not self._write_buffer:
            return
        chunk_number = self._next_chunk_number
        self._next_chunk_number += 1
        self._write_chunk_file(chunk_number, self._write_buffer)
        for h in self._write_buffer:
            self._manifest[h] = chunk_number
        self._write_buffer = {}
        self._write_buffer_bytes = 0

    @staticmethod
    def _estimate_bytes(token_data: dict) -> int:
        token_count = (
            len(token_data.get("titleTokens", []))
            + len(token_data.get("bodyTokens", []))
            + len(token_data.get("urlTokens", []))
        )
        return token_count * 80 + len(token_data.get("content", ""))

    def _save_manifest(self) -> None:
        self.storage.make_directory(self.cache_dir)
        path = os.path.join(self.cache_dir, _MANIFEST_FILENAME)
        tmp = f"{path}.tmp.{os.getpid()}"
        with open(tmp, "wb") as fh:
            fh.write(msgpack.packb(self._manifest, use_bin_type=True))
        os.replace(tmp, path)

    def _remove_chunk_from_manifest(self, chunk_number: int) -> None:
        self._manifest = {k: v for k, v in self._manifest.items() if v != chunk_number}
