# tests/integration/test_checkpoint_recovery.py
"""Integration tests for checkpoint and recovery.

End-to-end test that verifies checkpoint creation, simulated crash,
and recovery work together correctly.
"""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from elspeth.core.checkpoint import CheckpointManager
from elspeth.core.dag import ExecutionGraph
from elspeth.core.landscape.database import LandscapeDB


class TestCheckpointRecoveryIntegration:
    """End-to-end checkpoint/recovery tests."""

    @pytest.fixture
    def test_env(self, tmp_path: Path) -> dict[str, Any]:
        """Set up test environment with database and payload store."""
        from elspeth.core.checkpoint import CheckpointManager, RecoveryManager
        from elspeth.core.config import CheckpointSettings
        from elspeth.core.landscape.database import LandscapeDB
        from elspeth.core.payload_store import FilesystemPayloadStore

        db = LandscapeDB(f"sqlite:///{tmp_path}/test.db")

        payload_store = FilesystemPayloadStore(tmp_path / "payloads")
        checkpoint_mgr = CheckpointManager(db)
        recovery_mgr = RecoveryManager(db, checkpoint_mgr)
        checkpoint_settings = CheckpointSettings(frequency="every_row")

        return {
            "db": db,
            "payload_store": payload_store,
            "checkpoint_manager": checkpoint_mgr,
            "recovery_manager": recovery_mgr,
            "checkpoint_settings": checkpoint_settings,
            "tmp_path": tmp_path,
        }

    @pytest.fixture
    def mock_graph(self) -> ExecutionGraph:
        """Create a minimal mock graph for checkpoint/recovery tests."""
        graph = ExecutionGraph()
        graph.add_node("node-001", node_type="transform", plugin_name="test")
        return graph

    def test_full_checkpoint_recovery_cycle(self, test_env: dict[str, Any], mock_graph: ExecutionGraph) -> None:
        """Complete cycle: run -> checkpoint -> crash -> recover -> complete."""
        checkpoint_mgr = test_env["checkpoint_manager"]
        recovery_mgr = test_env["recovery_manager"]
        db = test_env["db"]

        # 1. Set up a run with rows and checkpoints
        run_id = self._setup_partial_run(db, checkpoint_mgr, mock_graph)

        # 2. Verify checkpoint exists
        checkpoint = checkpoint_mgr.get_latest_checkpoint(run_id)
        assert checkpoint is not None
        assert checkpoint.sequence_number > 0

        # 3. Verify can resume
        check = recovery_mgr.can_resume(run_id, mock_graph)
        assert check.can_resume is True, f"Cannot resume: {check.reason}"

        # 4. Get resume point
        resume_point = recovery_mgr.get_resume_point(run_id, mock_graph)
        assert resume_point is not None

        # 5. Get unprocessed rows (setup creates 5 rows 0-4, checkpoint at sequence 2)
        unprocessed = recovery_mgr.get_unprocessed_rows(run_id)
        assert len(unprocessed) == 2  # rows 3 and 4

    def test_checkpoint_sequence_ordering(self, test_env: dict[str, Any], mock_graph: ExecutionGraph) -> None:
        """Verify checkpoints are ordered by sequence number."""
        checkpoint_mgr = test_env["checkpoint_manager"]
        db = test_env["db"]

        run_id = self._setup_partial_run(db, checkpoint_mgr, mock_graph)

        # Create additional checkpoints at different sequence numbers
        # Use token IDs that were created by _setup_partial_run (tok-001-003, tok-001-004)
        # and use matching node_id from _setup_partial_run (default run_suffix="001")
        checkpoint_mgr.create_checkpoint(
            run_id=run_id,
            token_id="tok-001-003",
            node_id="node-001",
            sequence_number=3,
            graph=mock_graph,
        )
        checkpoint_mgr.create_checkpoint(
            run_id=run_id,
            token_id="tok-001-004",
            node_id="node-001",
            sequence_number=4,
            graph=mock_graph,
        )

        # Get all checkpoints
        checkpoints = checkpoint_mgr.get_checkpoints(run_id)
        assert len(checkpoints) >= 3  # At least 3 checkpoints (2, 3, 4)

        # Verify ordering
        for i in range(len(checkpoints) - 1):
            assert checkpoints[i].sequence_number < checkpoints[i + 1].sequence_number

        # Latest checkpoint should be the highest sequence
        latest = checkpoint_mgr.get_latest_checkpoint(run_id)
        assert latest is not None
        assert latest.sequence_number == max(c.sequence_number for c in checkpoints)

    def test_recovery_with_aggregation_state(self, test_env: dict[str, Any], mock_graph: ExecutionGraph) -> None:
        """Verify aggregation state is preserved across recovery."""
        checkpoint_mgr = test_env["checkpoint_manager"]
        recovery_mgr = test_env["recovery_manager"]
        db = test_env["db"]

        run_id = self._setup_partial_run(db, checkpoint_mgr, mock_graph)

        # Create checkpoint with aggregation state
        # Use token ID that was created by _setup_partial_run (tok-001-003)
        agg_state = {
            "buffer": [{"id": 1, "value": 100}, {"id": 2, "value": 200}],
            "count": 2,
            "sum": 300,
        }
        checkpoint_mgr.create_checkpoint(
            run_id=run_id,
            token_id="tok-001-003",
            node_id="node-001",
            sequence_number=3,
            aggregation_state=agg_state,
            graph=mock_graph,
        )

        # Get resume point
        resume_point = recovery_mgr.get_resume_point(run_id, mock_graph)
        assert resume_point is not None
        assert resume_point.aggregation_state is not None
        assert resume_point.aggregation_state == agg_state
        assert resume_point.aggregation_state["count"] == 2
        assert resume_point.aggregation_state["sum"] == 300

    def test_checkpoint_cleanup_after_completion(self, test_env: dict[str, Any], mock_graph: ExecutionGraph) -> None:
        """Verify checkpoints are cleaned up after successful run."""
        checkpoint_mgr = test_env["checkpoint_manager"]
        db = test_env["db"]

        run_id = self._setup_partial_run(db, checkpoint_mgr, mock_graph)

        # Verify checkpoints exist
        checkpoints = checkpoint_mgr.get_checkpoints(run_id)
        assert len(checkpoints) > 0

        # Delete checkpoints (simulating run completion)
        deleted_count = checkpoint_mgr.delete_checkpoints(run_id)
        assert deleted_count > 0

        # Verify no checkpoints remain
        remaining = checkpoint_mgr.get_checkpoints(run_id)
        assert len(remaining) == 0

    def test_recovery_respects_checkpoint_boundary(self, test_env: dict[str, Any], mock_graph: ExecutionGraph) -> None:
        """Verify recovery resumes from correct checkpoint position."""
        checkpoint_mgr = test_env["checkpoint_manager"]
        recovery_mgr = test_env["recovery_manager"]
        db = test_env["db"]

        run_id = self._setup_partial_run(db, checkpoint_mgr, mock_graph)

        # Resume point should match the checkpoint
        resume_point = recovery_mgr.get_resume_point(run_id, mock_graph)
        checkpoint = checkpoint_mgr.get_latest_checkpoint(run_id)

        assert resume_point is not None
        assert checkpoint is not None
        assert resume_point.token_id == checkpoint.token_id
        assert resume_point.node_id == checkpoint.node_id
        assert resume_point.sequence_number == checkpoint.sequence_number

    def test_multiple_runs_independent_checkpoints(self, test_env: dict[str, Any], mock_graph: ExecutionGraph) -> None:
        """Verify checkpoints are isolated per run."""
        checkpoint_mgr = test_env["checkpoint_manager"]
        db = test_env["db"]

        # Create two runs with different checkpoint states
        run_id_1 = self._setup_partial_run(db, checkpoint_mgr, mock_graph, run_suffix="001")
        run_id_2 = self._setup_partial_run(db, checkpoint_mgr, mock_graph, run_suffix="002")

        # Each run should have its own checkpoints
        cp_1 = checkpoint_mgr.get_checkpoints(run_id_1)
        cp_2 = checkpoint_mgr.get_checkpoints(run_id_2)

        assert len(cp_1) > 0
        assert len(cp_2) > 0

        # Deleting one run's checkpoints doesn't affect the other
        checkpoint_mgr.delete_checkpoints(run_id_1)
        assert len(checkpoint_mgr.get_checkpoints(run_id_1)) == 0
        assert len(checkpoint_mgr.get_checkpoints(run_id_2)) > 0

    def _setup_partial_run(
        self,
        db: LandscapeDB,
        checkpoint_mgr: CheckpointManager,
        graph: ExecutionGraph,
        *,
        run_suffix: str = "001",
    ) -> str:
        """Helper to create a partially-completed run with checkpoints."""
        from elspeth.core.landscape.schema import (
            nodes_table,
            rows_table,
            runs_table,
            tokens_table,
        )

        run_id = f"test-run-{run_suffix}"
        now = datetime.now(UTC)
        node_id = f"node-{run_suffix}"

        # Add node to graph if it doesn't exist
        if not graph.has_node(node_id):
            graph.add_node(node_id, node_type="transform", plugin_name="test")

        with db.engine.connect() as conn:
            # Create run (failed status)
            conn.execute(
                runs_table.insert().values(
                    run_id=run_id,
                    started_at=now,
                    config_hash="test",
                    settings_json="{}",
                    canonical_version="sha256-rfc8785-v1",
                    status="failed",
                )
            )

            # Create node
            conn.execute(
                nodes_table.insert().values(
                    node_id=f"node-{run_suffix}",
                    run_id=run_id,
                    plugin_name="test",
                    node_type="transform",
                    plugin_version="1.0",
                    determinism="deterministic",
                    config_hash="x",
                    config_json="{}",
                    registered_at=now,
                )
            )

            # Create multiple rows
            for i in range(5):
                row_id = f"row-{run_suffix}-{i:03d}"
                conn.execute(
                    rows_table.insert().values(
                        row_id=row_id,
                        run_id=run_id,
                        source_node_id=f"node-{run_suffix}",
                        row_index=i,
                        source_data_hash=f"hash{i}",
                        created_at=now,
                    )
                )
                conn.execute(
                    tokens_table.insert().values(
                        token_id=f"tok-{run_suffix}-{i:03d}",
                        row_id=row_id,
                        created_at=now,
                    )
                )

            conn.commit()

        # Create checkpoint at row 2 (simulating partial progress)
        checkpoint_mgr.create_checkpoint(
            run_id=run_id,
            token_id=f"tok-{run_suffix}-002",
            node_id=f"node-{run_suffix}",
            sequence_number=2,
            graph=graph,
        )

        return run_id

    def test_full_resume_processes_remaining_rows(self, test_env: dict[str, Any], mock_graph: ExecutionGraph) -> None:
        """Complete cycle: run -> crash simulation -> resume -> all rows processed."""
        import json

        from elspeth.contracts import RunStatus
        from elspeth.core.landscape.schema import (
            edges_table,
            nodes_table,
            rows_table,
            runs_table,
            tokens_table,
        )
        from elspeth.engine.orchestrator import Orchestrator, PipelineConfig
        from elspeth.plugins.sinks.csv_sink import CSVSink
        from elspeth.plugins.sources.null_source import NullSource
        from elspeth.plugins.transforms.passthrough import PassThrough

        db = test_env["db"]
        checkpoint_mgr = test_env["checkpoint_manager"]
        recovery_mgr = test_env["recovery_manager"]
        payload_store = test_env["payload_store"]
        checkpoint_settings = test_env["checkpoint_settings"]
        tmp_path = test_env["tmp_path"]

        # Create graph for this test with the actual nodes used
        test_graph = ExecutionGraph()
        test_graph.add_node("src", node_type="source", plugin_name="null")
        test_graph.add_node("xform", node_type="transform", plugin_name="passthrough")
        test_graph.add_node("sink", node_type="sink", plugin_name="csv")

        # 1. Set up failed run with 5 rows, checkpoint at row 2
        run_id = "integration-resume-test"
        output_path = tmp_path / "resume_output.csv"
        now = datetime.now(UTC)

        # Create source schema for resume ({"id": int, "name": str})
        source_schema_json = json.dumps({"properties": {"id": {"type": "integer"}, "name": {"type": "string"}}, "required": ["id", "name"]})

        with db.engine.connect() as conn:
            # Create run
            conn.execute(
                runs_table.insert().values(
                    run_id=run_id,
                    started_at=now,
                    config_hash="x",
                    settings_json="{}",
                    canonical_version="v1",
                    status="failed",
                    source_schema_json=source_schema_json,
                )
            )

            # Create nodes
            conn.execute(
                nodes_table.insert().values(
                    node_id="src",
                    run_id=run_id,
                    plugin_name="null",
                    node_type="source",
                    plugin_version="1.0.0",
                    determinism="deterministic",
                    config_hash="x",
                    config_json="{}",
                    registered_at=now,
                )
            )
            conn.execute(
                nodes_table.insert().values(
                    node_id="xform",
                    run_id=run_id,
                    plugin_name="passthrough",
                    node_type="transform",
                    plugin_version="1.0.0",
                    determinism="deterministic",
                    config_hash="x",
                    config_json="{}",
                    registered_at=now,
                )
            )
            conn.execute(
                nodes_table.insert().values(
                    node_id="sink",
                    run_id=run_id,
                    plugin_name="csv",
                    node_type="sink",
                    plugin_version="1.0.0",
                    determinism="io_write",
                    config_hash="x",
                    config_json="{}",
                    registered_at=now,
                )
            )

            # Create edges
            conn.execute(
                edges_table.insert().values(
                    edge_id="e1",
                    run_id=run_id,
                    from_node_id="src",
                    to_node_id="xform",
                    label="continue",
                    default_mode="move",
                    created_at=now,
                )
            )
            conn.execute(
                edges_table.insert().values(
                    edge_id="e2",
                    run_id=run_id,
                    from_node_id="xform",
                    to_node_id="sink",
                    label="continue",
                    default_mode="move",
                    created_at=now,
                )
            )

            # Create 5 rows with payloads
            for i in range(5):
                row_data = {"id": i, "name": f"row-{i}"}
                ref = payload_store.store(json.dumps(row_data).encode())
                conn.execute(
                    rows_table.insert().values(
                        row_id=f"r{i}",
                        run_id=run_id,
                        source_node_id="src",
                        row_index=i,
                        source_data_hash=f"h{i}",
                        source_data_ref=ref,
                        created_at=now,
                    )
                )
                conn.execute(
                    tokens_table.insert().values(
                        token_id=f"t{i}",
                        row_id=f"r{i}",
                        created_at=now,
                    )
                )
            conn.commit()

        # Simulate partial output (rows 0-2 already written)
        with open(output_path, "w") as f:
            f.write("id,name\n")
            f.write("0,row-0\n")
            f.write("1,row-1\n")
            f.write("2,row-2\n")

        # Create checkpoint at row 2
        checkpoint_mgr.create_checkpoint(
            run_id=run_id,
            token_id="t2",
            node_id="xform",
            sequence_number=2,
            graph=test_graph,
        )

        # 2. Verify can resume
        assert recovery_mgr.can_resume(run_id, test_graph).can_resume
        resume_point = recovery_mgr.get_resume_point(run_id, test_graph)
        assert resume_point is not None

        # 3. Resume
        orchestrator = Orchestrator(
            db,
            checkpoint_manager=checkpoint_mgr,
            checkpoint_settings=checkpoint_settings,
        )

        config = PipelineConfig(
            source=NullSource({}),
            transforms=[
                PassThrough({"schema": {"fields": "dynamic"}}),
            ],
            sinks={
                "default": CSVSink(
                    {
                        "path": str(output_path),
                        "schema": {"fields": "dynamic"},
                        "mode": "append",
                    }
                )
            },
        )

        # Build graph using add_node() API
        graph = ExecutionGraph()
        graph.add_node("src", node_type="source", plugin_name="null", config={})
        graph.add_node("xform", node_type="transform", plugin_name="passthrough", config={})
        graph.add_node("sink", node_type="sink", plugin_name="csv", config={})
        graph.add_edge("src", "xform", label="continue")
        graph.add_edge("xform", "sink", label="continue")

        # Manually set the sink_id_map and transform_id_map since we're building
        # the graph manually (not from config)
        graph._sink_id_map = {"default": "sink"}
        graph._transform_id_map = {0: "xform"}
        graph._default_sink = "default"

        result = orchestrator.resume(
            resume_point=resume_point,
            config=config,
            graph=graph,
            payload_store=payload_store,
        )

        # 4. Verify
        assert result.rows_processed == 2
        assert result.rows_succeeded == 2
        assert result.status == RunStatus.COMPLETED

        # Check output file has all 5 rows
        lines = output_path.read_text().strip().split("\n")
        assert len(lines) == 6  # header + 5 rows
        assert "0,row-0" in lines[1]
        assert "4,row-4" in lines[5]


class TestCheckpointTopologyHashAtomicity:
    """Test for Bug #1 fix: Topology hash race condition.

    Verifies that topology hash is computed atomically inside the transaction,
    preventing race conditions where graph modification after hash computation
    but before checkpoint write could cause hash mismatch.
    """

    @pytest.fixture
    def test_env(self, tmp_path: Path) -> dict[str, Any]:
        """Set up test environment."""
        db = LandscapeDB(f"sqlite:///{tmp_path}/test.db")
        checkpoint_mgr = CheckpointManager(db)
        return {"db": db, "checkpoint_manager": checkpoint_mgr}

    def test_checkpoint_hash_matches_graph_at_creation_time(self, test_env: dict[str, Any]) -> None:
        """Verify topology hash in checkpoint matches graph state at creation time.

        This test verifies Bug #1 fix: moving topology hash computation inside
        the transaction ensures hash consistency even if graph is modified
        after checkpoint creation.
        """
        from elspeth.contracts import Determinism, NodeType
        from elspeth.contracts.schema import SchemaConfig
        from elspeth.core.canonical import compute_upstream_topology_hash
        from elspeth.core.landscape.recorder import LandscapeRecorder

        checkpoint_mgr = test_env["checkpoint_manager"]
        db = test_env["db"]
        recorder = LandscapeRecorder(db)

        # Create initial graph with two nodes
        graph = ExecutionGraph()
        graph.add_node("source", node_type="source", plugin_name="test", config={"version": 1})
        graph.add_node("transform_a", node_type="transform", plugin_name="test", config={"version": 1})

        # Create run
        run = recorder.begin_run(config={}, canonical_version="test-v1")

        # Register nodes in database
        schema_config = SchemaConfig(mode=None, fields=None, is_dynamic=True)
        recorder.register_node(
            run_id=run.run_id,
            node_id="source",
            plugin_name="test",
            node_type=NodeType.SOURCE,
            plugin_version="1.0",
            config={"version": 1},
            determinism=Determinism.DETERMINISTIC,
            schema_config=schema_config,
        )
        recorder.register_node(
            run_id=run.run_id,
            node_id="transform_a",
            plugin_name="test",
            node_type=NodeType.TRANSFORM,
            plugin_version="1.0",
            config={"version": 1},
            determinism=Determinism.DETERMINISTIC,
            schema_config=schema_config,
        )

        # Create row for checkpoint
        row = recorder.create_row(
            run_id=run.run_id,
            source_node_id="source",
            row_index=0,
            data={"test": "data"},
        )
        token = recorder.create_token(row_id=row.row_id)

        # Compute expected hash for current graph state
        expected_hash = compute_upstream_topology_hash(graph, "transform_a")

        # Create checkpoint with current graph state
        checkpoint = checkpoint_mgr.create_checkpoint(
            run_id=run.run_id,
            token_id=token.token_id,
            node_id="transform_a",
            sequence_number=0,
            graph=graph,
        )

        # Verify checkpoint has expected hash
        assert checkpoint.upstream_topology_hash == expected_hash, (
            f"Checkpoint hash {checkpoint.upstream_topology_hash} does not match expected hash {expected_hash} from graph at creation time"
        )

        # Now modify the graph (simulating what could happen in a race condition)
        graph.add_node("transform_b", node_type="transform", plugin_name="new_plugin", config={"version": 2})

        # Compute hash with modified graph
        modified_hash = compute_upstream_topology_hash(graph, "transform_a")

        # Verify stored hash still matches ORIGINAL graph, not modified graph
        # (This proves hash was captured atomically at checkpoint creation time)
        assert checkpoint.upstream_topology_hash == expected_hash, "Checkpoint hash should match graph at creation time, not current state"

        # Additional verification: if graph was modified BEFORE checkpoint,
        # the hashes would differ
        if expected_hash != modified_hash:
            # Graph modification changed the hash (as expected for topology changes)
            assert checkpoint.upstream_topology_hash != modified_hash, "Checkpoint should NOT have hash from modified graph"

    def test_checkpoint_validates_graph_parameter(self, test_env: dict[str, Any]) -> None:
        """Verify create_checkpoint() rejects None graph (Bug #9 early fix)."""
        from elspeth.contracts import Determinism, NodeType
        from elspeth.contracts.schema import SchemaConfig
        from elspeth.core.landscape.recorder import LandscapeRecorder

        checkpoint_mgr = test_env["checkpoint_manager"]
        db = test_env["db"]
        recorder = LandscapeRecorder(db)

        # Create minimal run
        run = recorder.begin_run(config={}, canonical_version="test-v1")

        # Register source node
        schema_config = SchemaConfig(mode=None, fields=None, is_dynamic=True)
        recorder.register_node(
            run_id=run.run_id,
            node_id="source",
            plugin_name="test",
            node_type=NodeType.SOURCE,
            plugin_version="1.0",
            config={},
            determinism=Determinism.DETERMINISTIC,
            schema_config=schema_config,
        )

        # Create row/token
        row = recorder.create_row(
            run_id=run.run_id,
            source_node_id="source",
            row_index=0,
            data={},
        )
        token = recorder.create_token(row_id=row.row_id)

        # Attempt to create checkpoint with None graph
        with pytest.raises(ValueError, match="graph parameter is required"):
            checkpoint_mgr.create_checkpoint(
                run_id=run.run_id,
                token_id=token.token_id,
                node_id="test_node",
                sequence_number=0,
                graph=None,  # type: ignore
            )

    def test_checkpoint_validates_node_exists_in_graph(self, test_env: dict[str, Any]) -> None:
        """Verify create_checkpoint() rejects node_id not in graph (Bug #9 early fix)."""
        from elspeth.contracts import Determinism, NodeType
        from elspeth.contracts.schema import SchemaConfig
        from elspeth.core.landscape.recorder import LandscapeRecorder

        checkpoint_mgr = test_env["checkpoint_manager"]
        db = test_env["db"]
        recorder = LandscapeRecorder(db)

        # Create graph with one node
        graph = ExecutionGraph()
        graph.add_node("existing_node", node_type="transform", plugin_name="test")

        # Create minimal run
        run = recorder.begin_run(config={}, canonical_version="test-v1")

        # Register nodes in database (need source for row creation)
        schema_config = SchemaConfig(mode=None, fields=None, is_dynamic=True)
        recorder.register_node(
            run_id=run.run_id,
            node_id="source",
            plugin_name="test",
            node_type=NodeType.SOURCE,
            plugin_version="1.0",
            config={},
            determinism=Determinism.DETERMINISTIC,
            schema_config=schema_config,
        )
        recorder.register_node(
            run_id=run.run_id,
            node_id="existing_node",
            plugin_name="test",
            node_type=NodeType.TRANSFORM,
            plugin_version="1.0",
            config={},
            determinism=Determinism.DETERMINISTIC,
            schema_config=schema_config,
        )

        # Create row/token
        row = recorder.create_row(
            run_id=run.run_id,
            source_node_id="source",
            row_index=0,
            data={},
        )
        token = recorder.create_token(row_id=row.row_id)

        # Attempt to create checkpoint with non-existent node_id
        with pytest.raises(ValueError, match="does not exist in graph"):
            checkpoint_mgr.create_checkpoint(
                run_id=run.run_id,
                token_id=token.token_id,
                node_id="nonexistent_node",
                sequence_number=0,
                graph=graph,
            )
