"""Tests for database operation helpers."""


class TestDatabaseOpsTier1Validation:
    """Test Tier-1 audit integrity: crash on zero-row updates/inserts."""

    def test_execute_update_crashes_on_zero_rows_affected(self) -> None:
        """execute_update raises ValueError when zero rows are affected.

        Per Data Manifesto (Tier-1): "Bad data in the audit trail = crash immediately"
        Silent no-ops on missing IDs violate audit integrity.
        """
        from elspeth.core.landscape import LandscapeDB
        from elspeth.core.landscape._database_ops import DatabaseOps
        from elspeth.core.landscape.recorder import LandscapeRecorder
        from elspeth.core.landscape.schema import runs_table

        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        _ = recorder.begin_run(config={}, canonical_version="v1")

        # Try to update a nonexistent run - should crash, not silently no-op
        ops = DatabaseOps(db)
        update_stmt = runs_table.update().where(runs_table.c.run_id == "nonexistent_run_id").values(status="completed")

        # Should raise ValueError on zero rows affected
        import pytest

        with pytest.raises(ValueError, match="zero rows affected"):
            ops.execute_update(update_stmt)

    def test_execute_update_succeeds_on_valid_update(self) -> None:
        """execute_update succeeds when exactly one row is affected."""
        from elspeth.contracts import RunStatus
        from elspeth.core.landscape import LandscapeDB
        from elspeth.core.landscape._database_ops import DatabaseOps
        from elspeth.core.landscape.recorder import LandscapeRecorder
        from elspeth.core.landscape.schema import runs_table

        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        run = recorder.begin_run(config={}, canonical_version="v1")

        # Update existing run - should succeed
        ops = DatabaseOps(db)
        update_stmt = runs_table.update().where(runs_table.c.run_id == run.run_id).values(status=RunStatus.COMPLETED.value)

        # Should not raise - exactly 1 row affected
        ops.execute_update(update_stmt)
