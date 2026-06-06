"""Ported from tests/Index/CborEncoderTest.php (1:1), plus a UTF-8 byte-length case."""

import pytest

from scolta.index.cbor import CborEncoder


@pytest.fixture
def cbor():
    return CborEncoder()


def test_encode_uint_zero(cbor):
    assert cbor.encode_uint(0) == b"\x00"


def test_encode_uint_one(cbor):
    assert cbor.encode_uint(1) == b"\x01"


def test_encode_uint_ten(cbor):
    assert cbor.encode_uint(10) == b"\x0a"


def test_encode_uint_23_is_one_byte_canonical(cbor):
    assert cbor.encode_uint(23) == b"\x17"


def test_encode_uint_24_is_two_bytes(cbor):
    assert cbor.encode_uint(24) == b"\x18\x18"


def test_encode_uint_100(cbor):
    assert cbor.encode_uint(100) == b"\x18\x64"


def test_encode_uint_1000(cbor):
    assert cbor.encode_uint(1000) == b"\x19\x03\xe8"


def test_encode_uint_255(cbor):
    assert cbor.encode_uint(255) == b"\x18\xff"


def test_encode_uint_65535(cbor):
    assert cbor.encode_uint(65535) == b"\x19\xff\xff"


def test_encode_uint_65536(cbor):
    assert cbor.encode_uint(65536) == b"\x1a\x00\x01\x00\x00"


def test_encode_negative_one(cbor):
    assert cbor.encode_neg_int(-1) == b"\x20"


def test_encode_negative_ten(cbor):
    assert cbor.encode_neg_int(-10) == b"\x29"


def test_encode_negative_100(cbor):
    assert cbor.encode_neg_int(-100) == b"\x38\x63"


def test_encode_empty_string(cbor):
    assert cbor.encode_string("") == b"\x60"


def test_encode_single_char_string(cbor):
    assert cbor.encode_string("a") == b"\x61\x61"


def test_encode_string_uses_utf8_byte_length(cbor):
    # CJK char is 3 UTF-8 bytes -> length prefix 3, then the 3 bytes.
    encoded = cbor.encode_string("世")
    assert encoded == b"\x63" + "世".encode()
    assert len(encoded) == 4


def test_encode_empty_array(cbor):
    assert cbor.encode_array([]) == b"\x80"


def test_encode_array_of_ints(cbor):
    items = [cbor.encode_uint(1), cbor.encode_uint(2), cbor.encode_uint(3)]
    assert cbor.encode_array(items) == b"\x83\x01\x02\x03"


def test_encode_nested_array(cbor):
    inner = cbor.encode_array([cbor.encode_uint(1)])
    assert cbor.encode_array([inner]) == b"\x81\x81\x01"


def test_encode_uint_rejects_negative(cbor):
    with pytest.raises(ValueError):
        cbor.encode_uint(-1)


def test_encode_neg_int_rejects_positive(cbor):
    with pytest.raises(ValueError):
        cbor.encode_neg_int(0)
