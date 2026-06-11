"""Export content items as Pagefind-ready HTML files.

Port of ``Tag1\\Scolta\\Export\\ContentExporter``. CMS-agnostic export logic:
output-dir preparation, HTML cleaning, Pagefind document generation, the
URL->file-path mapping that keeps the Python and binary indexers' ``data.url``
identical, and the min-content-length filter used by the in-process indexer.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable, Iterator

from . import html as htmlmod
from .content import ContentItem

_MANIFEST_NAME = ".scolta-export-manifest.json"


class ContentExporter:
    def __init__(self, output_dir: str, min_content_length: int = 50) -> None:
        self.output_dir = output_dir
        self.min_content_length = min_content_length
        self._exported = 0
        self._skipped = 0
        self._exported_paths: dict[str, str] = {}

    @staticmethod
    def url_to_export_path(url: str) -> str:
        """Map a canonical URL path to an export-relative file path.

        /recipe/chocolate-cake/  -> recipe/chocolate-cake/index.html
        /recipe/chocolate-cake   -> recipe/chocolate-cake/index.html
        /about                   -> about/index.html
        /                        -> index.html
        """
        # PHP strtok($url, '?#'): first token, skipping any leading delimiters.
        path = url
        for delim in ("?", "#"):
            idx = path.find(delim)
            if idx != -1:
                path = path[:idx]
        path = path.lstrip("?#")
        if path == "":
            path = "/"
        path = path.lstrip("/")
        if path == "":
            return "index.html"
        path = path.rstrip("/")
        return path + "/index.html"

    def prepare_output_dir(self) -> None:
        """Remove all files in the output directory and ensure it exists."""
        if os.path.isdir(self.output_dir):
            for root, dirs, files in os.walk(self.output_dir, topdown=False):
                for name in files:
                    os.unlink(os.path.join(root, name))
                for name in dirs:
                    os.rmdir(os.path.join(root, name))
        if not os.path.isdir(self.output_dir):
            os.makedirs(self.output_dir, mode=0o755, exist_ok=True)
        self._exported_paths = {}

    def export(self, item: ContentItem) -> bool:
        """Export a single content item; return False if skipped (too short)."""
        clean_text = htmlmod.clean(item.body_html, item.title)

        if len(clean_text) < self.min_content_length:
            self._skipped += 1
            return False

        html = htmlmod.build(
            item.id,
            item.title,
            clean_text,
            item.url,
            item.date,
            item.site_name,
            item.language,
            item.filters,
            item.metadata,
            item.sortable,
        )

        relative_path = self.url_to_export_path(item.url)

        if relative_path in self._exported_paths:
            raise RuntimeError(
                f'Export path collision: items "{self._exported_paths[relative_path]}" '
                f'and "{item.id}" both map to "{relative_path}" (URL: "{item.url}")'
            )
        self._exported_paths[relative_path] = item.id

        export_path = os.path.join(self.output_dir, relative_path)
        os.makedirs(os.path.dirname(export_path), mode=0o755, exist_ok=True)
        with open(export_path, "w", encoding="utf-8") as fh:
            fh.write(html)
        self._exported += 1
        return True

    def export_to_items(self, items: list[ContentItem]) -> list[ContentItem]:
        """Filter items by minimum content length without writing to disk."""
        result = []
        for item in items:
            cleaned = htmlmod.clean(item.body_html)
            if len(cleaned) >= self.min_content_length:
                result.append(item)
        return result

    def filter_items(self, items: Iterable) -> Iterator:
        """Lazily filter items by min content length.

        Non-ContentItem objects (e.g. CachedContentReference cache-hit markers)
        pass through unchanged — they carry no body_html and are handled
        downstream by the build orchestrator."""
        for item in items:
            if not isinstance(item, ContentItem):
                yield item
                continue
            cleaned = htmlmod.clean(item.body_html)
            if len(cleaned) >= self.min_content_length:
                yield item

    @staticmethod
    def count_html_files(directory: str) -> int:
        """Count .html files recursively."""
        if not os.path.isdir(directory):
            return 0
        count = 0
        for _root, _dirs, files in os.walk(directory):
            for name in files:
                if name.endswith(".html"):
                    count += 1
        return count

    def delete_by_url(self, url: str) -> bool:
        relative_path = self.url_to_export_path(url)
        full_path = os.path.join(self.output_dir, relative_path)
        if os.path.exists(full_path):
            os.unlink(full_path)
            self._exported_paths.pop(relative_path, None)
            return True
        return False

    def delete_by_id(self, id: str) -> bool:
        manifest = self.read_manifest(self.output_dir)
        if id in manifest:
            full_path = os.path.join(self.output_dir, manifest[id])
            if os.path.exists(full_path):
                os.unlink(full_path)
                return True
        flat_path = os.path.join(self.output_dir, id + ".html")
        if os.path.exists(flat_path):
            os.unlink(flat_path)
            return True
        return False

    def write_manifest(self) -> None:
        manifest = {item_id: path for path, item_id in self._exported_paths.items()}
        manifest_path = os.path.join(self.output_dir, _MANIFEST_NAME)
        with open(manifest_path, "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, indent=4)

    @staticmethod
    def read_manifest(output_dir: str) -> dict[str, str]:
        manifest_path = os.path.join(output_dir, _MANIFEST_NAME)
        if not os.path.exists(manifest_path):
            return {}
        with open(manifest_path, encoding="utf-8") as fh:
            try:
                data = json.load(fh)
            except json.JSONDecodeError:
                return {}
        return data if isinstance(data, dict) else {}

    def get_stats(self) -> dict:
        return {"exported": self._exported, "skipped": self._skipped}
