"""Tests for checkpoint topology compatibility validation.

Tests the topological validation approach that allows safe config changes
(downstream additions, sink changes) while blocking unsafe changes
(upstream modifications, checkpoint node removal).
"""

from datetime import UTC, datetime

from elspeth.contracts import Checkpoint, RoutingMode
from elspeth.core.canonical import stable_hash
from elspeth.core.checkpoint.compatibility import CheckpointCompatibilityValidator
from elspeth.core.dag import ExecutionGraph


class TestForkJoinTopology:
    """Tests for fork/join (coalesce) topologies - CRITICAL GAP identified by QA review."""

    def test_resume_rejects_fork_path_change(self) -> None:
        """Changing one fork path should reject if it feeds checkpoint."""
        # Original graph: source → gate → path_A → coalesce → checkpoint
        #                              → path_B ────┘
        original_graph = ExecutionGraph()
        original_graph.add_node("source", node_type="source", plugin_name="csv")
        original_graph.add_node("gate", node_type="gate", plugin_name="threshold_gate")
        original_graph.add_node("path_A", node_type="transform", plugin_name="passthrough", config={"version": "v1"})
        original_graph.add_node("path_B", node_type="transform", plugin_name="passthrough", config={"version": "v1"})
        original_graph.add_node("coalesce", node_type="coalesce", plugin_name="coalesce")
        original_graph.add_node("checkpoint_node", node_type="transform", plugin_name="llm", config={"prompt": "test"})

        original_graph.add_edge("source", "gate", label="continue", mode=RoutingMode.MOVE)
        original_graph.add_edge("gate", "path_A", label="branch_a", mode=RoutingMode.COPY)
        original_graph.add_edge("gate", "path_B", label="branch_b", mode=RoutingMode.COPY)
        original_graph.add_edge("path_A", "coalesce", label="continue", mode=RoutingMode.MOVE)
        original_graph.add_edge("path_B", "coalesce", label="continue", mode=RoutingMode.MOVE)
        original_graph.add_edge("coalesce", "checkpoint_node", label="continue", mode=RoutingMode.MOVE)

        # Create checkpoint with original topology
        validator = CheckpointCompatibilityValidator()
        original_topology_hash = validator.compute_upstream_topology_hash(original_graph, "checkpoint_node")
        original_config_hash = stable_hash({"prompt": "test"})

        checkpoint = Checkpoint(
            checkpoint_id="ckpt-001",
            run_id="run-001",
            token_id="tok-001",
            node_id="checkpoint_node",
            sequence_number=10,
            created_at=datetime.now(UTC),
            upstream_topology_hash=original_topology_hash,
            checkpoint_node_config_hash=original_config_hash,
        )

        # Modified graph: change path_A config
        modified_graph = ExecutionGraph()
        modified_graph.add_node("source", node_type="source", plugin_name="csv")
        modified_graph.add_node("gate", node_type="gate", plugin_name="threshold_gate")
        modified_graph.add_node("path_A", node_type="transform", plugin_name="passthrough", config={"version": "v2"})  # CHANGED
        modified_graph.add_node("path_B", node_type="transform", plugin_name="passthrough", config={"version": "v1"})
        modified_graph.add_node("coalesce", node_type="coalesce", plugin_name="coalesce")
        modified_graph.add_node("checkpoint_node", node_type="transform", plugin_name="llm", config={"prompt": "test"})

        modified_graph.add_edge("source", "gate", label="continue", mode=RoutingMode.MOVE)
        modified_graph.add_edge("gate", "path_A", label="branch_a", mode=RoutingMode.COPY)
        modified_graph.add_edge("gate", "path_B", label="branch_b", mode=RoutingMode.COPY)
        modified_graph.add_edge("path_A", "coalesce", label="continue", mode=RoutingMode.MOVE)
        modified_graph.add_edge("path_B", "coalesce", label="continue", mode=RoutingMode.MOVE)
        modified_graph.add_edge("coalesce", "checkpoint_node", label="continue", mode=RoutingMode.MOVE)

        # Should FAIL - upstream path changed
        result = validator.validate(checkpoint, modified_graph)

        assert not result.can_resume
        assert "upstream" in result.reason.lower() or "structure changed" in result.reason.lower()

    def test_resume_allows_fork_path_change_after_checkpoint(self) -> None:
        """Changing fork path AFTER checkpoint is safe."""
        # Original: checkpoint → gate → path_A → sink_A
        #                             → path_B → sink_B
        original_graph = ExecutionGraph()
        original_graph.add_node("source", node_type="source", plugin_name="csv")
        original_graph.add_node("checkpoint_node", node_type="transform", plugin_name="llm", config={"prompt": "test"})
        original_graph.add_node("gate", node_type="gate", plugin_name="threshold_gate")
        original_graph.add_node("path_A", node_type="transform", plugin_name="passthrough")
        original_graph.add_node("sink_A", node_type="sink", plugin_name="csv")

        original_graph.add_edge("source", "checkpoint_node", label="continue", mode=RoutingMode.MOVE)
        original_graph.add_edge("checkpoint_node", "gate", label="continue", mode=RoutingMode.MOVE)
        original_graph.add_edge("gate", "path_A", label="branch_a", mode=RoutingMode.COPY)
        original_graph.add_edge("path_A", "sink_A", label="continue", mode=RoutingMode.MOVE)

        validator = CheckpointCompatibilityValidator()
        original_topology_hash = validator.compute_upstream_topology_hash(original_graph, "checkpoint_node")
        original_config_hash = stable_hash({"prompt": "test"})

        checkpoint = Checkpoint(
            checkpoint_id="ckpt-002",
            run_id="run-002",
            token_id="tok-002",
            node_id="checkpoint_node",
            sequence_number=5,
            created_at=datetime.now(UTC),
            upstream_topology_hash=original_topology_hash,
            checkpoint_node_config_hash=original_config_hash,
        )

        # Modified: Add new fork path after checkpoint
        modified_graph = ExecutionGraph()
        modified_graph.add_node("source", node_type="source", plugin_name="csv")
        modified_graph.add_node("checkpoint_node", node_type="transform", plugin_name="llm", config={"prompt": "test"})
        modified_graph.add_node("gate", node_type="gate", plugin_name="threshold_gate")
        modified_graph.add_node("path_A", node_type="transform", plugin_name="passthrough")
        modified_graph.add_node("path_C", node_type="transform", plugin_name="new_transform")  # NEW
        modified_graph.add_node("sink_A", node_type="sink", plugin_name="csv")
        modified_graph.add_node("sink_C", node_type="sink", plugin_name="csv")  # NEW

        modified_graph.add_edge("source", "checkpoint_node", label="continue", mode=RoutingMode.MOVE)
        modified_graph.add_edge("checkpoint_node", "gate", label="continue", mode=RoutingMode.MOVE)
        modified_graph.add_edge("gate", "path_A", label="branch_a", mode=RoutingMode.COPY)
        modified_graph.add_edge("gate", "path_C", label="branch_c", mode=RoutingMode.COPY)  # NEW
        modified_graph.add_edge("path_A", "sink_A", label="continue", mode=RoutingMode.MOVE)
        modified_graph.add_edge("path_C", "sink_C", label="continue", mode=RoutingMode.MOVE)  # NEW

        # Should PASS - downstream change
        result = validator.validate(checkpoint, modified_graph)

        assert result.can_resume


class TestTransitiveUpstreamChanges:
    """Tests for transitive upstream changes - CRITICAL GAP identified by QA review."""

    def test_resume_rejects_grandparent_node_change(self) -> None:
        """Changing node 2+ hops upstream should reject."""
        # Original: source → A → B → checkpoint
        original_graph = ExecutionGraph()
        original_graph.add_node("source", node_type="source", plugin_name="csv", config={"path": "input.csv"})
        original_graph.add_node("transform_A", node_type="transform", plugin_name="passthrough")
        original_graph.add_node("transform_B", node_type="transform", plugin_name="passthrough")
        original_graph.add_node("checkpoint_node", node_type="transform", plugin_name="llm", config={"prompt": "test"})

        original_graph.add_edge("source", "transform_A", label="continue", mode=RoutingMode.MOVE)
        original_graph.add_edge("transform_A", "transform_B", label="continue", mode=RoutingMode.MOVE)
        original_graph.add_edge("transform_B", "checkpoint_node", label="continue", mode=RoutingMode.MOVE)

        validator = CheckpointCompatibilityValidator()
        original_topology_hash = validator.compute_upstream_topology_hash(original_graph, "checkpoint_node")
        original_config_hash = stable_hash({"prompt": "test"})

        checkpoint = Checkpoint(
            checkpoint_id="ckpt-003",
            run_id="run-003",
            token_id="tok-003",
            node_id="checkpoint_node",
            sequence_number=15,
            created_at=datetime.now(UTC),
            upstream_topology_hash=original_topology_hash,
            checkpoint_node_config_hash=original_config_hash,
        )

        # Modified: change source config (grandparent of checkpoint)
        modified_graph = ExecutionGraph()
        modified_graph.add_node("source", node_type="source", plugin_name="csv", config={"path": "input_v2.csv"})  # CHANGED
        modified_graph.add_node("transform_A", node_type="transform", plugin_name="passthrough")
        modified_graph.add_node("transform_B", node_type="transform", plugin_name="passthrough")
        modified_graph.add_node("checkpoint_node", node_type="transform", plugin_name="llm", config={"prompt": "test"})

        modified_graph.add_edge("source", "transform_A", label="continue", mode=RoutingMode.MOVE)
        modified_graph.add_edge("transform_A", "transform_B", label="continue", mode=RoutingMode.MOVE)
        modified_graph.add_edge("transform_B", "checkpoint_node", label="continue", mode=RoutingMode.MOVE)

        # Should FAIL - upstream node changed
        result = validator.validate(checkpoint, modified_graph)

        assert not result.can_resume
        assert "upstream" in result.reason.lower() or "structure changed" in result.reason.lower()

    def test_resume_rejects_deep_upstream_insertion(self) -> None:
        """Inserting transform far upstream should reject."""
        # Original: source → A → B → C → checkpoint
        original_graph = ExecutionGraph()
        original_graph.add_node("source", node_type="source", plugin_name="csv")
        original_graph.add_node("transform_A", node_type="transform", plugin_name="passthrough")
        original_graph.add_node("transform_B", node_type="transform", plugin_name="passthrough")
        original_graph.add_node("transform_C", node_type="transform", plugin_name="passthrough")
        original_graph.add_node("checkpoint_node", node_type="transform", plugin_name="llm", config={"prompt": "test"})

        original_graph.add_edge("source", "transform_A", label="continue", mode=RoutingMode.MOVE)
        original_graph.add_edge("transform_A", "transform_B", label="continue", mode=RoutingMode.MOVE)
        original_graph.add_edge("transform_B", "transform_C", label="continue", mode=RoutingMode.MOVE)
        original_graph.add_edge("transform_C", "checkpoint_node", label="continue", mode=RoutingMode.MOVE)

        validator = CheckpointCompatibilityValidator()
        original_topology_hash = validator.compute_upstream_topology_hash(original_graph, "checkpoint_node")
        original_config_hash = stable_hash({"prompt": "test"})

        checkpoint = Checkpoint(
            checkpoint_id="ckpt-004",
            run_id="run-004",
            token_id="tok-004",
            node_id="checkpoint_node",
            sequence_number=20,
            created_at=datetime.now(UTC),
            upstream_topology_hash=original_topology_hash,
            checkpoint_node_config_hash=original_config_hash,
        )

        # Modified: insert NEW transform far upstream (between source and A)
        modified_graph = ExecutionGraph()
        modified_graph.add_node("source", node_type="source", plugin_name="csv")
        modified_graph.add_node("transform_NEW", node_type="transform", plugin_name="field_mapper")  # NEW
        modified_graph.add_node("transform_A", node_type="transform", plugin_name="passthrough")
        modified_graph.add_node("transform_B", node_type="transform", plugin_name="passthrough")
        modified_graph.add_node("transform_C", node_type="transform", plugin_name="passthrough")
        modified_graph.add_node("checkpoint_node", node_type="transform", plugin_name="llm", config={"prompt": "test"})

        modified_graph.add_edge("source", "transform_NEW", label="continue", mode=RoutingMode.MOVE)  # NEW
        modified_graph.add_edge("transform_NEW", "transform_A", label="continue", mode=RoutingMode.MOVE)  # NEW
        modified_graph.add_edge("transform_A", "transform_B", label="continue", mode=RoutingMode.MOVE)
        modified_graph.add_edge("transform_B", "transform_C", label="continue", mode=RoutingMode.MOVE)
        modified_graph.add_edge("transform_C", "checkpoint_node", label="continue", mode=RoutingMode.MOVE)

        # Should FAIL - upstream topology changed
        result = validator.validate(checkpoint, modified_graph)

        assert not result.can_resume


class TestParallelEdgeValidation:
    """Tests for MultiDiGraph parallel edge validation - CRITICAL GAP identified by QA review."""

    def test_topology_hash_includes_edge_keys(self) -> None:
        """Parallel edges must have different keys in hash."""
        # Gate with fork creates parallel edges to same transform
        graph = ExecutionGraph()
        graph.add_node("source", node_type="source", plugin_name="csv")
        graph.add_node("gate", node_type="gate", plugin_name="threshold_gate")
        graph.add_node("transform", node_type="transform", plugin_name="passthrough")
        graph.add_node("checkpoint", node_type="transform", plugin_name="llm", config={"prompt": "test"})

        # Two parallel edges from gate to transform (different route labels)
        graph.add_edge("source", "gate", label="continue", mode=RoutingMode.MOVE)
        graph.add_edge("gate", "transform", label="route_A", mode=RoutingMode.COPY)
        graph.add_edge("gate", "transform", label="route_B", mode=RoutingMode.COPY)
        graph.add_edge("transform", "checkpoint", label="continue", mode=RoutingMode.MOVE)

        validator = CheckpointCompatibilityValidator()
        topology_hash_with_both_edges = validator.compute_upstream_topology_hash(graph, "checkpoint")

        # Create second graph with only one edge
        graph2 = ExecutionGraph()
        graph2.add_node("source", node_type="source", plugin_name="csv")
        graph2.add_node("gate", node_type="gate", plugin_name="threshold_gate")
        graph2.add_node("transform", node_type="transform", plugin_name="passthrough")
        graph2.add_node("checkpoint", node_type="transform", plugin_name="llm", config={"prompt": "test"})

        graph2.add_edge("source", "gate", label="continue", mode=RoutingMode.MOVE)
        graph2.add_edge("gate", "transform", label="route_A", mode=RoutingMode.COPY)  # Only route_A
        graph2.add_edge("transform", "checkpoint", label="continue", mode=RoutingMode.MOVE)

        topology_hash_with_one_edge = validator.compute_upstream_topology_hash(graph2, "checkpoint")

        # Hashes MUST be different - parallel edges matter
        assert topology_hash_with_both_edges != topology_hash_with_one_edge

    def test_resume_rejects_parallel_edge_addition(self) -> None:
        """Adding second edge between same nodes should reject."""
        # Original: source → gate --[approved]--> transform → checkpoint
        original_graph = ExecutionGraph()
        original_graph.add_node("source", node_type="source", plugin_name="csv")
        original_graph.add_node("gate", node_type="gate", plugin_name="threshold_gate")
        original_graph.add_node("upstream_transform", node_type="transform", plugin_name="passthrough")
        original_graph.add_node("checkpoint_node", node_type="transform", plugin_name="llm", config={"prompt": "test"})

        original_graph.add_edge("source", "gate", label="continue", mode=RoutingMode.MOVE)
        original_graph.add_edge("gate", "upstream_transform", label="approved", mode=RoutingMode.MOVE)
        original_graph.add_edge("upstream_transform", "checkpoint_node", label="continue", mode=RoutingMode.MOVE)

        validator = CheckpointCompatibilityValidator()
        original_topology_hash = validator.compute_upstream_topology_hash(original_graph, "checkpoint_node")
        original_config_hash = stable_hash({"prompt": "test"})

        checkpoint = Checkpoint(
            checkpoint_id="ckpt-005",
            run_id="run-005",
            token_id="tok-005",
            node_id="checkpoint_node",
            sequence_number=25,
            created_at=datetime.now(UTC),
            upstream_topology_hash=original_topology_hash,
            checkpoint_node_config_hash=original_config_hash,
        )

        # Modified: Add second parallel edge between gate and upstream_transform
        modified_graph = ExecutionGraph()
        modified_graph.add_node("source", node_type="source", plugin_name="csv")
        modified_graph.add_node("gate", node_type="gate", plugin_name="threshold_gate")
        modified_graph.add_node("upstream_transform", node_type="transform", plugin_name="passthrough")
        modified_graph.add_node("checkpoint_node", node_type="transform", plugin_name="llm", config={"prompt": "test"})

        modified_graph.add_edge("source", "gate", label="continue", mode=RoutingMode.MOVE)
        modified_graph.add_edge("gate", "upstream_transform", label="approved", mode=RoutingMode.MOVE)
        modified_graph.add_edge("gate", "upstream_transform", label="verified", mode=RoutingMode.COPY)  # NEW parallel edge
        modified_graph.add_edge("upstream_transform", "checkpoint_node", label="continue", mode=RoutingMode.MOVE)

        # Should FAIL - edge structure changed in upstream
        result = validator.validate(checkpoint, modified_graph)

        assert not result.can_resume


# Bug #7 fix: Legacy checkpoint test class removed
# With nullable=False on topology hash fields, legacy checkpoints cannot exist in the system.
# This enforces the "No Legacy Code Policy" - old checkpoints are incompatible by design.
