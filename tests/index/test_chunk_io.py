"""Tests for ChunkWriter/ChunkReader (ported from ChunkWriterReaderTest.php)."""

import os

import pytest

from scolta.index.chunk_io import ChunkReader, ChunkWriter


def _partial():
    return {
        "pages": {
            0: {"id": "a", "url": "/a", "wordCount": 3, "content": "x"},
            1: {"id": "b", "url": "/b", "wordCount": 5, "content": "y"},
        },
        "index": {
            "beta": {0: {"positions": {25: [1, 2]}, "meta_positions": []}},
            "alpha": {
                1: {"positions": {25: [3]}, "meta_positions": [0]},
                "_variants": {"álpha": [1]},
            },
        },
    }


def test_round_trip(tmp_path):
    path = str(tmp_path / "chunk-000.dat")
    ChunkWriter().write(path, _partial())

    pages = dict(ChunkReader(path).open_pages())
    assert set(pages.keys()) == {0, 1}
    assert pages[1]["wordCount"] == 5

    index = dict(ChunkReader(path).open_index())
    assert set(index.keys()) == {"alpha", "beta"}
    # int page/weight keys preserved through msgpack round-trip
    assert index["beta"][0]["positions"][25] == [1, 2]
    assert index["alpha"]["_variants"]["álpha"] == [1]


def test_terms_yielded_in_alphabetical_order(tmp_path):
    path = str(tmp_path / "c.dat")
    ChunkWriter().write(path, _partial())
    terms = [t for t, _ in ChunkReader(path).open_index()]
    assert terms == sorted(terms)


def test_crc32_validates(tmp_path):
    path = str(tmp_path / "c.dat")
    ChunkWriter().write(path, _partial())
    assert ChunkReader(path).verify_crc32() is True


def test_crc32_detects_corruption(tmp_path):
    chunk_file = tmp_path / "c.dat"
    ChunkWriter().write(str(chunk_file), _partial())
    data = bytearray(chunk_file.read_bytes())
    # Flip a byte in the record region (after the header line).
    nl = data.index(b"\n")
    data[nl + 10] ^= 0xFF
    chunk_file.write_bytes(bytes(data))
    assert ChunkReader(str(chunk_file)).verify_crc32() is False


def test_hmac_round_trip(tmp_path):
    path = str(tmp_path / "c.dat")
    ChunkWriter().write(path, _partial(), hmac_secret="secret")
    assert ChunkReader(path).verify_hmac("secret") is True
    assert ChunkReader(path).verify_hmac("wrong") is False


def test_rejects_non_v2_format(tmp_path):
    path = str(tmp_path / "old.dat")
    with open(path, "wb") as fh:
        fh.write(b"a:1;old-php-serialized-format")
    with pytest.raises(RuntimeError, match="not in v2"):
        list(ChunkReader(path).open_pages())


def test_empty_partial(tmp_path):
    path = str(tmp_path / "c.dat")
    ChunkWriter().write(path, {"pages": {}, "index": {}})
    assert dict(ChunkReader(path).open_pages()) == {}
    assert dict(ChunkReader(path).open_index()) == {}
    assert ChunkReader(path).verify_crc32() is True


def test_open_index_skips_pages_correctly(tmp_path):
    # A page payload containing bytes that look like a sentinel must not confuse
    # the index reader, which seeks past pages by length prefix.
    path = str(tmp_path / "c.dat")
    partial = {
        "pages": {0: {"url": "/a", "wordCount": 1, "blob": "\x00\x00\x00\x00"}},
        "index": {"term": {0: {"positions": {25: [0]}, "meta_positions": []}}},
    }
    ChunkWriter().write(path, partial)
    assert [t for t, _ in ChunkReader(path).open_index()] == ["term"]
    assert os.path.exists(path)
