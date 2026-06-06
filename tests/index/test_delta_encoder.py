"""Ported from tests/Index/DeltaEncoderTest.php (1:1)."""

from scolta.index.delta_encoder import DeltaEncoder


def test_delta_encode_basic():
    assert DeltaEncoder.delta_encode([3, 7, 12, 15]) == [3, 4, 5, 3]


def test_delta_encode_empty():
    assert DeltaEncoder.delta_encode([]) == []


def test_delta_encode_single():
    assert DeltaEncoder.delta_encode([42]) == [42]


def test_delta_encode_consecutive():
    assert DeltaEncoder.delta_encode([1, 2, 3]) == [1, 1, 1]


def test_encode_positions_default_weight_only():
    assert DeltaEncoder.encode_positions({25: [5, 20, 35]}) == [5, 15, 15]


def test_encode_positions_multiple_weights():
    assert DeltaEncoder.encode_positions({25: [5, 20, 35], 50: [10, 15]}) == [5, 15, 15, -51, 10, 5]


def test_encode_positions_empty():
    assert DeltaEncoder.encode_positions({}) == []


def test_encode_positions_empty_weight_group_filtered():
    assert DeltaEncoder.encode_positions({25: [5], 50: []}) == [5]


def test_encode_positions_non_default_weight_only():
    assert DeltaEncoder.encode_positions({50: [10, 15]}) == [-51, 10, 5]


def test_encode_positions_single_position_per_weight():
    assert DeltaEncoder.encode_positions({25: [100], 75: [200]}) == [100, -76, 200]


def test_weight_marker_calculation():
    assert DeltaEncoder.encode_positions({50: [10]}) == [-51, 10]


def test_multiple_non_default_weights_sorted():
    assert DeltaEncoder.encode_positions({75: [30], 50: [10]}) == [-51, 10, -76, 30]
