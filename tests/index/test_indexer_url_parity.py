"""Release Gate #3 — indexer URL parity (the #155 root cause).

The Python indexer must store data.url == the canonical item.url (never a
/{id}.html artifact path), and the export path must mirror the canonical URL so
the binary indexer (pagefind --site, which derives data.url from the file path)
yields identical URLs. Asserted by joining on stable item id, NOT by URL — a
URL-keyed test is structurally blind to URL drift.
"""

import gzip
import json
import sys
from pathlib import Path

from scolta.content import ContentItem
from scolta.export import ContentExporter
from scolta.index.build_intent import BuildIntent
from scolta.index.memory_budget import MemoryBudget
from scolta.index.orchestrator import IndexBuildOrchestrator

sys.path.insert(0, str(Path(__file__).parent.parent / "support"))


def _corpus():
    body = "<p>" + "This is a sufficiently long paragraph for indexing. " * 5 + "</p>"
    return [
        ContentItem(
            "post-1",
            "Chocolate Cake Recipe",
            body,
            "/recipe/chocolate-cake/",
            "2026-01-15",
            "Recipes",
        ),
        ContentItem("post-2", "Hello World", body, "/blog/hello-world/", "2026-02-10", "Blog"),
        ContentItem("post-3", "About Us", body, "/about/", "2026-03-01", "Pages"),
        ContentItem("post-4", "Home Page", body, "/", "2026-04-01", "Pages"),
        ContentItem(
            "post-5", "Deep Nested Page", body, "/docs/api/v2/reference/", "2026-05-01", "Docs"
        ),
    ]


def test_export_path_mirrors_canonical_url(tmp_path):
    export_dir = str(tmp_path / "export")
    exporter = ContentExporter(export_dir, min_content_length=10)
    exporter.prepare_output_dir()
    for item in _corpus():
        exporter.export(item)

    expected = {
        "post-1": "/recipe/chocolate-cake/",
        "post-2": "/blog/hello-world/",
        "post-3": "/about/",
        "post-4": "/",
        "post-5": "/docs/api/v2/reference/",
    }
    for canonical in expected.values():
        rel = ContentExporter.url_to_export_path(canonical)
        assert (Path(export_dir) / rel).exists(), f"{canonical} not exported to {rel}"


def test_python_indexer_stores_canonical_url(tmp_path):
    items = _corpus()
    sd, od = str(tmp_path / "s"), str(tmp_path / "o")
    IndexBuildOrchestrator(sd, od).build(
        BuildIntent.fresh(len(items), MemoryBudget.default()), items
    )

    # Decode every fragment's url. Each item produces exactly one fragment whose
    # url must equal its canonical url — so the url SET must equal item.url SET.
    # (Joining by id: each id's canonical url must be present and no other.)
    fragment_urls = set()
    for f in (Path(od) / "pagefind" / "fragment").glob("*.pf_fragment"):
        raw = gzip.decompress(f.read_bytes())
        if raw.startswith(b"pagefind_dcd"):
            raw = raw[12:]
        fragment_urls.add(json.loads(raw.decode("utf-8"))["url"])

    expected_urls = {it.url for it in items}
    assert fragment_urls == expected_urls
    # No stale /{id}.html artifact URLs.
    for url in fragment_urls:
        assert not url.endswith(".html"), f"stale artifact url: {url}"
