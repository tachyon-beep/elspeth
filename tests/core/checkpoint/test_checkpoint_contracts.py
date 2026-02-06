"""Tests for contract integrity verification during checkpoint resume.

These tests verify that:
1. Schema contracts are verified during resume
2. Corrupted contracts cause CheckpointCorruptionError
3. Missing contracts cause CheckpointCorruptionError (no backward compatibility)
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
                    assert result is not None
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

    def test_resume_without_contract_raises(
        self,
        db: LandscapeDB,
        checkpoint_manager: CheckpointManager,
        recovery_manager: RecoveryManager,
        graph: ExecutionGraph,
    ) -> None:
        """Resume raises CheckpointCorruptionError for runs without contracts.

        Per CLAUDE.md Tier-1 trust model: missing contract = audit trail corruption.
        NO backward compatibility for pre-contract runs.
        """
        run_id = self._create_failed_run_with_checkpoint(db, checkpoint_manager, graph, with_contract=False)

        with pytest.raises(CheckpointCorruptionError) as exc_info:
            recovery_manager.can_resume(run_id, graph)

        # Verify error message contains relevant information
        error_msg = str(exc_info.value)
        assert "missing" in error_msg.lower()
        assert run_id in error_msg

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

    def test_verify_contract_integrity_raises_without_contract(
        self,
        db: LandscapeDB,
        checkpoint_manager: CheckpointManager,
        recovery_manager: RecoveryManager,
        graph: ExecutionGraph,
    ) -> None:
        """verify_contract_integrity raises CheckpointCorruptionError for runs without contracts.

        Per CLAUDE.md Tier-1 trust model: missing contract = audit trail corruption.
        NO backward compatibility for pre-contract runs.
        """
        run_id = self._create_failed_run_with_checkpoint(db, checkpoint_manager, graph, with_contract=False)

        with pytest.raises(CheckpointCorruptionError) as exc_info:
            recovery_manager.verify_contract_integrity(run_id)

        # Verify error message contains relevant information
        error_msg = str(exc_info.value)
        assert "missing" in error_msg.lower()
        assert run_id in error_msg

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


class TestResumePointAggregationStateValidation:
    """Tests for ResumePoint aggregation_state type validation.

    Per CLAUDE.md Tier-1 trust model: ResumePoint is audit data.
    aggregation_state must be dict or None - crash immediately on
    any other type to prevent corrupted checkpoint data from propagating.

    Bug ref: P2-2026-02-05-resumepoint-allows-non-dict-aggregation-state
    """

    def test_resume_point_accepts_dict_aggregation_state(self) -> None:
        """ResumePoint accepts dict aggregation_state."""
        from elspeth.contracts import ResumePoint
        from elspeth.contracts.audit import Checkpoint

        checkpoint = Checkpoint(
            checkpoint_id="cp-1",
            run_id="run-1",
            token_id="tok-1",
            node_id="node-1",
            sequence_number=1,
            created_at=datetime.now(UTC),
            upstream_topology_hash="hash1",
            checkpoint_node_config_hash="hash2",
        )

        rp = ResumePoint(
            checkpoint=checkpoint,
            token_id="tok-1",
            node_id="node-1",
            sequence_number=1,
            aggregation_state={"count": 42, "sum": 100.0},
        )

        assert rp.aggregation_state == {"count": 42, "sum": 100.0}

    def test_resume_point_accepts_none_aggregation_state(self) -> None:
        """ResumePoint accepts None aggregation_state."""
        from elspeth.contracts import ResumePoint
        from elspeth.contracts.audit import Checkpoint

        checkpoint = Checkpoint(
            checkpoint_id="cp-1",
            run_id="run-1",
            token_id="tok-1",
            node_id="node-1",
            sequence_number=1,
            created_at=datetime.now(UTC),
            upstream_topology_hash="hash1",
            checkpoint_node_config_hash="hash2",
        )

        rp = ResumePoint(
            checkpoint=checkpoint,
            token_id="tok-1",
            node_id="node-1",
            sequence_number=1,
            aggregation_state=None,
        )

        assert rp.aggregation_state is None

    def test_resume_point_rejects_list_aggregation_state(self) -> None:
        """ResumePoint raises ValueError for list aggregation_state.

        Per CLAUDE.md Tier-1 trust model: crash immediately on audit data anomaly.
        """
        from elspeth.contracts import ResumePoint
        from elspeth.contracts.audit import Checkpoint

        checkpoint = Checkpoint(
            checkpoint_id="cp-1",
            run_id="run-1",
            token_id="tok-1",
            node_id="node-1",
            sequence_number=1,
            created_at=datetime.now(UTC),
            upstream_topology_hash="hash1",
            checkpoint_node_config_hash="hash2",
        )

        with pytest.raises(ValueError) as exc_info:
            ResumePoint(
                checkpoint=checkpoint,
                token_id="tok-1",
                node_id="node-1",
                sequence_number=1,
                aggregation_state=[],  # type: ignore[arg-type]
            )

        error_msg = str(exc_info.value)
        assert "aggregation_state must be dict or None" in error_msg
        assert "list" in error_msg

    def test_resume_point_rejects_string_aggregation_state(self) -> None:
        """ResumePoint raises ValueError for string aggregation_state."""
        from elspeth.contracts import ResumePoint
        from elspeth.contracts.audit import Checkpoint

        checkpoint = Checkpoint(
            checkpoint_id="cp-1",
            run_id="run-1",
            token_id="tok-1",
            node_id="node-1",
            sequence_number=1,
            created_at=datetime.now(UTC),
            upstream_topology_hash="hash1",
            checkpoint_node_config_hash="hash2",
        )

        with pytest.raises(ValueError) as exc_info:
            ResumePoint(
                checkpoint=checkpoint,
                token_id="tok-1",
                node_id="node-1",
                sequence_number=1,
                aggregation_state="not a dict",  # type: ignore[arg-type]
            )

        error_msg = str(exc_info.value)
        assert "aggregation_state must be dict or None" in error_msg
        assert "str" in error_msg

    def test_resume_point_rejects_int_aggregation_state(self) -> None:
        """ResumePoint raises ValueError for int aggregation_state."""
        from elspeth.contracts import ResumePoint
        from elspeth.contracts.audit import Checkpoint

        checkpoint = Checkpoint(
            checkpoint_id="cp-1",
            run_id="run-1",
            token_id="tok-1",
            node_id="node-1",
            sequence_number=1,
            created_at=datetime.now(UTC),
            upstream_topology_hash="hash1",
            checkpoint_node_config_hash="hash2",
        )

        with pytest.raises(ValueError) as exc_info:
            ResumePoint(
                checkpoint=checkpoint,
                token_id="tok-1",
                node_id="node-1",
                sequence_number=1,
                aggregation_state=42,  # type: ignore[arg-type]
            )

        error_msg = str(exc_info.value)
        assert "aggregation_state must be dict or None" in error_msg
        assert "int" in error_msg


class TestRecoveryRejectsNonDictAggregationState:
    """Tests that get_resume_point raises when checkpoint has non-dict aggregation_state.

    Per CLAUDE.md Tier-1 trust model: checkpoints are audit data.
    Corrupted aggregation_state_json (valid JSON but not a dict) must crash
    immediately, not propagate into resume logic.

    Bug ref: P2-2026-02-05-resumepoint-allows-non-dict-aggregation-state
    """

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

    def _create_run_with_corrupted_checkpoint(
        self,
        db: LandscapeDB,
        graph: ExecutionGraph,
        corrupted_agg_json: str,
    ) -> str:
        """Create a failed run with checkpoint containing corrupted aggregation_state_json.

        This bypasses CheckpointManager to directly insert a checkpoint with
        malformed data, simulating database corruption or tampering.
        """
        from elspeth.contracts import Checkpoint
        from elspeth.contracts.contract_records import ContractAuditRecord
        from elspeth.contracts.schema_contract import FieldContract, SchemaContract
        from elspeth.core.canonical import compute_full_topology_hash, stable_hash
        from elspeth.core.landscape.schema import checkpoints_table

        run_id = f"test-corrupted-{datetime.now(UTC).timestamp()}"
        now = datetime.now(UTC)

        # Create schema contract for the run
        field_contracts = (
            FieldContract(
                normalized_name="test_field",
                original_name="test_field",
                python_type=str,
                required=True,
                source="declared",
            ),
        )
        contract = SchemaContract(fields=field_contracts, mode="FIXED", locked=True)
        audit_record = ContractAuditRecord.from_contract(contract)
        contract_json = audit_record.to_json()
        contract_hash = contract.version_hash()

        with db.engine.connect() as conn:
            # Create run with valid contract
            conn.execute(
                runs_table.insert().values(
                    run_id=run_id,
                    started_at=now,
                    config_hash="test-config-hash",
                    settings_json="{}",
                    canonical_version="sha256-rfc8785-v1",
                    status=RunStatus.FAILED,
                    schema_contract_json=contract_json,
                    schema_contract_hash=contract_hash,
                )
            )

            # Create nodes
            for node_id, node_type in [
                ("source-node", NodeType.SOURCE),
                ("transform-node", NodeType.TRANSFORM),
                ("sink-node", NodeType.SINK),
            ]:
                conn.execute(
                    nodes_table.insert().values(
                        node_id=node_id,
                        run_id=run_id,
                        plugin_name=f"test-{node_type.value}",
                        node_type=node_type,
                        plugin_version="1.0",
                        determinism=Determinism.DETERMINISTIC,
                        config_hash=f"{node_id}-hash",
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

            # DIRECTLY insert checkpoint with corrupted aggregation_state_json
            # This bypasses CheckpointManager validation to simulate DB corruption
            node_info = graph.get_node_info("transform-node")
            conn.execute(
                checkpoints_table.insert().values(
                    checkpoint_id="cp-corrupted",
                    run_id=run_id,
                    token_id="tok-001",
                    node_id="transform-node",
                    sequence_number=1,
                    aggregation_state_json=corrupted_agg_json,  # Corrupted!
                    created_at=now,
                    upstream_topology_hash=compute_full_topology_hash(graph),
                    checkpoint_node_config_hash=stable_hash(node_info.config),
                    format_version=Checkpoint.CURRENT_FORMAT_VERSION,
                )
            )

            conn.commit()

        return run_id

    def test_get_resume_point_raises_on_list_aggregation_state_json(
        self,
        db: LandscapeDB,
        recovery_manager: RecoveryManager,
        graph: ExecutionGraph,
    ) -> None:
        """get_resume_point raises ValueError when aggregation_state_json is a JSON array.

        Simulates database corruption where valid JSON (a list) is stored instead of
        the expected dict.
        """
        # JSON array is valid JSON but not a dict
        corrupted_json = '["item1", "item2", "item3"]'
        run_id = self._create_run_with_corrupted_checkpoint(db, graph, corrupted_json)

        with pytest.raises(ValueError) as exc_info:
            recovery_manager.get_resume_point(run_id, graph)

        error_msg = str(exc_info.value)
        assert "aggregation_state must be dict or None" in error_msg
        assert "list" in error_msg

    def test_get_resume_point_raises_on_string_aggregation_state_json(
        self,
        db: LandscapeDB,
        recovery_manager: RecoveryManager,
        graph: ExecutionGraph,
    ) -> None:
        """get_resume_point raises ValueError when aggregation_state_json is a JSON string."""
        # JSON string is valid JSON but not a dict
        corrupted_json = '"just a string"'
        run_id = self._create_run_with_corrupted_checkpoint(db, graph, corrupted_json)

        with pytest.raises(ValueError) as exc_info:
            recovery_manager.get_resume_point(run_id, graph)

        error_msg = str(exc_info.value)
        assert "aggregation_state must be dict or None" in error_msg
        assert "str" in error_msg

    def test_get_resume_point_raises_on_int_aggregation_state_json(
        self,
        db: LandscapeDB,
        recovery_manager: RecoveryManager,
        graph: ExecutionGraph,
    ) -> None:
        """get_resume_point raises ValueError when aggregation_state_json is a JSON number."""
        # JSON number is valid JSON but not a dict
        corrupted_json = "42"
        run_id = self._create_run_with_corrupted_checkpoint(db, graph, corrupted_json)

        with pytest.raises(ValueError) as exc_info:
            recovery_manager.get_resume_point(run_id, graph)

        error_msg = str(exc_info.value)
        assert "aggregation_state must be dict or None" in error_msg
        assert "int" in error_msg

    def test_get_resume_point_succeeds_with_valid_dict_aggregation_state_json(
        self,
        db: LandscapeDB,
        recovery_manager: RecoveryManager,
        graph: ExecutionGraph,
    ) -> None:
        """get_resume_point succeeds when aggregation_state_json is a valid JSON object."""
        valid_json = '{"count": 42, "sum": 100.5}'
        run_id = self._create_run_with_corrupted_checkpoint(db, graph, valid_json)

        resume_point = recovery_manager.get_resume_point(run_id, graph)

        assert resume_point is not None
        assert resume_point.aggregation_state == {"count": 42, "sum": 100.5}
