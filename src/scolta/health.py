"""Health checks and setup diagnostics (port of ``Health\\HealthChecker`` and
``SetupCheck``), adapted to Python (no ini_get / extension_loaded).

Diagnostics: Python indexer ready, assets present, config valid, AI reachable;
the Pagefind binary is only required when indexer == 'binary'.
"""

from __future__ import annotations

import gzip
import json
import os
import re
import sys
from pathlib import Path

from .config import ScoltaConfig
from .pagefind import PagefindBinary

_ASSETS = Path(__file__).resolve().parent / "assets"
_STALE_URL = re.compile(r"^/[a-zA-Z0-9_-]+\.html$")


class HealthChecker:
    def __init__(
        self,
        config: ScoltaConfig,
        index_output_dir: str,
        pagefind_binary_path: str | None,
        project_dir: str | None,
    ) -> None:
        self.config = config
        self.index_output_dir = index_output_dir
        self.pagefind_binary_path = pagefind_binary_path
        self.project_dir = project_dir

    def check(self) -> dict:
        binary_status = PagefindBinary(self.pagefind_binary_path, self.project_dir).status()

        index_exists = os.path.exists(os.path.join(self.index_output_dir, "pagefind", "pagefind.js")) or \
            os.path.exists(os.path.join(self.index_output_dir, "pagefind.js"))
        ai_configured = self.config.ai_api_key.strip() != ""

        status = "ok"
        if not index_exists or not ai_configured:
            status = "degraded"

        configured_indexer = self.config.indexer or "auto"
        indexer_active = "binary" if (configured_indexer == "binary" and binary_status["available"]) else "python"
        upgrade_message = (
            'Pagefind binary not found. Set indexer to "python" or install Pagefind: npm install -g pagefind'
            if (configured_indexer == "binary" and not binary_status["available"])
            else None
        )

        stale = self._detect_stale_artifact_urls()
        if stale:
            status = "degraded"

        return {
            "status": status,
            "ai_provider": self.config.ai_provider or "anthropic",
            "ai_configured": ai_configured,
            "pagefind_available": binary_status["available"],
            "wasm_available": False,
            "index_exists": index_exists,
            "indexer_active": indexer_active,
            "indexer_upgrade_available": configured_indexer == "binary" and not binary_status["available"],
            "indexer_upgrade_message": upgrade_message,
            "stale_artifact_urls": stale,
            "stale_artifact_message": (
                "Index contains /{id}.html URLs from a pre-1.1.0 binary build. Run a full rebuild to fix."
                if stale else None
            ),
            "pagefind": {
                "available": binary_status["available"],
                "version": binary_status["version"],
                "resolved_via": binary_status["via"],
            },
            "wasm": {
                "available": False,
                "message": "Server-side WASM removed — HTML processing is pure Python",
            },
        }

    def _detect_stale_artifact_urls(self) -> bool:
        base = self.index_output_dir
        index_dir = os.path.join(base, "pagefind") if os.path.exists(
            os.path.join(base, "pagefind", "pagefind-entry.json")
        ) else base
        fragment_dir = os.path.join(index_dir, "fragment")
        if not os.path.isdir(fragment_dir):
            fragment_dir = index_dir
        import glob

        fragments = glob.glob(os.path.join(fragment_dir, "*.pf_fragment"))
        if not fragments:
            return False
        for f in fragments[:5]:
            try:
                data = gzip.decompress(Path(f).read_bytes())
            except OSError:
                continue
            if data.startswith(b"pagefind_dcd"):
                data = data[12:]
            try:
                j = json.loads(data.decode("utf-8"))
            except ValueError:
                continue
            if isinstance(j, dict) and "url" in j and _STALE_URL.match(j["url"]):
                return True
        return False


class SetupCheck:
    @staticmethod
    def run(
        configured_binary_path: str | None = None,
        project_dir: str | None = None,
        ai_api_key: str | None = None,
        browser_wasm_dir: str | None = None,
    ) -> list[dict]:
        results = []

        py_ok = sys.version_info >= (3, 10)
        version = ".".join(map(str, sys.version_info[:3]))
        results.append({
            "name": "Python version",
            "status": "pass" if py_ok else "fail",
            "message": f"Python {version}" if py_ok else f"Python {version} — requires 3.10+",
            "category": "runtime",
        })

        has_key = bool(ai_api_key)
        results.append({
            "name": "AI API key",
            "status": "pass" if has_key else "warn",
            "message": "AI API key configured" if has_key else "AI API key not set — AI features disabled",
            "category": "runtime",
        })

        wasm_dir = Path(browser_wasm_dir) if browser_wasm_dir else _ASSETS / "wasm"
        wasm_present = (wasm_dir / "scolta_core_bg.wasm").exists() and (wasm_dir / "scolta_core.js").exists()
        results.append({
            "name": "Browser WASM",
            "status": "pass" if wasm_present else "warn",
            "message": "Browser WASM assets found" if wasm_present else "Browser WASM assets missing",
            "category": "runtime",
        })

        binary_status = PagefindBinary(configured_binary_path, project_dir).status()
        results.append({
            "name": "Pagefind binary",
            "status": "pass" if binary_status["available"] else "warn",
            "message": binary_status["message"] if binary_status["available"]
            else "Pagefind not found — Python indexer will be used",
            "category": "build",
        })

        return results

    @staticmethod
    def run_all(output_dir: str) -> list[dict]:
        return [
            SetupCheck.check_icu(),
            SetupCheck.check_output_directory_writable(output_dir),
        ]

    @staticmethod
    def check_icu() -> dict:
        try:
            import icu  # noqa: F401

            return {"level": "ok", "message": "PyICU available"}
        except ImportError:
            return {
                "level": "warning",
                "message": "PyICU not installed — diacritic normalization uses the unicodedata fallback "
                "(install the [icu] extra for full ICU parity)",
            }

    @staticmethod
    def check_output_directory_writable(output_dir: str) -> dict:
        if os.path.isdir(output_dir) and os.access(output_dir, os.W_OK):
            return {"level": "ok", "message": f"Output directory writable: {output_dir}"}
        parent = os.path.dirname(output_dir.rstrip("/")) or "."
        if os.path.isdir(parent) and os.access(parent, os.W_OK):
            return {"level": "ok", "message": f"Output directory will be created in: {parent}"}
        return {"level": "error", "message": f"Output directory not writable: {output_dir}"}

    @staticmethod
    def exit_code(results: list[dict]) -> int:
        for result in results:
            level = result.get("status", result.get("level", ""))
            if level in ("fail", "error"):
                return 1
        return 0
