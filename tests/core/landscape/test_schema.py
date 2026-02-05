# tests/core/landscape/test_schema.py
"""Tests for Landscape SQLAlchemy schema."""

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import inspect


class TestSchemaCreation:
    """Creating tables in a database."""

    def test_create_all_tables(self, tmp_path: Path) -> None:
        from sqlalchemy import create_engine

        from elspeth.core.landscape.schema import metadata

        db_path = tmp_path / "test.db"
        engine = create_engine(f"sqlite:///{db_path}")

        metadata.create_all(engine)

        # Verify tables exist
        inspector = inspect(engine)
        tables = inspector.get_table_names()

        assert "runs" in tables
        assert "nodes" in tables
        assert "rows" in tables
        assert "tokens" in tables
        assert "node_states" in tables




class TestNodesDeterminismColumn:
    """Tests for determinism column in nodes table."""

    def test_nodes_table_has_determinism_column(self) -> None:
        from elspeth.core.landscape.schema import nodes_table

        columns = {c.name for c in nodes_table.columns}
        assert "determinism" in columns

    def test_node_model_has_determinism_field(self) -> None:
        from datetime import UTC, datetime

        from elspeth.contracts import Determinism, Node, NodeType

        node = Node(
            node_id="node-001",
            run_id="run-001",
            plugin_name="test_plugin",
            node_type=NodeType.TRANSFORM,
            plugin_version="1.0.0",
            determinism=Determinism.DETERMINISTIC,  # New field
            config_hash="abc123",
            config_json="{}",
            registered_at=datetime.now(UTC),
        )
        assert node.determinism == Determinism.DETERMINISTIC

    def test_determinism_values(self) -> None:
        """Verify valid determinism values match Determinism enum."""
        from elspeth.contracts import Determinism

        valid_values = {d.value for d in Determinism}
        # All 6 values per architecture specification
        expected = {
            "deterministic",
            "seeded",
            "io_read",
            "io_write",
            "external_call",
            "non_deterministic",
        }
        assert valid_values == expected


class TestPhase5CheckpointSchema:
    """Tests for checkpoint table added in Phase 5."""

    def test_checkpoints_table_exists(self) -> None:
        from elspeth.core.landscape.schema import checkpoints_table

        assert checkpoints_table.name == "checkpoints"
        columns = {c.name for c in checkpoints_table.columns}
        assert "checkpoint_id" in columns
        assert "run_id" in columns
        assert "token_id" in columns
        assert "node_id" in columns
        assert "created_at" in columns

    def test_checkpoints_table_has_progress_columns(self) -> None:
        """Verify sequence_number and aggregation_state_json columns."""
        from elspeth.core.landscape.schema import checkpoints_table

        columns = {c.name for c in checkpoints_table.columns}
        assert "sequence_number" in columns
        assert "aggregation_state_json" in columns

    def test_checkpoints_table_has_topology_validation_columns(self) -> None:
        """P1: Verify checkpoint topology hash columns exist and are non-nullable.

        These columns were added in Bug #7 fix for checkpoint validation.
        A schema regression that removes them would break checkpoint
        compatibility validation and undermine recovery integrity.
        """
        from elspeth.core.landscape.schema import checkpoints_table

        columns = {c.name: c for c in checkpoints_table.columns}

        # upstream_topology_hash must exist and be non-nullable
        assert "upstream_topology_hash" in columns, "Missing upstream_topology_hash column"
        assert columns["upstream_topology_hash"].nullable is False, "upstream_topology_hash must be non-nullable for checkpoint validation"

        # checkpoint_node_config_hash must exist and be non-nullable
        assert "checkpoint_node_config_hash" in columns, "Missing checkpoint_node_config_hash column"
        assert columns["checkpoint_node_config_hash"].nullable is False, (
            "checkpoint_node_config_hash must be non-nullable for checkpoint validation"
        )

    def test_checkpoints_table_in_metadata(self) -> None:
        """Verify checkpoints table is registered in metadata."""
        from elspeth.core.landscape.schema import metadata

        assert "checkpoints" in metadata.tables

    def test_checkpoints_table_creates_in_database(self, tmp_path: Path) -> None:
        """Verify checkpoints table can be created in a real database."""
        from sqlalchemy import create_engine, inspect

        from elspeth.core.landscape.schema import metadata

        db_path = tmp_path / "test_checkpoints.db"
        engine = create_engine(f"sqlite:///{db_path}")
        metadata.create_all(engine)

        inspector = inspect(engine)
        tables = inspector.get_table_names()
        assert "checkpoints" in tables

    def test_checkpoint_model(self) -> None:
        from elspeth.contracts import Checkpoint

        checkpoint = Checkpoint(
            checkpoint_id="cp-001",
            run_id="run-001",
            token_id="tok-001",
            node_id="node-001",
            sequence_number=42,
            created_at=datetime.now(UTC),
            upstream_topology_hash="a" * 64,
            checkpoint_node_config_hash="b" * 64,
        )
        assert checkpoint.sequence_number == 42

    def test_checkpoint_model_with_aggregation_state(self) -> None:
        """Verify Checkpoint model supports aggregation state."""
        from elspeth.contracts import Checkpoint

        checkpoint = Checkpoint(
            checkpoint_id="cp-002",
            run_id="run-001",
            token_id="tok-001",
            node_id="node-001",
            sequence_number=100,
            created_at=datetime.now(UTC),
            upstream_topology_hash="a" * 64,
            checkpoint_node_config_hash="b" * 64,
            aggregation_state_json='{"buffer": [1, 2, 3]}',
        )
        assert checkpoint.aggregation_state_json == '{"buffer": [1, 2, 3]}'


class TestArtifactsIdempotencyKey:
    """Tests for idempotency_key column in artifacts table (WP-05 Task 2)."""

    def test_artifacts_table_has_idempotency_key(self) -> None:
        """artifacts table should have idempotency_key column."""
        from elspeth.core.landscape.schema import artifacts_table

        column_names = [c.name for c in artifacts_table.columns]
        assert "idempotency_key" in column_names

    def test_artifact_model_has_idempotency_key(self) -> None:
        """Artifact model should have idempotency_key field."""
        from dataclasses import fields

        from elspeth.contracts import Artifact

        field_names = [f.name for f in fields(Artifact)]
        assert "idempotency_key" in field_names


class TestBatchStatusType:
    """Tests for Batch.status type being BatchStatus enum (WP-05 Task 4)."""

    def test_batch_status_is_typed(self) -> None:
        """Batch.status should accept BatchStatus enum."""
        from elspeth.contracts import Batch, BatchStatus

        batch = Batch(
            batch_id="b1",
            run_id="r1",
            aggregation_node_id="agg1",
            attempt=1,
            status=BatchStatus.DRAFT,  # Should work without type error
            created_at=datetime.now(UTC),
        )

        assert batch.status == BatchStatus.DRAFT


class TestBatchesTriggerType:
    """Tests for trigger_type column in batches table (WP-05 Task 3)."""

    def test_batches_table_has_trigger_type(self) -> None:
        """batches table should have trigger_type column."""
        from elspeth.core.landscape.schema import batches_table

        column_names = [c.name for c in batches_table.columns]
        assert "trigger_type" in column_names

    def test_batch_model_has_trigger_type(self) -> None:
        """Batch model should have trigger_type field."""
        from dataclasses import fields

        from elspeth.contracts import Batch

        field_names = [f.name for f in fields(Batch)]
        assert "trigger_type" in field_names
