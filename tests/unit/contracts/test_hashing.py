"""Tests for contracts/hashing.py — NaN/Infinity rejection."""

import pytest

from elspeth.contracts.hashing import canonical_json, stable_hash


class TestCanonicalJsonNanRejection:
    """NaN and Infinity must be rejected with clear error messages."""

    def test_rejects_nan(self) -> None:
        with pytest.raises(ValueError, match="NaN"):
            canonical_json(float("nan"))

    def test_rejects_positive_infinity(self) -> None:
        with pytest.raises(ValueError, match="Infinity"):
            canonical_json(float("inf"))

    def test_rejects_negative_infinity(self) -> None:
        with pytest.raises(ValueError, match="Infinity"):
            canonical_json(float("-inf"))

    def test_rejects_nan_nested_in_dict(self) -> None:
        with pytest.raises(ValueError, match="NaN"):
            canonical_json({"key": float("nan")})

    def test_rejects_nan_nested_in_list(self) -> None:
        with pytest.raises(ValueError, match="NaN"):
            canonical_json([1, 2, float("nan")])

    def test_rejects_nan_deeply_nested(self) -> None:
        with pytest.raises(ValueError, match="NaN"):
            canonical_json({"a": {"b": [{"c": float("nan")}]}})

    def test_rejects_infinity_in_dict_value(self) -> None:
        with pytest.raises(ValueError, match="Infinity"):
            canonical_json({"amount": float("inf")})

    def test_accepts_normal_floats(self) -> None:
        result = canonical_json({"value": 3.14, "zero": 0.0, "neg": -1.5})
        assert "3.14" in result

    def test_accepts_primitives(self) -> None:
        result = canonical_json({"str": "hello", "int": 42, "bool": True, "null": None})
        assert '"hello"' in result


class TestStableHashNanRejection:
    """stable_hash delegates to canonical_json, so NaN rejection propagates."""

    def test_rejects_nan(self) -> None:
        with pytest.raises(ValueError, match="NaN"):
            stable_hash({"field": float("nan")})

    def test_accepts_normal_data(self) -> None:
        h = stable_hash({"key": "value"})
        assert len(h) == 64  # SHA-256 hex digest
