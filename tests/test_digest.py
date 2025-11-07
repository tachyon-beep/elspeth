"""Tests for content-based digest computation."""

import pandas as pd
import pytest

from elspeth.core.security.digest import (
    compute_dataframe_digest,
    compute_digest_for_frame,
    verify_digest,
)


def test_compute_dataframe_digest_deterministic():
    """Test that same DataFrame produces same digest."""
    df = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})

    digest1 = compute_dataframe_digest(df)
    digest2 = compute_dataframe_digest(df)

    assert digest1 == digest2, "Same DataFrame should produce same digest"
    assert len(digest1) == 32, "Digest should be 32 bytes"


def test_compute_dataframe_digest_content_change():
    """Test that digest changes when data changes."""
    df1 = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
    df2 = pd.DataFrame({"a": [1, 2, 999], "b": [4, 5, 6]})  # Changed one value

    digest1 = compute_dataframe_digest(df1)
    digest2 = compute_dataframe_digest(df2)

    assert digest1 != digest2, "Different data should produce different digests"


def test_compute_dataframe_digest_schema_change():
    """Test that digest changes when schema changes."""
    df1 = pd.DataFrame({"a": [1, 2, 3]})
    df2 = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})  # Added column

    digest1 = compute_dataframe_digest(df1)
    digest2 = compute_dataframe_digest(df2)

    assert digest1 != digest2, "Different schema should produce different digests"


def test_compute_dataframe_digest_row_order():
    """Test that digest changes when row order changes."""
    df1 = pd.DataFrame({"a": [1, 2, 3]})
    df2 = pd.DataFrame({"a": [3, 2, 1]})  # Reversed order

    digest1 = compute_dataframe_digest(df1)
    digest2 = compute_dataframe_digest(df2)

    assert digest1 != digest2, "Different row order should produce different digests"


def test_compute_dataframe_digest_empty():
    """Test digest computation on empty DataFrame."""
    df = pd.DataFrame()

    digest = compute_dataframe_digest(df)

    assert len(digest) == 32, "Empty DataFrame should produce 32-byte digest"


def test_compute_dataframe_digest_types():
    """Test digest computation with various data types."""
    df = pd.DataFrame(
        {
            "int_col": [1, 2, 3],
            "float_col": [1.1, 2.2, 3.3],
            "str_col": ["a", "b", "c"],
            "bool_col": [True, False, True],
        }
    )

    digest = compute_dataframe_digest(df)

    assert len(digest) == 32, "Mixed types should produce 32-byte digest"


def test_compute_digest_for_frame_binds_frame_id():
    """Test that digest binds to frame_id."""
    df = pd.DataFrame({"a": [1, 2, 3]})
    frame_id1 = b"\x01" * 16
    frame_id2 = b"\x02" * 16
    level = 2

    digest1 = compute_digest_for_frame(df, frame_id1, level)
    digest2 = compute_digest_for_frame(df, frame_id2, level)

    assert digest1 != digest2, "Different frame_id should produce different digests"


def test_compute_digest_for_frame_binds_level():
    """Test that digest binds to security level."""
    df = pd.DataFrame({"a": [1, 2, 3]})
    frame_id = b"\x01" * 16
    level1 = 2
    level2 = 3

    digest1 = compute_digest_for_frame(df, frame_id, level1)
    digest2 = compute_digest_for_frame(df, frame_id, level2)

    assert digest1 != digest2, "Different level should produce different digests"


def test_verify_digest_success():
    """Test successful digest verification."""
    df = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
    expected_digest = compute_dataframe_digest(df)

    result = verify_digest(df, expected_digest)

    assert result is True, "Matching digest should verify successfully"


def test_verify_digest_failure():
    """Test failed digest verification."""
    df1 = pd.DataFrame({"a": [1, 2, 3]})
    df2 = pd.DataFrame({"a": [1, 2, 999]})  # Different data

    digest1 = compute_dataframe_digest(df1)

    result = verify_digest(df2, digest1)

    assert result is False, "Non-matching digest should fail verification"


def test_compute_dataframe_digest_reproducible_across_copies():
    """Test that digest is same for DataFrame copies."""
    df1 = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
    df2 = df1.copy()  # Create independent copy

    digest1 = compute_dataframe_digest(df1)
    digest2 = compute_dataframe_digest(df2)

    assert digest1 == digest2, "DataFrame copy should produce same digest"


def test_compute_dataframe_digest_column_order_independence():
    """Test that digest is same regardless of column order (canonicalization)."""
    df1 = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6], "c": [7, 8, 9]})
    df2 = pd.DataFrame({"c": [7, 8, 9], "a": [1, 2, 3], "b": [4, 5, 6]})  # Different column order

    digest1 = compute_dataframe_digest(df1)
    digest2 = compute_dataframe_digest(df2)

    assert digest1 == digest2, "Column reordering should not change digest (canonical sorting)"


def test_compute_dataframe_digest_row_order_independence_with_explicit_index():
    """Test that digest is same for reordered rows when index determines identity."""
    df1 = pd.DataFrame({"a": [1, 2, 3]}, index=[0, 1, 2])
    df2 = pd.DataFrame({"a": [3, 2, 1]}, index=[2, 1, 0])  # Same data, different order

    digest1 = compute_dataframe_digest(df1)
    digest2 = compute_dataframe_digest(df2)

    assert digest1 == digest2, "Row reordering should not change digest when indexed correctly"


def test_compute_dataframe_digest_heterogeneous_columns():
    """Test digest with mixed int/string column names (heterogeneous labels)."""
    df = pd.DataFrame({
        "col_a": [1, 2, 3],
        1: [4, 5, 6],
        "col_b": [7, 8, 9],
        0: [10, 11, 12],
    })

    # Should not raise TypeError during canonicalization
    digest = compute_dataframe_digest(df)

    assert len(digest) == 32, "Heterogeneous columns should produce valid digest"


def test_compute_dataframe_digest_categorical_dtype():
    """Test digest with categorical dtype (extension type conversion)."""
    df = pd.DataFrame({
        "category": pd.Categorical(["a", "b", "c", "a"]),
        "value": [1, 2, 3, 4],
    })

    # Should not raise during type-safe conversion
    digest = compute_dataframe_digest(df)

    assert len(digest) == 32, "Categorical dtype should be handled via _as_type_safe()"


def test_compute_dataframe_digest_datetime_with_timezone():
    """Test digest with timezone-aware datetime (extension type conversion)."""
    import datetime
    df = pd.DataFrame({
        "timestamp": pd.date_range("2025-01-01", periods=3, freq="h", tz="US/Eastern"),
        "value": [1, 2, 3],
    })

    # Should not raise during type-safe conversion (tz-aware → UTC → tz-naive)
    digest = compute_dataframe_digest(df)

    assert len(digest) == 32, "Timezone-aware datetime should be handled via _as_type_safe()"


def test_compute_dataframe_digest_datetime_without_timezone():
    """Test digest with timezone-naive datetime (hits return series path)."""
    df = pd.DataFrame({
        "timestamp": pd.date_range("2025-01-01", periods=3, freq="h"),
        "value": [1, 2, 3],
    })

    # Should not raise - hits line 141 return series path
    digest = compute_dataframe_digest(df)

    assert len(digest) == 32, "Timezone-naive datetime should be handled correctly"


def test_compute_dataframe_digest_period_dtype():
    """Test digest with Period dtype (extension type conversion)."""
    df = pd.DataFrame({
        "period": pd.period_range("2025-01", periods=3, freq="M"),
        "value": [1, 2, 3],
    })

    # Should not raise during type-safe conversion (Period → str)
    digest = compute_dataframe_digest(df)

    assert len(digest) == 32, "Period dtype should be handled via _as_type_safe()"


def test_compute_dataframe_digest_interval_dtype():
    """Test digest with Interval dtype (extension type conversion)."""
    df = pd.DataFrame({
        "interval": pd.IntervalIndex.from_tuples([(0, 1), (1, 2), (2, 3)]),
        "value": [1, 2, 3],
    })

    # Should not raise during type-safe conversion (Interval → str)
    digest = compute_dataframe_digest(df)

    assert len(digest) == 32, "Interval dtype should be handled via _as_type_safe()"


def test_compute_dataframe_digest_sparse_dtype():
    """Test digest with Sparse dtype (extension type conversion)."""
    df = pd.DataFrame({
        "sparse": pd.arrays.SparseArray([1, 0, 0, 2, 0]),
        "value": [1, 2, 3, 4, 5],
    })

    # Should not raise during type-safe conversion (Sparse → dense)
    digest = compute_dataframe_digest(df)

    assert len(digest) == 32, "Sparse dtype should be handled via _as_type_safe()"


def test_compute_dataframe_digest_unsupported_dtype():
    """Test that unsupported dtypes raise clear error."""
    # Create DataFrame with complex numbers (unsupported by Arrow/Parquet)
    df = pd.DataFrame({
        "complex": [1 + 2j, 3 + 4j, 5 + 6j],
        "value": [1, 2, 3],
    })

    # Should raise ValueError with clear message about unsupported dtype
    with pytest.raises(ValueError, match="Unsupported dtype.*complex.*Cannot safely encode"):
        compute_dataframe_digest(df)


def test_compute_dataframe_digest_error_with_column_context():
    """Test that dtype errors include column name in message."""
    # Create DataFrame with unsupported dtype in specific column
    df = pd.DataFrame({
        "good_col": [1, 2, 3],
        "bad_col": [1 + 2j, 3 + 4j, 5 + 6j],  # Complex numbers unsupported
    })

    # Should raise ValueError mentioning the problematic column name
    with pytest.raises(ValueError, match="Column 'bad_col'"):
        compute_dataframe_digest(df)
