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
