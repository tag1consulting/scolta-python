"""Integration tests for IndexBuildOrchestrator (Phase 6).

Covers a valid build, multi-chunk == single-chunk equivalence, the memory-abort
voluntary yield, and resume-after-interruption producing the same index.
"""

import glob
import re
import sys
from pathlib import Path

from scolta.content import ContentItem
from scolta.index.build_intent import BuildIntent
from scolta.index.memory_budget import MemoryBudget
from scolta.index.orchestrator import IndexBuildOrchestrator

sys.path.insert(0, str(Path(__file__).parent.parent / "support"))
import cbor_decoder  # noqa: E402

_FIX = Path(__file__).parent.parent / "fixtures"


def _items():
    out = []
    for i, p in enumerate(sorted(glob.glob(str(_FIX / "recipes" / "*.html")))):
        h = Path(p).read_text(encoding="utf-8")
        out.append(ContentItem(
            str(i + 1), re.search(r"<title>(.*?)</title>", h, re.S).group(1),
            h, re.search(r'data-pagefind-meta="url:([^"]*)"', h).group(1),
            "2024-01-01", "Recipes", "en",
        ))
    return out


def _word_set(output_dir):
    words = set()
    for f in glob.glob(output_dir + "/pagefind/index/*.pf_index"):
        for w, _pages, _variants in cbor_decoder.decode_pf_file(f)[0]:
            words.add(w)
    return words


def _fragment_count(output_dir):
    return len(glob.glob(output_dir + "/pagefind/fragment/*.pf_fragment"))


def test_build_produces_valid_index(tmp_path):
    sd, od = str(tmp_path / "s"), str(tmp_path / "o")
    r = IndexBuildOrchestrator(sd, od).build(BuildIntent.fresh(20, MemoryBudget.default()), _items())
    assert r.success is True
    assert r.pages_processed == 20
    assert _fragment_count(od) == 20
    IndexBuildOrchestrator.verify_index_complete(od)  # must not raise


def test_small_chunks_equal_single_chunk(tmp_path):
    items = _items()
    big = str(tmp_path / "big")
    IndexBuildOrchestrator(str(tmp_path / "sb"), big).build(
        BuildIntent.fresh(20, MemoryBudget.default().with_chunk_size(100)), items
    )
    small = str(tmp_path / "small")
    IndexBuildOrchestrator(str(tmp_path / "ss"), small).build(
        BuildIntent.fresh(20, MemoryBudget.default().with_chunk_size(3)), items
    )
    assert _word_set(big) == _word_set(small)
    assert _fragment_count(big) == _fragment_count(small) == 20


def test_memory_abort_yields_resumable(tmp_path):
    sd, od = str(tmp_path / "s"), str(tmp_path / "o")
    orch = IndexBuildOrchestrator(sd, od, memory_pressure_probe=lambda: True)
    r = orch.build(BuildIntent.fresh(20, MemoryBudget.default().with_chunk_size(5)), _items())
    assert r.success is False
    assert r.error == "memory_abort"
    assert r.pages_processed == 5  # one chunk committed
    # The build is resumable: state preserved.
    from scolta.index.build_state import BuildState

    assert BuildState(sd).should_resume() is not None


def test_resume_produces_same_index_as_uninterrupted(tmp_path):
    items = _items()

    # Uninterrupted reference build.
    ref = str(tmp_path / "ref")
    IndexBuildOrchestrator(str(tmp_path / "sref"), ref).build(
        BuildIntent.fresh(20, MemoryBudget.default().with_chunk_size(5)), items
    )

    # Interrupted build: yield after the first chunk (5 pages).
    sd, od = str(tmp_path / "s"), str(tmp_path / "o")
    orch = IndexBuildOrchestrator(sd, od, memory_pressure_probe=lambda: True)
    r1 = orch.build(BuildIntent.fresh(20, MemoryBudget.default().with_chunk_size(5)), items)
    assert r1.error == "memory_abort"

    # Resume with the remaining pages (offset continues from pages_processed).
    orch2 = IndexBuildOrchestrator(sd, od)
    r2 = orch2.build(BuildIntent.resume(MemoryBudget.default().with_chunk_size(5)), items[5:])
    assert r2.success is True
    assert _word_set(od) == _word_set(ref)
    assert _fragment_count(od) == 20
