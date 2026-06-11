"""Filesystem storage abstraction used by the indexer.

Ports ``Tag1\\Scolta\\Storage\\StorageDriverInterface`` and
``FilesystemDriver``. Defaults to the local filesystem; serverless platforms
can swap for cloud storage by implementing :class:`StorageDriver`.
"""

from __future__ import annotations

import glob as _glob
import os
import re
import shutil
from abc import ABC, abstractmethod

_STREAM_WRAPPER = re.compile(r"^[a-zA-Z][a-zA-Z0-9+\-.]*://")


class StorageDriver(ABC):
    @abstractmethod
    def exists(self, path: str) -> bool: ...

    @abstractmethod
    def get(self, path: str) -> str: ...

    @abstractmethod
    def put(self, path: str, contents: str) -> bool: ...

    @abstractmethod
    def delete(self, path: str) -> bool: ...

    @abstractmethod
    def delete_directory(self, path: str) -> bool: ...

    @abstractmethod
    def make_directory(self, path: str) -> bool: ...

    @abstractmethod
    def move(self, src: str, dst: str) -> bool: ...

    @abstractmethod
    def files(self, directory: str, pattern: str = "*") -> list[str]: ...


class FilesystemDriver(StorageDriver):
    """Local filesystem storage driver. Default for most adapters."""

    @staticmethod
    def _validate_path(path: str) -> None:
        """Reject PHP-style stream wrappers (defense in depth)."""
        if _STREAM_WRAPPER.match(path):
            raise ValueError("Stream wrappers are not allowed in file paths.")

    def exists(self, path: str) -> bool:
        return os.path.exists(path)

    def get(self, path: str) -> str:
        self._validate_path(path)
        try:
            with open(path, encoding="utf-8") as fh:
                return fh.read()
        except OSError as exc:
            raise RuntimeError(f"Failed to read: {path}") from exc

    def put(self, path: str, contents: str) -> bool:
        self._validate_path(path)
        directory = os.path.dirname(path)
        if directory and not os.path.isdir(directory):
            os.makedirs(directory, mode=0o755, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(contents)
        return True

    def delete(self, path: str) -> bool:
        self._validate_path(path)
        if not os.path.exists(path):
            return True
        os.unlink(path)
        return True

    def delete_directory(self, path: str) -> bool:
        self._validate_path(path)
        if not os.path.isdir(path):
            return True
        shutil.rmtree(path)
        return True

    def make_directory(self, path: str) -> bool:
        self._validate_path(path)
        if os.path.isdir(path):
            return True
        os.makedirs(path, mode=0o755, exist_ok=True)
        return True

    def move(self, src: str, dst: str) -> bool:
        self._validate_path(src)
        self._validate_path(dst)
        # shutil.move falls back to copy+delete when src and dst sit on
        # different filesystems (os.rename raises EXDEV there).
        shutil.move(src, dst)
        return True

    def files(self, directory: str, pattern: str = "*") -> list[str]:
        self._validate_path(directory)
        return sorted(_glob.glob(os.path.join(directory, pattern)))
