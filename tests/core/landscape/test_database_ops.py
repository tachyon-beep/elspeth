"""Tests for database operation helpers."""

from unittest.mock import MagicMock

from elspeth.core.landscape._database_ops import DatabaseOps


class TestDatabaseOps:
    """Test database operation helper methods."""

    def test_execute_fetchone_returns_row(self) -> None:
        """execute_fetchone returns single row from query."""
        mock_db = MagicMock()
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_row = MagicMock(id="row1")

        mock_db.connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_db.connection.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.execute.return_value = mock_result
        mock_result.fetchone.return_value = mock_row

        ops = DatabaseOps(mock_db)
        query = MagicMock()

        result = ops.execute_fetchone(query)

        assert result == mock_row
        mock_conn.execute.assert_called_once_with(query)

    def test_execute_fetchone_returns_none_when_no_row(self) -> None:
        """execute_fetchone returns None when no row found."""
        mock_db = MagicMock()
        mock_conn = MagicMock()
        mock_result = MagicMock()

        mock_db.connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_db.connection.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.execute.return_value = mock_result
        mock_result.fetchone.return_value = None

        ops = DatabaseOps(mock_db)
        result = ops.execute_fetchone(MagicMock())

        assert result is None

    def test_execute_fetchall_returns_list(self) -> None:
        """execute_fetchall returns list of rows."""
        mock_db = MagicMock()
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_rows = [MagicMock(id="row1"), MagicMock(id="row2")]

        mock_db.connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_db.connection.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.execute.return_value = mock_result
        mock_result.fetchall.return_value = mock_rows

        ops = DatabaseOps(mock_db)
        result = ops.execute_fetchall(MagicMock())

        assert result == mock_rows

    def test_execute_insert_commits(self) -> None:
        """execute_insert executes insert statement."""
        mock_db = MagicMock()
        mock_conn = MagicMock()

        mock_db.connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_db.connection.return_value.__exit__ = MagicMock(return_value=False)

        ops = DatabaseOps(mock_db)
        stmt = MagicMock()

        ops.execute_insert(stmt)

        mock_conn.execute.assert_called_once_with(stmt)

    def test_execute_update_commits(self) -> None:
        """execute_update executes update statement."""
        mock_db = MagicMock()
        mock_conn = MagicMock()

        mock_db.connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_db.connection.return_value.__exit__ = MagicMock(return_value=False)

        ops = DatabaseOps(mock_db)
        stmt = MagicMock()

        ops.execute_update(stmt)

        mock_conn.execute.assert_called_once_with(stmt)


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
