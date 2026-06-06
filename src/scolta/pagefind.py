"""Pagefind binary resolver (port of ``Tag1\\Scolta\\Binary\\PagefindBinary``).

Deterministic fallback chain, each step probed by running ``{cmd} --version``:
  1. explicitly configured path
  2. project-local .scolta/bin/pagefind
  3. npx pagefind
  4. bare 'pagefind' on PATH

Opt-in path (indexer: binary). The Python in-process indexer is the default and
needs none of this.
"""

from __future__ import annotations

import os
import subprocess


def _is_executable(cmd: str) -> bool:
    try:
        result = subprocess.run(
            cmd.split() + ["--version"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


class PagefindBinary:
    def __init__(self, configured_path: str | None = None, project_dir: str | None = None) -> None:
        self.configured_path = configured_path
        self.project_dir = project_dir
        self._resolved: str | None = None
        self._resolved_via = "none"

    def resolve(self) -> str | None:
        if self._resolved is not None:
            return self._resolved

        if self.configured_path and self.configured_path != "pagefind":
            if _is_executable(self.configured_path):
                self._resolved = self.configured_path
                self._resolved_via = "configured"
                return self._resolved

        if self.project_dir is not None:
            local = os.path.join(self.project_dir.rstrip("/"), ".scolta", "bin", "pagefind")
            if _is_executable(local):
                self._resolved = local
                self._resolved_via = "local"
                return self._resolved

        if _is_executable("npx pagefind"):
            self._resolved = "npx pagefind"
            self._resolved_via = "npx"
            return self._resolved

        if _is_executable("pagefind"):
            self._resolved = "pagefind"
            self._resolved_via = "path"
            return self._resolved

        self._resolved_via = "none"
        return None

    def resolved_via(self) -> str:
        if self._resolved is None and self._resolved_via == "none":
            self.resolve()
        return self._resolved_via

    def version(self) -> str | None:
        binary = self.resolve()
        if binary is None:
            return None
        try:
            result = subprocess.run(
                binary.split() + ["--version"], capture_output=True, text=True, timeout=15
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        return None

    def status(self) -> dict:
        binary = self.resolve()
        version = self.version()
        if binary is not None:
            return {
                "available": True,
                "binary": binary,
                "version": version,
                "via": self._resolved_via,
                "message": f"Pagefind {version or 'unknown version'} (resolved via {self._resolved_via})",
            }

        tried = []
        if self.configured_path and self.configured_path != "pagefind":
            tried.append(f"configured path '{self.configured_path}' -- not found or not executable")
        if self.project_dir is not None:
            local = os.path.join(self.project_dir.rstrip("/"), ".scolta", "bin", "pagefind")
            tried.append(f"project-local {local} -- not found")
        tried.append("npx pagefind -- npx not available or pagefind not installable")
        tried.append("system PATH -- 'pagefind' not found")
        return {
            "available": False,
            "binary": None,
            "version": None,
            "via": "none",
            "message": "Pagefind binary not found. Tried:\n  - "
            + "\n  - ".join(tried)
            + "\n\nInstall: npm install -g pagefind",
        }

    def download_target_dir(self) -> str:
        if self.project_dir is not None:
            d = os.path.join(self.project_dir.rstrip("/"), ".scolta", "bin")
            os.makedirs(d, exist_ok=True)
            return d
        import tempfile

        return tempfile.gettempdir()
