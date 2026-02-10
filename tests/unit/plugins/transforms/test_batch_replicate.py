"""Tests for BatchReplicate aggregation transform.

BatchReplicate replicates rows based on a copies field. It is batch-aware,
meaning it receives lists of rows when aggregation triggers fire.

Contract enforcement tests verify that wrong types raise TypeError per
the Tier 2 trust model - transforms must not coerce pipeline data types.
"""

import pytest

from elspeth.contracts.plugin_context import PluginContext
from elspeth.testing import make_pipeline_row

# Common schema config for dynamic field handling (accepts any fields)
DYNAMIC_SCHEMA = {"mode": "observed"}


class TestBatchReplicateHappyPath:
    """Happy path tests for BatchReplicate transform."""

    @pytest.fixture
    def ctx(self) -> PluginContext:
        """Create minimal plugin context."""
        return PluginContext(run_id="test-run", config={})

    def test_has_required_attributes(self) -> None:
        """BatchReplicate has name and is_batch_aware."""
        from elspeth.plugins.transforms.batch_replicate import BatchReplicate

        assert BatchReplicate.name == "batch_replicate"
        assert BatchReplicate.is_batch_aware is True

    def test_replicates_rows_by_copies_field(self, ctx: PluginContext) -> None:
        """BatchReplicate creates N copies of each row based on copies field."""
        from elspeth.plugins.transforms.batch_replicate import BatchReplicate

        transform = BatchReplicate(
            {
                "schema": DYNAMIC_SCHEMA,
                "copies_field": "copies",
            }
        )

        rows = [
            make_pipeline_row({"id": 1, "copies": 2}),
            make_pipeline_row({"id": 2, "copies": 3}),
            make_pipeline_row({"id": 3, "copies": 1}),
        ]

        result = transform.process(rows, ctx)

        assert result.status == "success"
        assert result.rows is not None
        assert len(result.rows) == 6  # 2 + 3 + 1
        # Check copy indices
        assert result.rows[0]["copy_index"] == 0
        assert result.rows[1]["copy_index"] == 1
        assert result.rows[2]["copy_index"] == 0
        assert result.rows[3]["copy_index"] == 1
        assert result.rows[4]["copy_index"] == 2

    def test_uses_default_copies_when_field_missing(self, ctx: PluginContext) -> None:
        """Missing copies field uses default_copies value."""
        from elspeth.plugins.transforms.batch_replicate import BatchReplicate

        transform = BatchReplicate(
            {
                "schema": DYNAMIC_SCHEMA,
                "copies_field": "copies",
                "default_copies": 2,
            }
        )

        rows = [
            make_pipeline_row({"id": 1}),  # No copies field - use default
            make_pipeline_row({"id": 2, "copies": 3}),
        ]

        result = transform.process(rows, ctx)

        assert result.status == "success"
        assert result.rows is not None
        assert len(result.rows) == 5  # 2 (default) + 3

    def test_empty_batch_returns_marker(self, ctx: PluginContext) -> None:
        """Empty batch returns success with marker row."""
        from elspeth.plugins.transforms.batch_replicate import BatchReplicate

        transform = BatchReplicate(
            {
                "schema": DYNAMIC_SCHEMA,
                "copies_field": "copies",
            }
        )

        result = transform.process([], ctx)

        assert result.status == "success"
        assert result.row is not None
        assert result.row["batch_empty"] is True


class TestBatchReplicateTypeEnforcement:
    """Contract enforcement tests - transforms must not coerce types.

    Per CLAUDE.md Tier 2 trust model and docs/contracts/plugin-protocol.md:
    Transforms receive pipeline data that should already be type-validated.
    Wrong types indicate upstream bugs and must raise TypeError, not be coerced.
    """

    @pytest.fixture
    def ctx(self) -> PluginContext:
        """Create minimal plugin context."""
        return PluginContext(run_id="test-run", config={})

    def test_string_copies_raises_type_error(self, ctx: PluginContext) -> None:
        """String value in copies field raises TypeError (no coercion)."""
        from elspeth.plugins.transforms.batch_replicate import BatchReplicate

        transform = BatchReplicate(
            {
                "schema": DYNAMIC_SCHEMA,
                "copies_field": "copies",
            }
        )

        rows = [make_pipeline_row({"id": 1, "copies": "3"})]  # String "3" instead of int 3

        with pytest.raises(TypeError, match="must be int, got str"):
            transform.process(rows, ctx)

    def test_float_copies_raises_type_error(self, ctx: PluginContext) -> None:
        """Float value in copies field raises TypeError (no coercion)."""
        from elspeth.plugins.transforms.batch_replicate import BatchReplicate

        transform = BatchReplicate(
            {
                "schema": DYNAMIC_SCHEMA,
                "copies_field": "copies",
            }
        )

        rows = [make_pipeline_row({"id": 1, "copies": 3.5})]  # Float instead of int

        with pytest.raises(TypeError, match="must be int, got float"):
            transform.process(rows, ctx)

    def test_none_copies_raises_type_error(self, ctx: PluginContext) -> None:
        """None value in copies field raises TypeError."""
        from elspeth.plugins.transforms.batch_replicate import BatchReplicate

        transform = BatchReplicate(
            {
                "schema": DYNAMIC_SCHEMA,
                "copies_field": "copies",
            }
        )

        rows = [make_pipeline_row({"id": 1, "copies": None})]

        with pytest.raises(TypeError, match="must be int, got NoneType"):
            transform.process(rows, ctx)

    def test_zero_copies_returns_error_when_all_invalid(self, ctx: PluginContext) -> None:
        """All rows with zero copies returns error result (no valid output to expand)."""
        from elspeth.plugins.transforms.batch_replicate import BatchReplicate

        transform = BatchReplicate(
            {
                "schema": DYNAMIC_SCHEMA,
                "copies_field": "copies",
            }
        )

        rows = [make_pipeline_row({"id": 1, "copies": 0})]

        result = transform.process(rows, ctx)
        assert result.status == "error"
        assert result.reason is not None
        assert result.reason["reason"] == "all_rows_failed"
        assert "1 rows quarantined" in result.reason["error"]
        assert result.reason["row_errors"][0]["reason"] == "invalid_copies"

    def test_negative_copies_returns_error_when_all_invalid(self, ctx: PluginContext) -> None:
        """All rows with negative copies returns error result."""
        from elspeth.plugins.transforms.batch_replicate import BatchReplicate

        transform = BatchReplicate(
            {
                "schema": DYNAMIC_SCHEMA,
                "copies_field": "copies",
            }
        )

        rows = [make_pipeline_row({"id": 1, "copies": -1})]

        result = transform.process(rows, ctx)
        assert result.status == "error"
        assert result.reason is not None
        assert result.reason["reason"] == "all_rows_failed"
        assert result.reason["row_errors"][0]["reason"] == "invalid_copies"

    def test_invalid_copies_quarantined_alongside_valid_rows(self, ctx: PluginContext) -> None:
        """Rows with invalid copies are quarantined; valid rows still replicated."""
        from elspeth.plugins.transforms.batch_replicate import BatchReplicate

        transform = BatchReplicate(
            {
                "schema": DYNAMIC_SCHEMA,
                "copies_field": "copies",
            }
        )

        rows = [
            make_pipeline_row({"id": 1, "copies": -1}),
            make_pipeline_row({"id": 2, "copies": 2}),
        ]

        result = transform.process(rows, ctx)
        assert result.status == "success"
        assert result.rows is not None
        assert len(result.rows) == 2  # Only valid copies of row 2
        assert result.rows[0]["id"] == 2
        assert result.rows[0]["copy_index"] == 0
        assert result.rows[1]["id"] == 2
        assert result.rows[1]["copy_index"] == 1
        # Quarantine info in success_reason.metadata
        assert result.success_reason is not None
        assert result.success_reason["metadata"]["quarantined_count"] == 1
        assert result.success_reason["metadata"]["quarantined"][0]["reason"] == "invalid_copies"
        assert result.success_reason["metadata"]["quarantined"][0]["row_data"]["id"] == 1

    def test_error_message_indicates_upstream_bug(self, ctx: PluginContext) -> None:
        """Error message explicitly indicates upstream validation bug."""
        from elspeth.plugins.transforms.batch_replicate import BatchReplicate

        transform = BatchReplicate(
            {
                "schema": DYNAMIC_SCHEMA,
                "copies_field": "copies",
            }
        )

        rows = [make_pipeline_row({"id": 1, "copies": "invalid"})]

        with pytest.raises(TypeError, match="upstream validation bug"):
            transform.process(rows, ctx)


class TestBatchReplicateConfigValidation:
    """Config validation tests."""

    def test_default_copies_zero_rejected(self) -> None:
        """Config with default_copies=0 is rejected at validation time."""
        from elspeth.plugins.config_base import PluginConfigError
        from elspeth.plugins.transforms.batch_replicate import BatchReplicate

        with pytest.raises(PluginConfigError, match="default_copies"):
            BatchReplicate(
                {
                    "schema": {"mode": "observed"},
                    "default_copies": 0,
                }
            )

    def test_default_copies_negative_rejected(self) -> None:
        """Config with negative default_copies is rejected at validation time."""
        from elspeth.plugins.config_base import PluginConfigError
        from elspeth.plugins.transforms.batch_replicate import BatchReplicate

        with pytest.raises(PluginConfigError, match="default_copies"):
            BatchReplicate(
                {
                    "schema": {"mode": "observed"},
                    "default_copies": -1,
                }
            )


class TestBatchReplicateSchemaContract:
    """Schema contract tests."""

    def test_output_schema_is_observed_when_copy_index_enabled(self) -> None:
        """Output schema is dynamic to accommodate copy_index field."""
        from elspeth.plugins.transforms.batch_replicate import BatchReplicate

        transform = BatchReplicate(
            {
                "schema": {"fields": [{"id": "int"}], "mode": "fixed"},
                "include_copy_index": True,
            }
        )

        # Output schema should accept the copy_index field (dynamic schema)
        output_schema = transform.output_schema
        # Dynamic schemas accept any fields
        validated = output_schema.model_validate({"id": 1, "copy_index": 0})
        assert validated.copy_index == 0  # type: ignore[attr-defined]

    def test_output_schema_accepts_copy_index_field(self) -> None:
        """Output schema validation passes for rows with copy_index."""
        from elspeth.plugins.transforms.batch_replicate import BatchReplicate

        transform = BatchReplicate(
            {
                "schema": {"mode": "observed"},
                "include_copy_index": True,
            }
        )

        # Simulate what process() outputs
        output_row = {"original_field": "value", "copy_index": 2}
        # This should not raise
        transform.output_schema.model_validate(output_row)
