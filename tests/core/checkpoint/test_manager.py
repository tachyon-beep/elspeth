"""Tests for CheckpointManager."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from elspeth.core.checkpoint.manager import CheckpointManager, IncompatibleCheckpointError


class TestCheckpointManager:
    """Tests for checkpoint creation and loading."""

    @pytest.fixture
    def manager(self, tmp_path: Path) -> CheckpointManager:
        """Create CheckpointManager with test database."""
        from elspeth.core.landscape.database import LandscapeDB

        db = LandscapeDB(f"sqlite:///{tmp_path}/test.db")  # Tables auto-created
        return CheckpointManager(db)

    @pytest.fixture
    def setup_run(self, manager: CheckpointManager) -> str:
        """Create a run with some tokens for checkpoint tests."""
        from elspeth.core.landscape.schema import (
            nodes_table,
            rows_table,
            runs_table,
            tokens_table,
        )

        # Insert test run, node, row, token via schema tables
        db = manager._db
        with db.engine.connect() as conn:
            conn.execute(
                runs_table.insert().values(
                    run_id="run-001",
                    started_at=datetime.now(UTC),
                    config_hash="abc123",
                    settings_json="{}",
                    canonical_version="sha256-rfc8785-v1",
                    status="running",
                )
            )
            conn.execute(
                nodes_table.insert().values(
                    node_id="node-001",
                    run_id="run-001",
                    plugin_name="test_transform",
                    node_type="transform",
                    plugin_version="1.0.0",
                    determinism="deterministic",
                    config_hash="xyz",
                    config_json="{}",
                    registered_at=datetime.now(UTC),
                )
            )
            conn.execute(
                rows_table.insert().values(
                    row_id="row-001",
                    run_id="run-001",
                    source_node_id="node-001",
                    row_index=0,
                    source_data_hash="hash1",
                    created_at=datetime.now(UTC),
                )
            )
            conn.execute(
                tokens_table.insert().values(
                    token_id="tok-001",
                    row_id="row-001",
                    created_at=datetime.now(UTC),
                )
            )
            conn.commit()
        return "run-001"

    def test_create_checkpoint(self, manager: CheckpointManager, setup_run: str) -> None:
        """Can create a checkpoint."""
        checkpoint = manager.create_checkpoint(
            run_id="run-001",
            token_id="tok-001",
            node_id="node-001",
            sequence_number=1,
        )

        assert checkpoint.checkpoint_id is not None
        assert checkpoint.run_id == "run-001"
        assert checkpoint.sequence_number == 1

    def test_get_latest_checkpoint(self, manager: CheckpointManager, setup_run: str) -> None:
        """Can retrieve the latest checkpoint for a run."""
        # Create multiple checkpoints
        manager.create_checkpoint("run-001", "tok-001", "node-001", 1)
        manager.create_checkpoint("run-001", "tok-001", "node-001", 2)
        manager.create_checkpoint("run-001", "tok-001", "node-001", 3)

        latest = manager.get_latest_checkpoint("run-001")

        assert latest is not None
        assert latest.sequence_number == 3

    def test_get_latest_checkpoint_no_checkpoints(self, manager: CheckpointManager) -> None:
        """Returns None when no checkpoints exist."""
        latest = manager.get_latest_checkpoint("nonexistent-run")
        assert latest is None

    def test_checkpoint_with_aggregation_state(self, manager: CheckpointManager, setup_run: str) -> None:
        """Can store aggregation state in checkpoint."""
        agg_state = {"buffer": [1, 2, 3], "count": 3}

        manager.create_checkpoint(
            run_id="run-001",
            token_id="tok-001",
            node_id="node-001",
            sequence_number=1,
            aggregation_state=agg_state,
        )

        loaded = manager.get_latest_checkpoint("run-001")
        assert loaded is not None
        assert loaded.aggregation_state_json is not None
        assert json.loads(loaded.aggregation_state_json) == agg_state

    def test_checkpoint_with_empty_aggregation_state_preserved(self, manager: CheckpointManager, setup_run: str) -> None:
        """Empty aggregation state {} is distinct from None (no state).

        Regression test for truthiness bug: empty dict {} should serialize to "{}"
        not None. This ensures resume can distinguish "state is empty" from
        "no aggregation state was provided".

        See: docs/bugs/closed/P2-2026-01-19-checkpoint-empty-aggregation-state-dropped.md
        """
        # Create checkpoint with empty dict (NOT None)
        manager.create_checkpoint(
            run_id="run-001",
            token_id="tok-001",
            node_id="node-001",
            sequence_number=1,
            aggregation_state={},  # Empty dict, not None
        )

        loaded = manager.get_latest_checkpoint("run-001")
        assert loaded is not None
        # Critical: empty dict should serialize to "{}", NOT None
        assert loaded.aggregation_state_json == "{}", (
            f"Empty aggregation state should serialize to '{{}}', got {loaded.aggregation_state_json!r}. "
            "This is likely a truthiness bug where `if aggregation_state:` was used "
            "instead of `if aggregation_state is not None:`"
        )

    def test_checkpoint_with_none_aggregation_state_is_null(self, manager: CheckpointManager, setup_run: str) -> None:
        """None aggregation state stays as NULL/None in the database.

        Complements test_checkpoint_with_empty_aggregation_state_preserved to
        verify the full contract: {} → "{}" and None → NULL.
        """
        # Create checkpoint with explicit None
        manager.create_checkpoint(
            run_id="run-001",
            token_id="tok-001",
            node_id="node-001",
            sequence_number=1,
            aggregation_state=None,
        )

        loaded = manager.get_latest_checkpoint("run-001")
        assert loaded is not None
        # None should stay as None (NULL in DB)
        assert loaded.aggregation_state_json is None, f"None aggregation state should stay as None, got {loaded.aggregation_state_json!r}"

    def test_get_checkpoints_ordered(self, manager: CheckpointManager, setup_run: str) -> None:
        """Get all checkpoints ordered by sequence number."""
        manager.create_checkpoint("run-001", "tok-001", "node-001", 3)
        manager.create_checkpoint("run-001", "tok-001", "node-001", 1)
        manager.create_checkpoint("run-001", "tok-001", "node-001", 2)

        checkpoints = manager.get_checkpoints("run-001")

        assert len(checkpoints) == 3
        assert [c.sequence_number for c in checkpoints] == [1, 2, 3]

    def test_delete_checkpoints(self, manager: CheckpointManager, setup_run: str) -> None:
        """Delete all checkpoints for a run."""
        manager.create_checkpoint("run-001", "tok-001", "node-001", 1)
        manager.create_checkpoint("run-001", "tok-001", "node-001", 2)

        deleted = manager.delete_checkpoints("run-001")

        assert deleted == 2
        assert manager.get_latest_checkpoint("run-001") is None

    def test_delete_checkpoints_no_checkpoints(self, manager: CheckpointManager) -> None:
        """Delete returns 0 when no checkpoints exist."""
        deleted = manager.delete_checkpoints("nonexistent-run")
        assert deleted == 0

    def test_old_checkpoint_rejected(self, manager: CheckpointManager) -> None:
        """Checkpoints created before 2026-01-24 should be rejected.

        Old checkpoints use random UUID-based node IDs which are incompatible
        with the new deterministic hash-based node IDs. Loading such checkpoints
        would cause resume failures as node IDs won't match.
        """
        from elspeth.core.landscape.schema import (
            checkpoints_table,
            nodes_table,
            rows_table,
            runs_table,
            tokens_table,
        )

        # Set up required foreign key references
        run_id = "run-old"
        old_date = datetime(2026, 1, 23, 23, 59, 59, tzinfo=UTC)  # One second before cutoff

        with manager._db.engine.connect() as conn:
            # Create run
            conn.execute(
                runs_table.insert().values(
                    run_id=run_id,
                    started_at=old_date,
                    config_hash="abc123",
                    settings_json="{}",
                    canonical_version="sha256-rfc8785-v1",
                    status="failed",
                )
            )
            # Create node
            conn.execute(
                nodes_table.insert().values(
                    node_id="node-old",
                    run_id=run_id,
                    plugin_name="test_transform",
                    node_type="transform",
                    plugin_version="1.0.0",
                    determinism="deterministic",
                    config_hash="xyz",
                    config_json="{}",
                    registered_at=old_date,
                )
            )
            # Create row
            conn.execute(
                rows_table.insert().values(
                    row_id="row-old",
                    run_id=run_id,
                    source_node_id="node-old",
                    row_index=0,
                    source_data_hash="hash1",
                    created_at=old_date,
                )
            )
            # Create token
            conn.execute(
                tokens_table.insert().values(
                    token_id="tok-old",
                    row_id="row-old",
                    created_at=old_date,
                )
            )
            # Create checkpoint with old date
            checkpoint_id = "cp-old-checkpoint"
            conn.execute(
                checkpoints_table.insert().values(
                    checkpoint_id=checkpoint_id,
                    run_id=run_id,
                    token_id="tok-old",
                    node_id="node-old",
                    sequence_number=1,
                    aggregation_state_json=None,
                    created_at=old_date,
                )
            )
            conn.commit()

        # Attempting to load should raise IncompatibleCheckpointError
        with pytest.raises(IncompatibleCheckpointError) as exc_info:
            manager.get_latest_checkpoint(run_id)

        # Verify error message contains useful information
        error_msg = str(exc_info.value)
        assert checkpoint_id in error_msg
        assert "deterministic node IDs" in error_msg
        assert "Resume not supported" in error_msg

    def test_new_checkpoint_accepted(self, manager: CheckpointManager, setup_run: str) -> None:
        """Checkpoints created on or after 2026-01-24 should be accepted.

        New checkpoints use deterministic hash-based node IDs which are
        compatible with the current system.
        """
        # Create a checkpoint with new created_at date (on cutoff)
        new_date = datetime(2026, 1, 24, 0, 0, 0, tzinfo=UTC)  # Exactly at cutoff

        from elspeth.core.landscape.schema import checkpoints_table

        checkpoint_id = "cp-new-checkpoint"

        with manager._db.engine.connect() as conn:
            conn.execute(
                checkpoints_table.insert().values(
                    checkpoint_id=checkpoint_id,
                    run_id="run-001",
                    token_id="tok-001",
                    node_id="node-001",
                    sequence_number=1,
                    aggregation_state_json=None,
                    created_at=new_date,
                )
            )
            conn.commit()

        # Should load successfully without exception
        checkpoint = manager.get_latest_checkpoint("run-001")
        assert checkpoint is not None
        assert checkpoint.checkpoint_id == checkpoint_id
        # SQLite may return timezone-naive datetime, so compare the datetime values
        assert checkpoint.created_at.replace(tzinfo=None) == new_date.replace(tzinfo=None)

    def test_checkpoint_after_cutoff_accepted(self, manager: CheckpointManager, setup_run: str) -> None:
        """Checkpoints created after 2026-01-24 should be accepted.

        Verifies that the cutoff is inclusive - any date >= 2026-01-24 00:00:00 is valid.
        """
        # Create a checkpoint well after cutoff
        future_date = datetime(2026, 2, 1, 12, 30, 0, tzinfo=UTC)

        from elspeth.core.landscape.schema import checkpoints_table

        checkpoint_id = "cp-future-checkpoint"

        with manager._db.engine.connect() as conn:
            conn.execute(
                checkpoints_table.insert().values(
                    checkpoint_id=checkpoint_id,
                    run_id="run-001",
                    token_id="tok-001",
                    node_id="node-001",
                    sequence_number=1,
                    aggregation_state_json=None,
                    created_at=future_date,
                )
            )
            conn.commit()

        # Should load successfully
        checkpoint = manager.get_latest_checkpoint("run-001")
        assert checkpoint is not None
        assert checkpoint.checkpoint_id == checkpoint_id
