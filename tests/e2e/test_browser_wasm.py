"""Phase 11 browser E2E: prove the shared Pagefind WASM accepts a PYTHON-built
index and returns correct search results.

Builds an index from the recipe fixtures with the in-process Python indexer,
serves it, then drives the real ``pagefind.js`` (+ ``wasm.en.pagefind``) in
headless Chromium and asserts queries return the expected pages. Skipped if
Playwright/Chromium are unavailable.
"""

import glob
import re
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

playwright_api = pytest.importorskip("playwright.sync_api")

from scolta.content import ContentItem  # noqa: E402
from scolta.index.build_intent import BuildIntent  # noqa: E402
from scolta.index.memory_budget import MemoryBudget  # noqa: E402
from scolta.index.orchestrator import IndexBuildOrchestrator  # noqa: E402

_FIX = Path(__file__).parent.parent / "fixtures" / "recipes"

_TEST_PAGE = """<!DOCTYPE html><html><head><meta charset="utf-8"></head><body>
<script type="module">
  try {
    const pagefind = await import("/pagefind/pagefind.js");
    await pagefind.init();
    window.runSearch = async (q) => {
      const search = await pagefind.search(q);
      const data = await Promise.all(search.results.map(r => r.data()));
      return data.map(d => d.url);
    };
    window.pagefindReady = true;
  } catch (e) {
    window.pagefindError = String(e);
  }
</script></body></html>"""


class _Handler(SimpleHTTPRequestHandler):
    def log_message(self, *args):  # silence
        pass

    def guess_type(self, path):
        if path.endswith(".wasm") or path.endswith(".pagefind"):
            return "application/wasm"
        if path.endswith(".js"):
            return "text/javascript"
        return super().guess_type(path)


def _build_site(root: Path):
    items = []
    for i, p in enumerate(sorted(glob.glob(str(_FIX / "*.html")))):
        html = Path(p).read_text(encoding="utf-8")
        title = re.search(r"<title>(.*?)</title>", html, re.S).group(1)
        url = re.search(r'data-pagefind-meta="url:([^"]*)"', html).group(1)
        items.append(ContentItem(str(i + 1), title, html, url, "2024-01-01", "Recipes", "en"))
    IndexBuildOrchestrator(str(root / "state"), str(root / "site")).build(
        BuildIntent.fresh(len(items), MemoryBudget.default()), items
    )
    (root / "site" / "test.html").write_text(_TEST_PAGE, encoding="utf-8")
    return root / "site"


@pytest.fixture
def served_site(tmp_path):
    site = _build_site(tmp_path)
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(_Handler, directory=str(site)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()


def test_wasm_accepts_python_built_index(served_site):
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except PlaywrightError as exc:
            pytest.skip(f"Chromium not installed (run 'playwright install chromium'): {exc}")
        page = browser.new_page()
        page.goto(f"{served_site}/test.html")
        # Surface any module-load error instead of a bare timeout.
        page.wait_for_function(
            "() => window.pagefindReady === true || window.pagefindError", timeout=30000
        )
        err = page.evaluate("() => window.pagefindError || null")
        assert err is None, f"pagefind.js failed to load: {err}"

        # A real query returns the matching page from the Python-built index.
        eggplant = page.evaluate("async () => await window.runSearch('eggplant')")
        assert any("eggplant" in url for url in eggplant), f"no eggplant result: {eggplant}"

        noodles = page.evaluate("async () => await window.runSearch('noodles')")
        assert len(noodles) >= 2, f"expected multiple noodle recipes: {noodles}"

        # A nonsense query returns nothing (proves it is really searching).
        nothing = page.evaluate("async () => await window.runSearch('zzqqxx-nonexistent')")
        assert nothing == [], f"expected no results, got: {nothing}"

        browser.close()
