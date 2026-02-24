"""Tests for contracts/hashing.py — NaN/Infinity rejection and primitives."""

from datetime import UTC, datetime

import pytest

from elspeth.contracts import hashing as contracts_hashing
from elspeth.contracts.hashing import CANONICAL_VERSION, canonical_json, repr_hash, stable_hash
from elspeth.core import canonical as core_canonical
from elspeth.core.canonical import CANONICAL_VERSION as CORE_VERSION


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


class TestReprHash:
    """Tests for repr_hash()."""

    def test_produces_sha256_hex(self) -> None:
        result = repr_hash({"key": "value"})
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_deterministic(self) -> None:
        obj = {"key": "value", "num": 42}
        assert repr_hash(obj) == repr_hash(obj)

    def test_handles_non_serializable(self) -> None:
        repr_hash(datetime.now(UTC))  # must not raise


class TestCanonicalVersion:
    """Tests for the CANONICAL_VERSION constant."""

    def test_is_string(self) -> None:
        assert isinstance(CANONICAL_VERSION, str)

    def test_contains_sha256(self) -> None:
        assert "sha256" in CANONICAL_VERSION

    def test_contains_rfc8785(self) -> None:
        assert "rfc8785" in CANONICAL_VERSION

    def test_matches_core_canonical(self) -> None:
        assert CANONICAL_VERSION == CORE_VERSION


class TestCanonicalJsonTypeRejection:
    """Tests for non-JSON-safe types passed to canonical_json."""

    def test_rejects_datetime(self) -> None:
        with pytest.raises((TypeError, ValueError)):
            canonical_json({"ts": datetime.now(UTC)})

    def test_rejects_set(self) -> None:
        with pytest.raises((TypeError, ValueError)):
            canonical_json({"s": {1, 2, 3}})

    def test_rejects_bytes(self) -> None:
        with pytest.raises((TypeError, ValueError)):
            canonical_json({"b": b"hello"})


class TestCanonicalJsonConsistency:
    """Tests that contracts hashing matches core canonical for primitive data."""

    def test_matches_core_canonical_for_primitives(self) -> None:
        data = {"str": "hello", "int": 42, "bool": True, "null": None, "float": 3.14}
        assert contracts_hashing.canonical_json(data) == core_canonical.canonical_json(data)

    def test_stable_hash_matches_core(self) -> None:
        data = {"str": "hello", "int": 42, "bool": True, "null": None, "float": 3.14}
        assert contracts_hashing.stable_hash(data) == core_canonical.stable_hash(data)
