"""Resumable build state (port of ``Tag1\\Scolta\\Index\\BuildState``).

Transient per-build state: an exclusive lock (fcntl.flock), an atomically
written manifest.json, and chunk-NNN.dat files. ``cleanup()`` removes only the
transient *files* directly in the state dir — it never recurses into subdirs,
so the cross-build token cache (kept in its own subdir by the orchestrator)
survives a fresh-build wipe. This fixes the fragile co-location in scolta-php.
"""

from __future__ import annotations

import glob
import json
import os
import time

from .chunk_io import ChunkReader, ChunkWriter
from .supported_versions import SupportedVersions

_LOCK_FILE = "lock"
_MANIFEST_FILE = "manifest.json"
_STALE_LOCK_SECONDS = 3600


class BuildState:
    def __init__(self, state_dir: str, hmac_secret: str | None = None) -> None:
        self.state_dir = state_dir
        self.hmac_secret = hmac_secret
        self._lock_handle = None
        os.makedirs(state_dir, exist_ok=True)

    def initiate_build(self, manifest: dict) -> bool:
        lock_file = os.path.join(self.state_dir, _LOCK_FILE)

        if os.path.exists(lock_file):
            try:
                with open(lock_file) as fh:
                    lock_data = fh.read()
                if self._is_lock_stale(lock_data):
                    self._unlink_quietly(lock_file)
            except OSError:
                pass

        import fcntl

        fp = open(lock_file, "a+")
        try:
            fcntl.flock(fp.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            fp.close()
            return False

        fp.seek(0)
        fp.truncate()
        fp.write(f"{os.getpid()}:{int(time.time())}")
        fp.flush()
        self._lock_handle = fp

        full = {
            "version": "1.0.0",
            "language": "en",
            "pagefind_version": SupportedVersions.BUNDLED_VERSION,
            "total_pages": 0,
            "pages_processed": 0,
            "chunk_size": 100,
            "chunks_written": 0,
            "started_at": _utc_now(),
            "fingerprint": "",
            "status": "building",
            **manifest,
        }
        self._commit_manifest(full)
        return True

    def record_chunk(self, chunk_number: int, partial: dict) -> None:
        path = os.path.join(self.state_dir, f"chunk-{chunk_number:03d}.dat")
        ChunkWriter().write(path, partial, self.hmac_secret)
        manifest = self._read_manifest()
        if manifest is not None:
            manifest["chunks_written"] = chunk_number + 1
            manifest["pages_processed"] = manifest.get("pages_processed", 0) + len(partial.get("pages", {}))
            self._commit_manifest(manifest)

    def read_chunk(self, chunk_number: int) -> dict:
        path = os.path.join(self.state_dir, f"chunk-{chunk_number:03d}.dat")
        if not os.path.exists(path):
            raise RuntimeError(f"Chunk file not found: chunk-{chunk_number:03d}.dat")
        if self.hmac_secret is not None and not ChunkReader(path).verify_hmac(self.hmac_secret):
            raise RuntimeError(f"HMAC verification failed for chunk: {path}")
        if not ChunkReader(path).verify_crc32():
            raise RuntimeError(f"CRC32 validation failed for chunk: {path}")
        pages = dict(ChunkReader(path).open_pages())
        index = dict(ChunkReader(path).open_index())
        return {"pages": pages, "index": index}

    def release_lock(self) -> None:
        self._drop_lock_file_only()
        manifest = self._read_manifest()
        if manifest is not None:
            manifest["status"] = "idle"
            self._commit_manifest(manifest)

    def release_lock_only(self) -> None:
        self._drop_lock_file_only()

    def _drop_lock_file_only(self) -> None:
        if self._lock_handle is not None:
            import fcntl

            try:
                fcntl.flock(self._lock_handle.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
            self._lock_handle.close()
            self._lock_handle = None
        self._unlink_quietly(os.path.join(self.state_dir, _LOCK_FILE))

    def should_resume(self) -> dict | None:
        manifest = self._read_manifest()
        if manifest is None or manifest.get("status") != "building":
            return None
        lock_file = os.path.join(self.state_dir, _LOCK_FILE)
        if os.path.exists(lock_file):
            try:
                with open(lock_file) as fh:
                    if self._is_lock_stale(fh.read()):
                        self._unlink_quietly(lock_file)
            except OSError:
                pass
        return manifest

    def get_chunk_files(self) -> list[str]:
        manifest = self._read_manifest()
        chunks_written = (manifest or {}).get("chunks_written", 0)
        files = []
        for i in range(chunks_written):
            path = os.path.join(self.state_dir, f"chunk-{i:03d}.dat")
            if os.path.exists(path):
                files.append(path)
        return files

    def is_running(self) -> bool:
        manifest = self._read_manifest()
        if manifest is None or manifest.get("status") != "building":
            return False
        lock_file = os.path.join(self.state_dir, _LOCK_FILE)
        if not os.path.exists(lock_file):
            return False
        try:
            with open(lock_file) as fh:
                return not self._is_lock_stale(fh.read())
        except OSError:
            return False

    def get_progress(self) -> float:
        manifest = self._read_manifest()
        if manifest is None:
            return 0.0
        total_pages = int(manifest.get("total_pages", 0))
        chunk_size = int(manifest.get("chunk_size", 100))
        chunks_written = int(manifest.get("chunks_written", 0))
        total_chunks = -(-total_pages // max(1, chunk_size)) if total_pages > 0 else 1
        return min(1.0, chunks_written / total_chunks)

    def get_start_time(self) -> str | None:
        manifest = self._read_manifest()
        return manifest.get("started_at") if manifest else None

    def get_pages_processed(self) -> int:
        manifest = self._read_manifest()
        return int((manifest or {}).get("pages_processed", 0))

    def cleanup(self) -> None:
        """Remove transient build files (not subdirectories — the cache subdir survives)."""
        if not os.path.isdir(self.state_dir):
            return
        for path in glob.glob(os.path.join(self.state_dir, "*")):
            if os.path.isfile(path):
                self._unlink_quietly(path)

    # -- internal --

    def _commit_manifest(self, manifest: dict) -> None:
        manifest_path = os.path.join(self.state_dir, _MANIFEST_FILE)
        temp_path = manifest_path + ".tmp"
        with open(temp_path, "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, indent=4)
        os.replace(temp_path, manifest_path)

    def _read_manifest(self) -> dict | None:
        path = os.path.join(self.state_dir, _MANIFEST_FILE)
        for candidate in (path, path + ".tmp"):
            if not os.path.exists(candidate):
                continue
            try:
                with open(candidate, encoding="utf-8") as fh:
                    data = json.load(fh)
                if isinstance(data, dict):
                    return data
            except (OSError, ValueError):
                continue
        return None

    def _is_lock_stale(self, lock_data: str) -> bool:
        parts = lock_data.split(":", 1)
        if len(parts) == 2:
            pid, timestamp = parts
            try:
                if time.time() - int(timestamp) > _STALE_LOCK_SECONDS:
                    return True
            except ValueError:
                return True
            try:
                os.kill(int(pid), 0)
                return False
            except ProcessLookupError:
                return True
            except PermissionError:
                return False
            except (ValueError, OSError):
                return True
        lock_path = os.path.join(self.state_dir, _LOCK_FILE)
        try:
            mtime = os.path.getmtime(lock_path)
        except OSError:
            return True
        return time.time() - mtime > _STALE_LOCK_SECONDS

    @staticmethod
    def _unlink_quietly(path: str) -> None:
        try:
            os.unlink(path)
        except OSError:
            pass


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
