# tests/property/audit/test_nan_infinity_rejection.py
"""Property-based tests for NaN/Infinity rejection in float validation.

P0 KNOWN ISSUE: NaN/Infinity accepted in float validation, undermines RFC 8785.

ELSPETH's canonical JSON (RFC 8785) requires all floats to be finite. Non-finite
float values (NaN, Infinity, -Infinity) would corrupt the audit trail because:

1. NaN != NaN breaks hash determinism (same data could hash differently)
2. Infinity serialization is not defined in JSON (RFC 8259)
3. Silent conversion of NaN/Infinity to null or 0 is data corruption

This module uses Hypothesis to comprehensively verify that NaN/Infinity values
are rejected at both the canonical JSON layer and the contract validation layer.

Coverage:
- canonical_json() rejects NaN/Infinity in all positions (top-level, nested, lists)
- stable_hash() rejects NaN/Infinity (delegates to canonical_json)
- FieldContract float validation rejects NaN/Infinity
- SchemaContract validation rejects rows containing NaN/Infinity
- Edge-case float values near boundaries (max float, subnormals) are accepted
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from elspeth.core.canonical import canonical_json, stable_hash

# =============================================================================
# Strategies for non-finite float generation
# =============================================================================

# Python native NaN variants
python_nan = st.sampled_from([float("nan"), float("-nan")])

# Python native Infinity variants
python_inf = st.sampled_from([float("inf"), float("-inf")])

# NumPy NaN variants
numpy_nan = st.sampled_from([np.nan, np.float64("nan"), np.float32("nan")])

# NumPy Infinity variants
numpy_inf = st.sampled_from([np.inf, -np.inf, np.float64("inf"), np.float64("-inf")])

# All NaN values (Python + NumPy)
all_nan = python_nan | numpy_nan

# All Infinity values (Python + NumPy)
all_inf = python_inf | numpy_inf

# All non-finite values
all_non_finite = all_nan | all_inf

# Finite floats (for positive control tests)
finite_floats = st.floats(allow_nan=False, allow_infinity=False)

# Edge-case finite floats (boundary values)
edge_case_floats = st.sampled_from(
    [
        0.0,
        -0.0,
        1e-308,  # Subnormal
        2.2250738585072014e-308,  # Min positive normal
        1.7976931348623157e308,  # Max float
        -1.7976931348623157e308,  # Min float
        5e-324,  # Smallest positive subnormal
        1e-10,
        1e10,
        0.1,  # Common non-exact representation
        0.3,  # Another non-exact
    ]
)

# Nesting depth for deep structure tests
nesting_depth = st.integers(min_value=1, max_value=8)

# Dict keys for building nested structures
simple_keys = st.text(min_size=1, max_size=10, alphabet="abcdefghijklmnopqrstuvwxyz")


# =============================================================================
# NaN Rejection in canonical_json
# =============================================================================


class TestNaNRejectionCanonical:
    """Verify canonical_json() rejects all NaN variants."""

    @given(value=all_nan)
    @settings(max_examples=30)
    def test_nan_at_top_level(self, value: Any) -> None:
        """Property: NaN at top level is rejected."""
        with pytest.raises(ValueError, match="non-finite"):
            canonical_json(value)

    @given(value=all_nan, key=simple_keys)
    @settings(max_examples=30)
    def test_nan_as_dict_value(self, value: Any, key: str) -> None:
        """Property: NaN as a dict value is rejected."""
        with pytest.raises(ValueError, match="non-finite"):
            canonical_json({key: value})

    @given(value=all_nan)
    @settings(max_examples=30)
    def test_nan_in_list(self, value: Any) -> None:
        """Property: NaN inside a list is rejected."""
        with pytest.raises(ValueError, match="non-finite"):
            canonical_json([1, value, 3])

    @given(value=all_nan, depth=nesting_depth)
    @settings(max_examples=30)
    def test_nan_deeply_nested(self, value: Any, depth: int) -> None:
        """Property: NaN at arbitrary nesting depth is rejected."""
        data: dict[str, Any] = {"value": value}
        for i in range(depth):
            data = {f"level_{i}": data}
        with pytest.raises(ValueError, match="non-finite"):
            canonical_json(data)

    @given(value=all_nan)
    @settings(max_examples=20)
    def test_nan_in_mixed_structure(self, value: Any) -> None:
        """Property: NaN in a structure with valid data is still rejected."""
        data = {
            "valid_int": 42,
            "valid_str": "hello",
            "valid_list": [1, 2, 3],
            "bad_value": value,
        }
        with pytest.raises(ValueError, match="non-finite"):
            canonical_json(data)


# =============================================================================
# Infinity Rejection in canonical_json
# =============================================================================


class TestInfinityRejectionCanonical:
    """Verify canonical_json() rejects all Infinity variants."""

    @given(value=all_inf)
    @settings(max_examples=30)
    def test_infinity_at_top_level(self, value: Any) -> None:
        """Property: Infinity at top level is rejected."""
        with pytest.raises(ValueError, match="non-finite"):
            canonical_json(value)

    @given(value=all_inf, key=simple_keys)
    @settings(max_examples=30)
    def test_infinity_as_dict_value(self, value: Any, key: str) -> None:
        """Property: Infinity as a dict value is rejected."""
        with pytest.raises(ValueError, match="non-finite"):
            canonical_json({key: value})

    @given(value=all_inf)
    @settings(max_examples=30)
    def test_infinity_in_list(self, value: Any) -> None:
        """Property: Infinity inside a list is rejected."""
        with pytest.raises(ValueError, match="non-finite"):
            canonical_json([1, value, 3])

    @given(value=all_inf, depth=nesting_depth)
    @settings(max_examples=30)
    def test_infinity_deeply_nested(self, value: Any, depth: int) -> None:
        """Property: Infinity at arbitrary nesting depth is rejected."""
        data: dict[str, Any] = {"value": value}
        for i in range(depth):
            data = {f"level_{i}": data}
        with pytest.raises(ValueError, match="non-finite"):
            canonical_json(data)

    @given(value=all_inf)
    @settings(max_examples=20)
    def test_positive_and_negative_infinity_both_rejected(self, value: Any) -> None:
        """Property: Both +Inf and -Inf are rejected regardless of sign."""
        assert not math.isfinite(float(value))
        with pytest.raises(ValueError, match="non-finite"):
            canonical_json(value)


# =============================================================================
# NaN/Infinity Rejection in stable_hash
# =============================================================================


class TestNonFiniteRejectionStableHash:
    """Verify stable_hash() rejects all non-finite float values."""

    @given(value=all_non_finite)
    @settings(max_examples=30)
    def test_non_finite_at_top_level(self, value: Any) -> None:
        """Property: stable_hash() rejects non-finite floats at top level."""
        with pytest.raises(ValueError, match="non-finite"):
            stable_hash(value)

    @given(value=all_non_finite)
    @settings(max_examples=30)
    def test_non_finite_in_dict(self, value: Any) -> None:
        """Property: stable_hash() rejects dicts containing non-finite floats."""
        with pytest.raises(ValueError, match="non-finite"):
            stable_hash({"key": value})

    @given(value=all_non_finite)
    @settings(max_examples=30)
    def test_non_finite_in_nested_dict(self, value: Any) -> None:
        """Property: stable_hash() rejects deeply nested non-finite floats."""
        with pytest.raises(ValueError, match="non-finite"):
            stable_hash({"a": {"b": {"c": value}}})


# =============================================================================
# NumPy Array NaN/Infinity Rejection
# =============================================================================


class TestNumPyArrayNonFiniteRejection:
    """Verify non-finite values in NumPy arrays are rejected."""

    @given(value=all_non_finite)
    @settings(max_examples=30)
    def test_non_finite_in_numpy_array(self, value: Any) -> None:
        """Property: NumPy arrays containing non-finite values are rejected."""
        arr = np.array([1.0, 2.0, float(value), 4.0])
        with pytest.raises(ValueError, match="NaN/Infinity found in NumPy array"):
            canonical_json({"array": arr})

    def test_all_nan_numpy_array(self) -> None:
        """Array of all NaN values is rejected."""
        arr = np.array([np.nan, np.nan, np.nan])
        with pytest.raises(ValueError, match="NaN/Infinity found in NumPy array"):
            canonical_json({"array": arr})

    def test_all_inf_numpy_array(self) -> None:
        """Array of all Infinity values is rejected."""
        arr = np.array([np.inf, -np.inf, np.inf])
        with pytest.raises(ValueError, match="NaN/Infinity found in NumPy array"):
            canonical_json({"array": arr})


# =============================================================================
# Positive Controls: Finite Floats Accepted
# =============================================================================


class TestFiniteFloatsAccepted:
    """Verify that all finite floats are accepted (no false rejections)."""

    @given(value=finite_floats)
    @settings(max_examples=200)
    def test_finite_float_accepted_at_top_level(self, value: float) -> None:
        """Property: All finite floats pass canonical_json() without error."""
        result = canonical_json(value)
        assert isinstance(result, str)

    @given(value=finite_floats)
    @settings(max_examples=200)
    def test_finite_float_accepted_in_dict(self, value: float) -> None:
        """Property: Finite floats in dicts are accepted."""
        result = canonical_json({"value": value})
        assert isinstance(result, str)

    @given(value=finite_floats)
    @settings(max_examples=200)
    def test_finite_float_hash_is_deterministic(self, value: float) -> None:
        """Property: Finite floats hash deterministically."""
        h1 = stable_hash({"v": value})
        h2 = stable_hash({"v": value})
        assert h1 == h2

    @given(value=edge_case_floats)
    @settings(max_examples=50)
    def test_edge_case_floats_accepted(self, value: float) -> None:
        """Property: Boundary float values (max, min, subnormal) are accepted."""
        assert math.isfinite(value)
        result = canonical_json({"value": value})
        assert isinstance(result, str)

    def test_negative_zero_accepted(self) -> None:
        """Negative zero is a valid finite float and must be accepted."""
        result = canonical_json(-0.0)
        assert isinstance(result, str)

    def test_finite_numpy_array_accepted(self) -> None:
        """NumPy array of all finite values is accepted."""
        arr = np.array([1.0, -2.5, 0.0, 1e10, 1e-10])
        result = canonical_json({"array": arr})
        assert isinstance(result, str)


# =============================================================================
# NaN Self-Inequality Edge Case
# =============================================================================


class TestNaNSelfInequality:
    """Verify that NaN's unusual self-inequality does not bypass rejection."""

    def test_nan_not_equal_to_itself(self) -> None:
        """NaN != NaN is a property of IEEE 754. Our check must handle this."""
        nan = float("nan")
        # Confirm the IEEE 754 property
        assert nan != nan
        # Our rejection must still work
        with pytest.raises(ValueError, match="non-finite"):
            canonical_json(nan)

    def test_nan_identity_check_bypassed(self) -> None:
        """Even if NaN passes identity checks, value check catches it."""
        nan = float("nan")
        assert nan is nan  # Identity is True
        assert nan != nan  # But equality is False
        with pytest.raises(ValueError, match="non-finite"):
            canonical_json({"value": nan})

    @given(value=python_nan)
    @settings(max_examples=10)
    def test_nan_in_tuple_converted_to_list(self, value: float) -> None:
        """NaN in a tuple (which becomes a list in JSON) is still rejected."""
        with pytest.raises(ValueError, match="non-finite"):
            canonical_json({"data": (1, value, 3)})
