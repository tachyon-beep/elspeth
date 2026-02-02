"""Tests for type normalization utility.

This module tests normalize_type_for_contract() which converts numpy/pandas
types to Python primitives for consistent contract storage and validation.
"""

from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest


class TestNormalizeTypeForContract:
    """Tests for normalize_type_for_contract function."""

    # -------------------------------------------------------------------------
    # Python primitives pass through
    # -------------------------------------------------------------------------

    def test_none_returns_nonetype(self) -> None:
        """None -> type(None)."""
        from elspeth.contracts.type_normalization import normalize_type_for_contract

        result = normalize_type_for_contract(None)
        assert result is type(None)

    def test_int_returns_int(self) -> None:
        """42 -> int."""
        from elspeth.contracts.type_normalization import normalize_type_for_contract

        result = normalize_type_for_contract(42)
        assert result is int

    def test_str_returns_str(self) -> None:
        """'hello' -> str."""
        from elspeth.contracts.type_normalization import normalize_type_for_contract

        result = normalize_type_for_contract("hello")
        assert result is str

    def test_float_returns_float(self) -> None:
        """3.14 -> float."""
        from elspeth.contracts.type_normalization import normalize_type_for_contract

        result = normalize_type_for_contract(3.14)
        assert result is float

    def test_bool_returns_bool(self) -> None:
        """True -> bool."""
        from elspeth.contracts.type_normalization import normalize_type_for_contract

        result = normalize_type_for_contract(True)
        assert result is bool

    # -------------------------------------------------------------------------
    # NumPy types normalize to primitives
    # -------------------------------------------------------------------------

    def test_numpy_int64_returns_int(self) -> None:
        """np.int64(42) -> int."""
        from elspeth.contracts.type_normalization import normalize_type_for_contract

        result = normalize_type_for_contract(np.int64(42))
        assert result is int

    def test_numpy_int32_returns_int(self) -> None:
        """np.int32(42) -> int."""
        from elspeth.contracts.type_normalization import normalize_type_for_contract

        result = normalize_type_for_contract(np.int32(42))
        assert result is int

    def test_numpy_float64_returns_float(self) -> None:
        """np.float64(3.14) -> float."""
        from elspeth.contracts.type_normalization import normalize_type_for_contract

        result = normalize_type_for_contract(np.float64(3.14))
        assert result is float

    def test_numpy_float32_returns_float(self) -> None:
        """np.float32(3.14) -> float."""
        from elspeth.contracts.type_normalization import normalize_type_for_contract

        result = normalize_type_for_contract(np.float32(3.14))
        assert result is float

    def test_numpy_bool_returns_bool(self) -> None:
        """np.bool_(True) -> bool."""
        from elspeth.contracts.type_normalization import normalize_type_for_contract

        result = normalize_type_for_contract(np.bool_(True))
        assert result is bool

    # -------------------------------------------------------------------------
    # Pandas types normalize to primitives
    # -------------------------------------------------------------------------

    def test_pandas_timestamp_returns_datetime(self) -> None:
        """pd.Timestamp('2024-01-01') -> datetime."""
        from elspeth.contracts.type_normalization import normalize_type_for_contract

        result = normalize_type_for_contract(pd.Timestamp("2024-01-01"))
        assert result is datetime

    def test_numpy_datetime64_returns_datetime(self) -> None:
        """np.datetime64('2024-01-01') -> datetime."""
        from elspeth.contracts.type_normalization import normalize_type_for_contract

        result = normalize_type_for_contract(np.datetime64("2024-01-01"))
        assert result is datetime

    # -------------------------------------------------------------------------
    # NaN/Infinity rejection (Tier 1 audit integrity)
    # -------------------------------------------------------------------------

    def test_float_nan_raises_valueerror(self) -> None:
        """float('nan') raises ValueError with 'non-finite'."""
        from elspeth.contracts.type_normalization import normalize_type_for_contract

        with pytest.raises(ValueError, match="non-finite"):
            normalize_type_for_contract(float("nan"))

    def test_float_inf_raises_valueerror(self) -> None:
        """float('inf') raises ValueError with 'non-finite'."""
        from elspeth.contracts.type_normalization import normalize_type_for_contract

        with pytest.raises(ValueError, match="non-finite"):
            normalize_type_for_contract(float("inf"))

    def test_float_negative_inf_raises_valueerror(self) -> None:
        """float('-inf') raises ValueError with 'non-finite'."""
        from elspeth.contracts.type_normalization import normalize_type_for_contract

        with pytest.raises(ValueError, match="non-finite"):
            normalize_type_for_contract(float("-inf"))

    def test_numpy_nan_raises_valueerror(self) -> None:
        """np.nan raises ValueError."""
        from elspeth.contracts.type_normalization import normalize_type_for_contract

        with pytest.raises(ValueError, match="non-finite"):
            normalize_type_for_contract(np.nan)

    def test_numpy_inf_raises_valueerror(self) -> None:
        """np.inf raises ValueError."""
        from elspeth.contracts.type_normalization import normalize_type_for_contract

        with pytest.raises(ValueError, match="non-finite"):
            normalize_type_for_contract(np.inf)

    def test_numpy_float64_nan_raises_valueerror(self) -> None:
        """np.float64('nan') raises ValueError."""
        from elspeth.contracts.type_normalization import normalize_type_for_contract

        with pytest.raises(ValueError, match="non-finite"):
            normalize_type_for_contract(np.float64("nan"))

    def test_numpy_float64_inf_raises_valueerror(self) -> None:
        """np.float64('inf') raises ValueError."""
        from elspeth.contracts.type_normalization import normalize_type_for_contract

        with pytest.raises(ValueError, match="non-finite"):
            normalize_type_for_contract(np.float64("inf"))

    # -------------------------------------------------------------------------
    # Unknown types pass through
    # -------------------------------------------------------------------------

    def test_list_returns_list(self) -> None:
        """[1, 2, 3] -> list."""
        from elspeth.contracts.type_normalization import normalize_type_for_contract

        result = normalize_type_for_contract([1, 2, 3])
        assert result is list

    def test_dict_returns_dict(self) -> None:
        """{'a': 1} -> dict."""
        from elspeth.contracts.type_normalization import normalize_type_for_contract

        result = normalize_type_for_contract({"a": 1})
        assert result is dict

    def test_tuple_returns_tuple(self) -> None:
        """(1, 2, 3) -> tuple."""
        from elspeth.contracts.type_normalization import normalize_type_for_contract

        result = normalize_type_for_contract((1, 2, 3))
        assert result is tuple

    def test_set_returns_set(self) -> None:
        """{1, 2, 3} -> set."""
        from elspeth.contracts.type_normalization import normalize_type_for_contract

        result = normalize_type_for_contract({1, 2, 3})
        assert result is set

    def test_custom_class_returns_class_type(self) -> None:
        """Custom class instance returns its type."""
        from elspeth.contracts.type_normalization import normalize_type_for_contract

        class CustomClass:
            pass

        obj = CustomClass()
        result = normalize_type_for_contract(obj)
        assert result is CustomClass


class TestEdgeCases:
    """Edge cases for type normalization."""

    def test_numpy_str_returns_str(self) -> None:
        """np.str_('hello') -> str."""
        from elspeth.contracts.type_normalization import normalize_type_for_contract

        result = normalize_type_for_contract(np.str_("hello"))
        assert result is str

    def test_zero_float_is_valid(self) -> None:
        """0.0 is a valid float (not NaN/Infinity)."""
        from elspeth.contracts.type_normalization import normalize_type_for_contract

        result = normalize_type_for_contract(0.0)
        assert result is float

    def test_negative_float_is_valid(self) -> None:
        """-3.14 is a valid float."""
        from elspeth.contracts.type_normalization import normalize_type_for_contract

        result = normalize_type_for_contract(-3.14)
        assert result is float

    def test_numpy_zero_is_valid(self) -> None:
        """np.float64(0.0) is a valid float."""
        from elspeth.contracts.type_normalization import normalize_type_for_contract

        result = normalize_type_for_contract(np.float64(0.0))
        assert result is float

    def test_bool_false_returns_bool(self) -> None:
        """False -> bool (not confused with 0)."""
        from elspeth.contracts.type_normalization import normalize_type_for_contract

        result = normalize_type_for_contract(False)
        assert result is bool

    def test_empty_string_returns_str(self) -> None:
        """'' -> str."""
        from elspeth.contracts.type_normalization import normalize_type_for_contract

        result = normalize_type_for_contract("")
        assert result is str

    def test_datetime_returns_datetime(self) -> None:
        """Native datetime passes through."""
        from elspeth.contracts.type_normalization import normalize_type_for_contract

        result = normalize_type_for_contract(datetime(2024, 1, 1, tzinfo=UTC))
        assert result is datetime
