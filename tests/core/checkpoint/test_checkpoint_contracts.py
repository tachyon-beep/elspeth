"""Tests for contract integrity verification during checkpoint resume.

These tests verify that:
1. Schema contracts are verified during resume
2. Corrupted contracts cause CheckpointCorruptionError
3. Runs without contracts can still be resumed (backward compatibility)
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from elspeth.contracts import Determinism, NodeType, RunStatus, SchemaContract
from elspeth.contracts.schema_contract import FieldContract
from elspeth.core.checkpoint import CheckpointCorruptionError, CheckpointManager, RecoveryManager
from elspeth.core.dag import ExecutionGraph
from elspeth.core.landscape.database import LandscapeDB
from elspeth.core.landscape.recorder import LandscapeRecorder
from elspeth.core.landscape.schema import (
    nodes_table,
    rows_table,
    runs_table,
    tokens_table,
)


def _create_test_graph(checkpoint_node: str = "transform-node") -> ExecutionGraph:
    """Create a minimal test graph for checkpoint tests."""
    graph = ExecutionGraph()
    graph.add_node("source-node", node_type=NodeType.SOURCE, plugin_name="test-source", config={})
    graph.add_node("transform-node", node_type=NodeType.TRANSFORM, plugin_name="test-transform", config={})
    graph.add_node("sink-node", node_type=NodeType.SINK, plugin_name="test-sink", config={})
    graph.add_edge("source-node", "transform-node", label="continue")
    graph.add_edge("transform-node", "sink-node", label="continue")
    return graph


class TestContractVerificationOnResume:
    """Tests for contract integrity verification during resume."""

    @pytest.fixture
    def db(self, tmp_path: Path) -> LandscapeDB:
        """Create test database."""
        return LandscapeDB(f"sqlite:///{tmp_path}/test.db")

    @pytest.fixture
    def checkpoint_manager(self, db: LandscapeDB) -> CheckpointManager:
        """Create checkpoint manager."""
        return CheckpointManager(db)

    @pytest.fixture
    def recovery_manager(self, db: LandscapeDB, checkpoint_manager: CheckpointManager) -> RecoveryManager:
        """Create recovery manager."""
        return RecoveryManager(db, checkpoint_manager)

    @pytest.fixture
    def graph(self) -> ExecutionGraph:
        """Create test graph."""
        return _create_test_graph()

    def _create_failed_run_with_checkpoint(
        self,
        db: LandscapeDB,
        checkpoint_manager: CheckpointManager,
        graph: ExecutionGraph,
        *,
        with_contract: bool = True,
        corrupt_contract: bool = False,
    ) -> str:
        """Create a failed run with checkpoint and optionally a contract.

        Args:
            db: Database
            checkpoint_manager: Checkpoint manager
            graph: Execution graph
            with_contract: If True, store a valid contract
            corrupt_contract: If True, corrupt the contract hash in DB
        """
        run_id = f"test-run-{datetime.now(UTC).timestamp()}"
        now = datetime.now(UTC)

        with db.engine.connect() as conn:
            # Create run
            conn.execute(
                runs_table.insert().values(
                    run_id=run_id,
                    started_at=now,
                    config_hash="test-config-hash",
                    settings_json="{}",
                    canonical_version="sha256-rfc8785-v1",
                    status=RunStatus.FAILED,
                )
            )

            # Create nodes
            conn.execute(
                nodes_table.insert().values(
                    node_id="source-node",
                    run_id=run_id,
                    plugin_name="test-source",
                    node_type=NodeType.SOURCE,
                    plugin_version="1.0",
                    determinism=Determinism.DETERMINISTIC,
                    config_hash="src-hash",
                    config_json="{}",
                    registered_at=now,
                )
            )
            conn.execute(
                nodes_table.insert().values(
                    node_id="transform-node",
                    run_id=run_id,
                    plugin_name="test-transform",
                    node_type=NodeType.TRANSFORM,
                    plugin_version="1.0",
                    determinism=Determinism.DETERMINISTIC,
                    config_hash="xfm-hash",
                    config_json="{}",
                    registered_at=now,
                )
            )
            conn.execute(
                nodes_table.insert().values(
                    node_id="sink-node",
                    run_id=run_id,
                    plugin_name="test-sink",
                    node_type=NodeType.SINK,
                    plugin_version="1.0",
                    determinism=Determinism.DETERMINISTIC,
                    config_hash="sink-hash",
                    config_json="{}",
                    registered_at=now,
                )
            )

            # Create row and token
            conn.execute(
                rows_table.insert().values(
                    row_id="row-001",
                    run_id=run_id,
                    source_node_id="source-node",
                    row_index=0,
                    source_data_hash="data-hash",
                    created_at=now,
                )
            )
            conn.execute(
                tokens_table.insert().values(
                    token_id="tok-001",
                    row_id="row-001",
                    created_at=now,
                )
            )

            conn.commit()

        # Create checkpoint
        checkpoint_manager.create_checkpoint(
            run_id=run_id,
            token_id="tok-001",
            node_id="transform-node",
            sequence_number=1,
            graph=graph,
        )

        # Store contract if requested
        if with_contract:
            recorder = LandscapeRecorder(db)
            contract = SchemaContract(
                mode="FIXED",
                fields=(
                    FieldContract(
                        normalized_name="id",
                        original_name="id",
                        python_type=int,
                        required=True,
                        source="declared",
                    ),
                    FieldContract(
                        normalized_name="value",
                        original_name="value",
                        python_type=str,
                        required=True,
                        source="declared",
                    ),
                ),
                locked=True,
            )
            recorder.update_run_contract(run_id, contract)

            # Corrupt the hash if requested
            # The hash is stored INSIDE the JSON, so we need to modify the JSON itself
            if corrupt_contract:
                with db.engine.connect() as conn:
                    # Read the current JSON
                    result = conn.execute(runs_table.select().where(runs_table.c.run_id == run_id)).fetchone()
                    contract_json = result.schema_contract_json

                    # Modify the hash inside the JSON
                    contract_data = json.loads(contract_json)
                    contract_data["version_hash"] = "corrupted_hash_value"
                    corrupted_json = json.dumps(contract_data)

                    # Write back the corrupted JSON
                    conn.execute(runs_table.update().where(runs_table.c.run_id == run_id).values(schema_contract_json=corrupted_json))
                    conn.commit()

        return run_id

    def test_resume_with_valid_contract(
        self,
        db: LandscapeDB,
        checkpoint_manager: CheckpointManager,
        recovery_manager: RecoveryManager,
        graph: ExecutionGraph,
    ) -> None:
        """Resume succeeds when contract integrity verification passes."""
        run_id = self._create_failed_run_with_checkpoint(db, checkpoint_manager, graph, with_contract=True, corrupt_contract=False)

        check = recovery_manager.can_resume(run_id, graph)

        assert check.can_resume is True
        assert check.reason is None

    def test_resume_without_contract(
        self,
        db: LandscapeDB,
        checkpoint_manager: CheckpointManager,
        recovery_manager: RecoveryManager,
        graph: ExecutionGraph,
    ) -> None:
        """Resume succeeds for runs without contracts (backward compatibility)."""
        run_id = self._create_failed_run_with_checkpoint(db, checkpoint_manager, graph, with_contract=False)

        check = recovery_manager.can_resume(run_id, graph)

        assert check.can_resume is True
        assert check.reason is None

    def test_resume_with_corrupted_contract_raises(
        self,
        db: LandscapeDB,
        checkpoint_manager: CheckpointManager,
        recovery_manager: RecoveryManager,
        graph: ExecutionGraph,
    ) -> None:
        """Resume raises CheckpointCorruptionError when contract hash mismatches."""
        run_id = self._create_failed_run_with_checkpoint(db, checkpoint_manager, graph, with_contract=True, corrupt_contract=True)

        with pytest.raises(CheckpointCorruptionError) as exc_info:
            recovery_manager.can_resume(run_id, graph)

        # Verify error message contains relevant information
        error_msg = str(exc_info.value)
        assert "integrity" in error_msg.lower()
        assert run_id in error_msg

    def test_verify_contract_integrity_returns_contract(
        self,
        db: LandscapeDB,
        checkpoint_manager: CheckpointManager,
        recovery_manager: RecoveryManager,
        graph: ExecutionGraph,
    ) -> None:
        """verify_contract_integrity returns the contract when valid."""
        run_id = self._create_failed_run_with_checkpoint(db, checkpoint_manager, graph, with_contract=True)

        contract = recovery_manager.verify_contract_integrity(run_id)

        assert contract is not None
        assert contract.mode == "FIXED"
        assert len(contract.fields) == 2
        assert contract.locked is True

    def test_verify_contract_integrity_returns_none_without_contract(
        self,
        db: LandscapeDB,
        checkpoint_manager: CheckpointManager,
        recovery_manager: RecoveryManager,
        graph: ExecutionGraph,
    ) -> None:
        """verify_contract_integrity returns None for runs without contracts."""
        run_id = self._create_failed_run_with_checkpoint(db, checkpoint_manager, graph, with_contract=False)

        contract = recovery_manager.verify_contract_integrity(run_id)

        assert contract is None

    def test_verify_contract_integrity_raises_on_corruption(
        self,
        db: LandscapeDB,
        checkpoint_manager: CheckpointManager,
        recovery_manager: RecoveryManager,
        graph: ExecutionGraph,
    ) -> None:
        """verify_contract_integrity raises CheckpointCorruptionError on hash mismatch."""
        run_id = self._create_failed_run_with_checkpoint(db, checkpoint_manager, graph, with_contract=True, corrupt_contract=True)

        with pytest.raises(CheckpointCorruptionError) as exc_info:
            recovery_manager.verify_contract_integrity(run_id)

        error_msg = str(exc_info.value)
        assert "integrity" in error_msg.lower()
        assert "corrupted" in error_msg.lower() or "tampered" in error_msg.lower()


class TestCheckpointCorruptionErrorExport:
    """Tests that CheckpointCorruptionError is properly exported."""

    def test_error_importable_from_checkpoint_module(self) -> None:
        """CheckpointCorruptionError can be imported from checkpoint module."""
        from elspeth.core.checkpoint import CheckpointCorruptionError

        assert issubclass(CheckpointCorruptionError, Exception)

    def test_error_has_meaningful_message(self) -> None:
        """CheckpointCorruptionError can be created with a message."""
        error = CheckpointCorruptionError("Test corruption message")
        assert "Test corruption message" in str(error)


class TestContractVerificationWithResumePoint:
    """Tests that get_resume_point also validates contract integrity."""

    @pytest.fixture
    def db(self, tmp_path: Path) -> LandscapeDB:
        """Create test database."""
        return LandscapeDB(f"sqlite:///{tmp_path}/test.db")

    @pytest.fixture
    def checkpoint_manager(self, db: LandscapeDB) -> CheckpointManager:
        """Create checkpoint manager."""
        return CheckpointManager(db)

    @pytest.fixture
    def recovery_manager(self, db: LandscapeDB, checkpoint_manager: CheckpointManager) -> RecoveryManager:
        """Create recovery manager."""
        return RecoveryManager(db, checkpoint_manager)

    @pytest.fixture
    def graph(self) -> ExecutionGraph:
        """Create test graph."""
        return _create_test_graph()

    def test_get_resume_point_validates_contract(
        self,
        db: LandscapeDB,
        checkpoint_manager: CheckpointManager,
        recovery_manager: RecoveryManager,
        graph: ExecutionGraph,
    ) -> None:
        """get_resume_point raises on corrupted contract (via can_resume)."""
        # Create helper instance to set up the run
        helper = TestContractVerificationOnResume()
        run_id = helper._create_failed_run_with_checkpoint(db, checkpoint_manager, graph, with_contract=True, corrupt_contract=True)

        # get_resume_point calls can_resume internally, which should raise
        with pytest.raises(CheckpointCorruptionError):
            recovery_manager.get_resume_point(run_id, graph)
