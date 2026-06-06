"""Cross-build entity timestamp manifest (port of ``TimestampManifest``).

Maps entity key -> {ts, items} so unchanged entities can be skipped. Lives in
the cross-build cache directory (separate from transient build state). Uses
msgpack (Python-native; no parity constraint) instead of PHP serialize().
"""

from __future__ import annotations

import os

import msgpack

from ..storage import StorageDriver

_FILENAME = "timestamp-manifest.msgpack"


class TimestampManifest:
    def __init__(self, cache_dir: str, storage: StorageDriver) -> None:
        self.cache_dir = cache_dir
        self.storage = storage
        self._data: dict = {}
        self._seen: dict = {}
        self._dirty = False
        self._load_from_disk()

    def get(self, entity_key: str) -> dict | None:
        return self._data.get(entity_key)

    def put(self, entity_key: str, ts: int, items: list) -> None:
        self._data[entity_key] = {"ts": ts, "items": items}
        self._seen[entity_key] = True
        self._dirty = True

    def mark_seen(self, entity_key: str) -> None:
        self._seen[entity_key] = True

    def prune_and_save(self) -> None:
        for key in list(self._data.keys()):
            if key not in self._seen:
                del self._data[key]
                self._dirty = True
        if self._dirty:
            self._save_to_disk()
            self._dirty = False

    def is_empty(self) -> bool:
        return not self._data

    def count(self) -> int:
        return len(self._data)

    def _path(self) -> str:
        return os.path.join(self.cache_dir, _FILENAME)

    def _load_from_disk(self) -> None:
        path = self._path()
        if not self.storage.exists(path):
            return
        try:
            with open(path, "rb") as fh:
                data = msgpack.unpackb(fh.read(), raw=False, strict_map_key=False)
            if isinstance(data, dict):
                self._data = data
        except (OSError, ValueError):
            return

    def _save_to_disk(self) -> None:
        self.storage.make_directory(self.cache_dir)
        path = self._path()
        tmp = f"{path}.tmp.{os.getpid()}"
        with open(tmp, "wb") as fh:
            fh.write(msgpack.packb(self._data, use_bin_type=True))
        os.replace(tmp, path)
