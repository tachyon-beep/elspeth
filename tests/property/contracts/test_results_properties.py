# tests/property/contracts/test_results_properties.py
"""Property-based tests for plugin result contracts.

These tests verify the invariants of TransformResult, SourceRow,
and ArtifactDescriptor - the contracts between plugins and the engine:

TransformResult Properties:
- Factory methods produce mutually exclusive states
- is_multi_row and has_output_data properties are correct
- Empty rows list rejected by success_multi
- Audit fields default to None

SourceRow Properties:
- valid() and quarantined() produce distinct states
- Quarantined rows have error and destination

ArtifactDescriptor Properties:
- Factory methods produce correct artifact_type
- content_hash and size_bytes are required
"""

from __future__ import annotations

from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from elspeth.contracts.results import (
    ArtifactDescriptor,
    SourceRow,
    TransformResult,
)

# =============================================================================
# Strategies for generating result data
# =============================================================================

# Row data dictionaries
row_dicts = st.dictionaries(
    keys=st.text(min_size=1, max_size=20, alphabet="abcdefghijklmnopqrstuvwxyz_"),
    values=st.one_of(
        st.none(),
        st.booleans(),
        st.integers(min_value=-1000, max_value=1000),
        st.text(max_size=50),
    ),
    min_size=0,
    max_size=10,
)

# Non-empty row lists
non_empty_row_lists = st.lists(row_dicts, min_size=1, max_size=5)

# Error reason dictionaries
error_reasons = st.dictionaries(
    keys=st.sampled_from(["error", "message", "code", "details"]),
    values=st.one_of(st.text(max_size=50), st.integers()),
    min_size=1,
    max_size=5,
)

# Content hashes (64-char hex)
content_hashes = st.text(min_size=64, max_size=64, alphabet="0123456789abcdef")

# Size in bytes
sizes = st.integers(min_value=0, max_value=1_000_000)

# File paths
file_paths = st.text(
    min_size=1,
    max_size=100,
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789/_.-",
).filter(lambda s: not s.startswith("/") or len(s) > 1)


# =============================================================================
# TransformResult Factory Method Property Tests
# =============================================================================


class TestTransformResultSuccessProperties:
    """Property tests for TransformResult.success() factory."""

    @given(row=row_dicts)
    @settings(max_examples=100)
    def test_success_sets_status(self, row: dict[str, Any]) -> None:
        """Property: success() sets status to 'success'."""
        result = TransformResult.success(row)
        assert result.status == "success"

    @given(row=row_dicts)
    @settings(max_examples=100)
    def test_success_sets_row(self, row: dict[str, Any]) -> None:
        """Property: success() sets row to the provided value."""
        result = TransformResult.success(row)
        assert result.row == row

    @given(row=row_dicts)
    @settings(max_examples=100)
    def test_success_has_no_rows_list(self, row: dict[str, Any]) -> None:
        """Property: success() sets rows to None (single-row output)."""
        result = TransformResult.success(row)
        assert result.rows is None

    @given(row=row_dicts)
    @settings(max_examples=100)
    def test_success_has_no_reason(self, row: dict[str, Any]) -> None:
        """Property: success() sets reason to None."""
        result = TransformResult.success(row)
        assert result.reason is None

    @given(row=row_dicts)
    @settings(max_examples=100)
    def test_success_is_not_multi_row(self, row: dict[str, Any]) -> None:
        """Property: success() result is not multi-row."""
        result = TransformResult.success(row)
        assert result.is_multi_row is False

    @given(row=row_dicts)
    @settings(max_examples=100)
    def test_success_has_output_data(self, row: dict[str, Any]) -> None:
        """Property: success() result has output data."""
        result = TransformResult.success(row)
        assert result.has_output_data is True


class TestTransformResultSuccessMultiProperties:
    """Property tests for TransformResult.success_multi() factory."""

    @given(rows=non_empty_row_lists)
    @settings(max_examples=100)
    def test_success_multi_sets_status(self, rows: list[dict[str, Any]]) -> None:
        """Property: success_multi() sets status to 'success'."""
        result = TransformResult.success_multi(rows)
        assert result.status == "success"

    @given(rows=non_empty_row_lists)
    @settings(max_examples=100)
    def test_success_multi_sets_rows(self, rows: list[dict[str, Any]]) -> None:
        """Property: success_multi() sets rows to the provided list."""
        result = TransformResult.success_multi(rows)
        assert result.rows == rows

    @given(rows=non_empty_row_lists)
    @settings(max_examples=100)
    def test_success_multi_has_no_single_row(self, rows: list[dict[str, Any]]) -> None:
        """Property: success_multi() sets row to None."""
        result = TransformResult.success_multi(rows)
        assert result.row is None

    @given(rows=non_empty_row_lists)
    @settings(max_examples=100)
    def test_success_multi_is_multi_row(self, rows: list[dict[str, Any]]) -> None:
        """Property: success_multi() result is multi-row."""
        result = TransformResult.success_multi(rows)
        assert result.is_multi_row is True

    @given(rows=non_empty_row_lists)
    @settings(max_examples=100)
    def test_success_multi_has_output_data(self, rows: list[dict[str, Any]]) -> None:
        """Property: success_multi() result has output data."""
        result = TransformResult.success_multi(rows)
        assert result.has_output_data is True

    def test_success_multi_rejects_empty_list(self) -> None:
        """Property: success_multi() rejects empty rows list."""
        with pytest.raises(ValueError, match="at least one row"):
            TransformResult.success_multi([])


class TestTransformResultErrorProperties:
    """Property tests for TransformResult.error() factory."""

    @given(reason=error_reasons)
    @settings(max_examples=100)
    def test_error_sets_status(self, reason: dict[str, Any]) -> None:
        """Property: error() sets status to 'error'."""
        result = TransformResult.error(reason)
        assert result.status == "error"

    @given(reason=error_reasons)
    @settings(max_examples=100)
    def test_error_sets_reason(self, reason: dict[str, Any]) -> None:
        """Property: error() sets reason to the provided value."""
        result = TransformResult.error(reason)
        assert result.reason == reason

    @given(reason=error_reasons)
    @settings(max_examples=100)
    def test_error_has_no_row(self, reason: dict[str, Any]) -> None:
        """Property: error() sets row to None."""
        result = TransformResult.error(reason)
        assert result.row is None

    @given(reason=error_reasons)
    @settings(max_examples=100)
    def test_error_has_no_rows(self, reason: dict[str, Any]) -> None:
        """Property: error() sets rows to None."""
        result = TransformResult.error(reason)
        assert result.rows is None

    @given(reason=error_reasons)
    @settings(max_examples=100)
    def test_error_has_no_output_data(self, reason: dict[str, Any]) -> None:
        """Property: error() result has no output data."""
        result = TransformResult.error(reason)
        assert result.has_output_data is False

    @given(reason=error_reasons)
    @settings(max_examples=100)
    def test_error_default_not_retryable(self, reason: dict[str, Any]) -> None:
        """Property: error() defaults to retryable=False."""
        result = TransformResult.error(reason)
        assert result.retryable is False

    @given(reason=error_reasons, retryable=st.booleans())
    @settings(max_examples=50)
    def test_error_respects_retryable_flag(self, reason: dict[str, Any], retryable: bool) -> None:
        """Property: error() respects the retryable parameter."""
        result = TransformResult.error(reason, retryable=retryable)
        assert result.retryable is retryable


class TestTransformResultAuditFieldProperties:
    """Property tests for audit field defaults."""

    @given(row=row_dicts)
    @settings(max_examples=50)
    def test_success_audit_fields_are_none(self, row: dict[str, Any]) -> None:
        """Property: success() leaves audit fields as None."""
        result = TransformResult.success(row)
        assert result.input_hash is None
        assert result.output_hash is None
        assert result.duration_ms is None

    @given(reason=error_reasons)
    @settings(max_examples=50)
    def test_error_audit_fields_are_none(self, reason: dict[str, Any]) -> None:
        """Property: error() leaves audit fields as None."""
        result = TransformResult.error(reason)
        assert result.input_hash is None
        assert result.output_hash is None
        assert result.duration_ms is None


# =============================================================================
# SourceRow Factory Method Property Tests
# =============================================================================


class TestSourceRowValidProperties:
    """Property tests for SourceRow.valid() factory."""

    @given(row=row_dicts)
    @settings(max_examples=100)
    def test_valid_sets_row(self, row: dict[str, Any]) -> None:
        """Property: valid() sets row to the provided value."""
        result = SourceRow.valid(row)
        assert result.row == row

    @given(row=row_dicts)
    @settings(max_examples=100)
    def test_valid_is_not_quarantined(self, row: dict[str, Any]) -> None:
        """Property: valid() sets is_quarantined to False."""
        result = SourceRow.valid(row)
        assert result.is_quarantined is False

    @given(row=row_dicts)
    @settings(max_examples=100)
    def test_valid_has_no_error(self, row: dict[str, Any]) -> None:
        """Property: valid() sets quarantine_error to None."""
        result = SourceRow.valid(row)
        assert result.quarantine_error is None

    @given(row=row_dicts)
    @settings(max_examples=100)
    def test_valid_has_no_destination(self, row: dict[str, Any]) -> None:
        """Property: valid() sets quarantine_destination to None."""
        result = SourceRow.valid(row)
        assert result.quarantine_destination is None


class TestSourceRowQuarantinedProperties:
    """Property tests for SourceRow.quarantined() factory."""

    @given(
        row=st.one_of(row_dicts, st.integers(), st.text(max_size=50)),
        error=st.text(min_size=1, max_size=100),
        destination=st.text(min_size=1, max_size=50, alphabet="abcdefghijklmnopqrstuvwxyz_"),
    )
    @settings(max_examples=100)
    def test_quarantined_sets_row(self, row: Any, error: str, destination: str) -> None:
        """Property: quarantined() sets row to the provided value (any type)."""
        result = SourceRow.quarantined(row, error, destination)
        assert result.row == row

    @given(
        row=row_dicts,
        error=st.text(min_size=1, max_size=100),
        destination=st.text(min_size=1, max_size=50, alphabet="abcdefghijklmnopqrstuvwxyz_"),
    )
    @settings(max_examples=100)
    def test_quarantined_is_quarantined(self, row: dict[str, Any], error: str, destination: str) -> None:
        """Property: quarantined() sets is_quarantined to True."""
        result = SourceRow.quarantined(row, error, destination)
        assert result.is_quarantined is True

    @given(
        row=row_dicts,
        error=st.text(min_size=1, max_size=100),
        destination=st.text(min_size=1, max_size=50, alphabet="abcdefghijklmnopqrstuvwxyz_"),
    )
    @settings(max_examples=100)
    def test_quarantined_sets_error(self, row: dict[str, Any], error: str, destination: str) -> None:
        """Property: quarantined() sets quarantine_error."""
        result = SourceRow.quarantined(row, error, destination)
        assert result.quarantine_error == error

    @given(
        row=row_dicts,
        error=st.text(min_size=1, max_size=100),
        destination=st.text(min_size=1, max_size=50, alphabet="abcdefghijklmnopqrstuvwxyz_"),
    )
    @settings(max_examples=100)
    def test_quarantined_sets_destination(self, row: dict[str, Any], error: str, destination: str) -> None:
        """Property: quarantined() sets quarantine_destination."""
        result = SourceRow.quarantined(row, error, destination)
        assert result.quarantine_destination == destination


class TestSourceRowMutualExclusivityProperties:
    """Property tests for valid/quarantined mutual exclusivity."""

    @given(row=row_dicts)
    @settings(max_examples=50)
    def test_valid_and_quarantined_are_distinguishable(self, row: dict[str, Any]) -> None:
        """Property: valid() and quarantined() produce distinguishable results."""
        valid = SourceRow.valid(row)
        quarantined = SourceRow.quarantined(row, "error", "sink")

        # is_quarantined is the discriminator
        assert valid.is_quarantined is False
        assert quarantined.is_quarantined is True

        # Only quarantined has error and destination
        assert valid.quarantine_error is None
        assert valid.quarantine_destination is None
        assert quarantined.quarantine_error is not None
        assert quarantined.quarantine_destination is not None


# =============================================================================
# ArtifactDescriptor Factory Method Property Tests
# =============================================================================


class TestArtifactDescriptorFileProperties:
    """Property tests for ArtifactDescriptor.for_file() factory."""

    @given(path=file_paths, content_hash=content_hashes, size=sizes)
    @settings(max_examples=100)
    def test_for_file_sets_artifact_type(self, path: str, content_hash: str, size: int) -> None:
        """Property: for_file() sets artifact_type to 'file'."""
        result = ArtifactDescriptor.for_file(path, content_hash, size)
        assert result.artifact_type == "file"

    @given(path=file_paths, content_hash=content_hashes, size=sizes)
    @settings(max_examples=100)
    def test_for_file_sets_path_with_prefix(self, path: str, content_hash: str, size: int) -> None:
        """Property: for_file() prefixes path with 'file://'."""
        result = ArtifactDescriptor.for_file(path, content_hash, size)
        assert result.path_or_uri == f"file://{path}"

    @given(path=file_paths, content_hash=content_hashes, size=sizes)
    @settings(max_examples=100)
    def test_for_file_preserves_hash(self, path: str, content_hash: str, size: int) -> None:
        """Property: for_file() preserves content_hash."""
        result = ArtifactDescriptor.for_file(path, content_hash, size)
        assert result.content_hash == content_hash

    @given(path=file_paths, content_hash=content_hashes, size=sizes)
    @settings(max_examples=100)
    def test_for_file_preserves_size(self, path: str, content_hash: str, size: int) -> None:
        """Property: for_file() preserves size_bytes."""
        result = ArtifactDescriptor.for_file(path, content_hash, size)
        assert result.size_bytes == size


class TestArtifactDescriptorImmutabilityProperties:
    """Property tests for ArtifactDescriptor immutability."""

    @given(path=file_paths, content_hash=content_hashes, size=sizes)
    @settings(max_examples=50)
    def test_artifact_is_frozen(self, path: str, content_hash: str, size: int) -> None:
        """Property: ArtifactDescriptor is immutable (frozen=True)."""
        result = ArtifactDescriptor.for_file(path, content_hash, size)

        with pytest.raises(AttributeError):
            result.artifact_type = "database"  # type: ignore[misc]

        with pytest.raises(AttributeError):
            result.content_hash = "new_hash"  # type: ignore[misc]
