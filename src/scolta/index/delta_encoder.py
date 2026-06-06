"""Delta + weight-marker integer encoding (port of ``DeltaEncoder``).

Delta encoding stores differences between consecutive sorted values. Weight
markers signal weight-group changes as negative values ``-(weight + 1)``. This
is the wire encoding for CBOR position lists — NOT a build-delta mechanism.
"""

from __future__ import annotations


class DeltaEncoder:
    DEFAULT_WEIGHT = 25

    @staticmethod
    def delta_encode(values: list[int]) -> list[int]:
        if not values:
            return []
        result = [values[0]]
        for i in range(1, len(values)):
            result.append(values[i] - values[i - 1])
        return result

    @staticmethod
    def encode_positions(positions_by_weight: dict[int, list[int]]) -> list[int]:
        pbw = {w: p for w, p in positions_by_weight.items() if len(p) > 0}
        if not pbw:
            return []

        result: list[int] = []
        if DeltaEncoder.DEFAULT_WEIGHT in pbw:
            result = DeltaEncoder.delta_encode(pbw[DeltaEncoder.DEFAULT_WEIGHT])
            del pbw[DeltaEncoder.DEFAULT_WEIGHT]

        for weight in sorted(pbw):
            result.append(-(weight + 1))
            result.extend(DeltaEncoder.delta_encode(pbw[weight]))

        return result
