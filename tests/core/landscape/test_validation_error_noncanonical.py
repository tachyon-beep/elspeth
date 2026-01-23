"""Tests for validation error recording with non-canonical data.

Verifies that validation errors can be recorded even when row data is:
1. Non-dict (primitives, lists, etc.)
2. Contains non-finite values (NaN, Infinity)

This is critical for the Three-Tier Trust Model - Tier 3 (external data)
must be quarantined and recorded even when malformed.
"""

import pytest

from elspeth.core.landscape.database import LandscapeDB
from elspeth.core.landscape.recorder import LandscapeRecorder
from elspeth.plugins.context import PluginContext


@pytest.fixture
def recorder():
    """Create in-memory recorder with a registered run."""
    db = LandscapeDB("sqlite:///:memory:")
    rec = LandscapeRecorder(db)

    # Create a run for foreign key constraint
    rec.begin_run(
        config={},
        canonical_version="v1",
        run_id="test-run",
    )

    return rec


class TestValidationErrorNonCanonical:
    """Test validation error recording for non-canonical data."""

    def test_record_primitive_int(self, recorder):
        """Primitive int should be quarantined without crash."""
        ctx = PluginContext(
            run_id="test-run",
            config={},
            node_id="source_node",
            landscape=recorder,
        )

        token = ctx.record_validation_error(
            row=42,
            error="Expected dict, got int",
            schema_mode="dynamic",
            destination="discard",
        )

        assert token.error_id is not None
        assert token.node_id == "source_node"
        assert token.destination == "discard"

    def test_record_primitive_string(self, recorder):
        """Primitive string should be quarantined without crash."""
        ctx = PluginContext(
            run_id="test-run",
            config={},
            node_id="source_node",
            landscape=recorder,
        )

        token = ctx.record_validation_error(
            row="invalid_string",
            error="Expected dict, got str",
            schema_mode="dynamic",
            destination="discard",
        )

        assert token.error_id is not None

    def test_record_list(self, recorder):
        """List should be quarantined without crash."""
        ctx = PluginContext(
            run_id="test-run",
            config={},
            node_id="source_node",
            landscape=recorder,
        )

        token = ctx.record_validation_error(
            row=[1, 2, 3],
            error="Expected dict, got list",
            schema_mode="dynamic",
            destination="discard",
        )

        assert token.error_id is not None

    def test_record_nan_value(self, recorder):
        """Row with NaN should be quarantined without crash."""
        ctx = PluginContext(
            run_id="test-run",
            config={},
            node_id="source_node",
            landscape=recorder,
        )

        token = ctx.record_validation_error(
            row={"value": float("nan")},
            error="Row contains NaN",
            schema_mode="dynamic",
            destination="discard",
        )

        assert token.error_id is not None
        assert token.node_id == "source_node"

    def test_record_infinity_value(self, recorder):
        """Row with Infinity should be quarantined without crash."""
        ctx = PluginContext(
            run_id="test-run",
            config={},
            node_id="source_node",
            landscape=recorder,
        )

        token = ctx.record_validation_error(
            row={"value": float("inf")},
            error="Row contains Infinity",
            schema_mode="dynamic",
            destination="discard",
        )

        assert token.error_id is not None

    def test_record_negative_infinity(self, recorder):
        """Row with -Infinity should be quarantined without crash."""
        ctx = PluginContext(
            run_id="test-run",
            config={},
            node_id="source_node",
            landscape=recorder,
        )

        token = ctx.record_validation_error(
            row={"value": float("-inf")},
            error="Row contains -Infinity",
            schema_mode="dynamic",
            destination="discard",
        )

        assert token.error_id is not None

    def test_audit_trail_contains_repr_fallback(self, recorder):
        """Verify audit trail stores repr() for non-canonical data."""
        ctx = PluginContext(
            run_id="test-run",
            config={},
            node_id="source_node",
            landscape=recorder,
        )

        # Use NaN which actually triggers the fallback (primitives are canonical)
        token = ctx.record_validation_error(
            row={"value": float("nan")},
            error="Row contains NaN",
            schema_mode="dynamic",
            destination="discard",
        )

        # Query the validation_errors table to verify repr storage
        from sqlalchemy import select

        from elspeth.core.landscape.schema import validation_errors_table

        with recorder._db.connection() as conn:
            result = conn.execute(select(validation_errors_table).where(validation_errors_table.c.error_id == token.error_id))
            row = result.fetchone()

            assert row is not None
            # row_data_json should contain repr fallback metadata
            import json

            row_data = json.loads(row.row_data_json)

            # Check that it's a repr fallback (has __repr__ and __type__ keys)
            assert "__repr__" in row_data
            assert "__type__" in row_data
            assert row_data["__type__"] == "dict"
            assert "nan" in row_data["__repr__"].lower()
            assert "__canonical_error__" in row_data

    def test_multiple_non_canonical_rows(self, recorder):
        """Multiple non-canonical rows should all be recorded."""
        ctx = PluginContext(
            run_id="test-run",
            config={},
            node_id="source_node",
            landscape=recorder,
        )

        tokens = []
        test_rows = [
            42,
            "string",
            [1, 2, 3],
            {"nan": float("nan")},
            {"inf": float("inf")},
        ]

        for i, row in enumerate(test_rows):
            token = ctx.record_validation_error(
                row=row,
                error=f"Invalid row {i}",
                schema_mode="dynamic",
                destination="discard",
            )
            tokens.append(token)

        # All should have error_ids
        assert all(t.error_id is not None for t in tokens)

        # All should have unique error_ids
        error_ids = [t.error_id for t in tokens]
        assert len(error_ids) == len(set(error_ids))
