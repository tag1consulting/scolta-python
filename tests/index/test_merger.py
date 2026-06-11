"""Tests for IndexMerger (ported from IndexMergerTest.php / StreamingMergeTest.php)."""

from scolta.index.chunk_io import ChunkWriter
from scolta.index.merger import IndexMerger


def test_merge_combines_pages_and_index():
    p0 = {
        "pages": {0: {"id": "a", "url": "/a"}},
        "index": {"cat": {0: {"positions": {25: [1]}, "meta_positions": []}}},
    }
    p1 = {
        "pages": {1: {"id": "b", "url": "/b"}},
        "index": {
            "cat": {1: {"positions": {25: [2]}, "meta_positions": []}},
            "dog": {1: {"positions": {25: [5]}, "meta_positions": []}},
        },
    }
    merged = IndexMerger().merge([p0, p1])
    assert set(merged["pages"].keys()) == {0, 1}
    assert set(merged["index"].keys()) == {"cat", "dog"}
    assert set(merged["index"]["cat"].keys()) == {0, 1}


def test_merge_unions_variants():
    p0 = {
        "pages": {0: {}},
        "index": {
            "cafe": {0: {"positions": {25: [1]}, "meta_positions": []}, "_variants": {"café": [0]}}
        },
    }
    p1 = {
        "pages": {1: {}},
        "index": {
            "cafe": {1: {"positions": {25: [2]}, "meta_positions": []}, "_variants": {"café": [1]}}
        },
    }
    merged = IndexMerger().merge([p0, p1])
    assert merged["index"]["cafe"]["_variants"]["café"] == [0, 1]


def test_merge_streaming_matches_buffered(tmp_path):
    # Two chunks written to disk; streaming merge into a recording writer must
    # produce the same word set + postings as the buffered merge.
    p0 = {
        "pages": {
            0: {
                "id": "a",
                "url": "/a",
                "wordCount": 2,
                "content": "c",
                "filters": {},
                "meta": {},
                "sortable": {},
                "date": "",
            }
        },
        "index": {
            "cat": {0: {"positions": {25: [1]}, "meta_positions": []}},
            "ant": {0: {"positions": {25: [0]}, "meta_positions": []}},
        },
    }
    p1 = {
        "pages": {
            1: {
                "id": "b",
                "url": "/b",
                "wordCount": 2,
                "content": "c",
                "filters": {},
                "meta": {},
                "sortable": {},
                "date": "",
            }
        },
        "index": {
            "cat": {1: {"positions": {25: [2]}, "meta_positions": []}},
            "bee": {1: {"positions": {25: [0]}, "meta_positions": []}},
        },
    }
    a = str(tmp_path / "chunk-000.dat")
    b = str(tmp_path / "chunk-001.dat")
    ChunkWriter().write(a, p0)
    ChunkWriter().write(b, p1)

    class Recorder:
        def __init__(self):
            self.pages = {}
            self.terms = {}

        def write_page(self, pn, data):
            self.pages[pn] = data

        def write_term(self, term, data):
            self.terms[term] = data

    rec = Recorder()
    IndexMerger().merge_streaming([a, b], rec)

    assert set(rec.pages.keys()) == {0, 1}
    assert sorted(rec.terms.keys()) == ["ant", "bee", "cat"]
    # 'cat' appears on both pages, globally-unique page numbers preserved.
    assert set(rec.terms["cat"].keys()) == {0, 1}


def test_merge_streaming_terms_in_sorted_order(tmp_path):
    p = {
        "pages": {
            0: {
                "url": "/a",
                "wordCount": 1,
                "content": "c",
                "filters": {},
                "meta": {},
                "sortable": {},
                "date": "",
            }
        },
        "index": {
            "zebra": {0: {"positions": {25: [0]}, "meta_positions": []}},
            "apple": {0: {"positions": {25: [1]}, "meta_positions": []}},
            "mango": {0: {"positions": {25: [2]}, "meta_positions": []}},
        },
    }
    path = str(tmp_path / "chunk-000.dat")
    ChunkWriter().write(path, p)
    order = []

    class Rec:
        def write_page(self, pn, data):
            pass

        def write_term(self, term, data):
            order.append(term)

    IndexMerger().merge_streaming([path], Rec())
    assert order == ["apple", "mango", "zebra"]


def test_pre_merge_fan_in_reduction(tmp_path):
    # Force pre-merge by capping open file handles below the chunk count.
    from scolta.index.memory_budget import MemoryBudget

    paths = []
    for i in range(5):
        p = {
            "pages": {
                i: {
                    "url": f"/{i}",
                    "wordCount": 1,
                    "content": "c",
                    "filters": {},
                    "meta": {},
                    "sortable": {},
                    "date": "",
                }
            },
            "index": {
                f"term{i}": {i: {"positions": {25: [0]}, "meta_positions": []}},
                "shared": {i: {"positions": {25: [1]}, "meta_positions": []}},
            },
        }
        path = str(tmp_path / f"chunk-{i:03d}.dat")
        ChunkWriter().write(path, p)
        paths.append(path)

    # Construct a budget with a low open-file cap (2) so 5 chunks force the
    # recursive pre-merge fan-in reduction.
    budget = MemoryBudget("conservative", 1, 40000, 40000, 2, 96 * 1024 * 1024, 4 * 1024 * 1024)
    terms = {}

    class Rec:
        def write_page(self, pn, data):
            pass

        def write_term(self, term, data):
            terms[term] = data

    IndexMerger().merge_streaming(paths, Rec(), budget)
    assert sorted(terms.keys()) == ["shared", "term0", "term1", "term2", "term3", "term4"]
    assert set(terms["shared"].keys()) == {0, 1, 2, 3, 4}
