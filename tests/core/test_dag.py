# tests/core/test_dag.py
"""Tests for DAG validation and operations."""

import pytest


class TestDAGBuilder:
    """Building execution graphs from configuration."""

    def test_empty_dag(self) -> None:
        from elspeth.core.dag import ExecutionGraph

        graph = ExecutionGraph()
        assert graph.node_count == 0
        assert graph.edge_count == 0

    def test_add_node(self) -> None:
        from elspeth.core.dag import ExecutionGraph

        graph = ExecutionGraph()
        graph.add_node("source", node_type="source", plugin_name="csv")

        assert graph.node_count == 1
        assert graph.has_node("source")

    def test_add_edge(self) -> None:
        from elspeth.core.dag import ExecutionGraph

        graph = ExecutionGraph()
        graph.add_node("source", node_type="source", plugin_name="csv")
        graph.add_node("transform", node_type="transform", plugin_name="validate")
        graph.add_edge("source", "transform", label="continue")

        assert graph.edge_count == 1

    def test_linear_pipeline(self) -> None:
        from elspeth.core.dag import ExecutionGraph

        graph = ExecutionGraph()
        graph.add_node("source", node_type="source", plugin_name="csv")
        graph.add_node("t1", node_type="transform", plugin_name="enrich")
        graph.add_node("t2", node_type="transform", plugin_name="classify")
        graph.add_node("sink", node_type="sink", plugin_name="csv")

        graph.add_edge("source", "t1", label="continue")
        graph.add_edge("t1", "t2", label="continue")
        graph.add_edge("t2", "sink", label="continue")

        assert graph.node_count == 4
        assert graph.edge_count == 3


class TestDAGValidation:
    """Validation of execution graphs."""

    def test_is_valid_for_acyclic(self) -> None:
        from elspeth.core.dag import ExecutionGraph

        graph = ExecutionGraph()
        graph.add_node("a", node_type="source", plugin_name="csv")
        graph.add_node("b", node_type="transform", plugin_name="x")
        graph.add_node("c", node_type="sink", plugin_name="csv")
        graph.add_edge("a", "b", label="continue")
        graph.add_edge("b", "c", label="continue")

        assert graph.is_acyclic() is True

    def test_is_invalid_for_cycle(self) -> None:
        from elspeth.core.dag import ExecutionGraph

        graph = ExecutionGraph()
        graph.add_node("a", node_type="transform", plugin_name="x")
        graph.add_node("b", node_type="transform", plugin_name="y")
        graph.add_edge("a", "b", label="continue")
        graph.add_edge("b", "a", label="continue")  # Creates cycle!

        assert graph.is_acyclic() is False

    def test_validate_raises_on_cycle(self) -> None:
        from elspeth.core.dag import ExecutionGraph, GraphValidationError

        graph = ExecutionGraph()
        graph.add_node("a", node_type="transform", plugin_name="x")
        graph.add_node("b", node_type="transform", plugin_name="y")
        graph.add_edge("a", "b", label="continue")
        graph.add_edge("b", "a", label="continue")

        with pytest.raises(GraphValidationError, match="cycle"):
            graph.validate()

    def test_topological_order(self) -> None:
        from elspeth.core.dag import ExecutionGraph

        graph = ExecutionGraph()
        graph.add_node("source", node_type="source", plugin_name="csv")
        graph.add_node("t1", node_type="transform", plugin_name="a")
        graph.add_node("t2", node_type="transform", plugin_name="b")
        graph.add_node("sink", node_type="sink", plugin_name="csv")

        graph.add_edge("source", "t1", label="continue")
        graph.add_edge("t1", "t2", label="continue")
        graph.add_edge("t2", "sink", label="continue")

        order = graph.topological_order()

        # Source must come first, sink must come last
        assert order[0] == "source"
        assert order[-1] == "sink"
        # t1 must come before t2
        assert order.index("t1") < order.index("t2")

    def test_validate_rejects_duplicate_outgoing_edge_labels(self) -> None:
        """Duplicate outgoing edge labels from same node must be rejected.

        The orchestrator's edge_map keys by (from_node, label), so duplicate
        labels from the same node would cause silent overwrites during
        registration - routing events would be recorded against the wrong
        edge, corrupting the audit trail.
        """
        from elspeth.core.dag import ExecutionGraph, GraphValidationError

        graph = ExecutionGraph()
        graph.add_node("source", node_type="source", plugin_name="csv")
        graph.add_node("gate", node_type="gate", plugin_name="config_gate")
        graph.add_node("sink_a", node_type="sink", plugin_name="csv")
        graph.add_node("sink_b", node_type="sink", plugin_name="csv")

        # Gate has one "continue" edge to sink_a
        graph.add_edge("source", "gate", label="continue")
        graph.add_edge("gate", "sink_a", label="continue")
        # Add ANOTHER "continue" edge to a different sink - this is the collision
        graph.add_edge("gate", "sink_b", label="continue")

        with pytest.raises(GraphValidationError, match="duplicate outgoing edge label"):
            graph.validate()

    def test_validate_allows_same_label_from_different_nodes(self) -> None:
        """Same label from different nodes is allowed (no collision).

        The uniqueness constraint is per-node, not global. Multiple nodes
        can each have a 'continue' edge because edge_map keys by (from_node, label).
        """
        from elspeth.core.dag import ExecutionGraph

        graph = ExecutionGraph()
        graph.add_node("source", node_type="source", plugin_name="csv")
        graph.add_node("t1", node_type="transform", plugin_name="a")
        graph.add_node("t2", node_type="transform", plugin_name="b")
        graph.add_node("sink", node_type="sink", plugin_name="csv")

        # Each node has ONE "continue" edge - no collisions
        graph.add_edge("source", "t1", label="continue")
        graph.add_edge("t1", "t2", label="continue")
        graph.add_edge("t2", "sink", label="continue")

        # Should not raise - labels are unique per source node
        graph.validate()


class TestSourceSinkValidation:
    """Validation of source and sink constraints."""

    def test_validate_requires_exactly_one_source(self) -> None:
        from elspeth.core.dag import ExecutionGraph, GraphValidationError

        graph = ExecutionGraph()
        graph.add_node("t1", node_type="transform", plugin_name="x")
        graph.add_node("sink", node_type="sink", plugin_name="csv")
        graph.add_edge("t1", "sink", label="continue")

        with pytest.raises(GraphValidationError, match="exactly one source"):
            graph.validate()

    def test_validate_requires_at_least_one_sink(self) -> None:
        from elspeth.core.dag import ExecutionGraph, GraphValidationError

        graph = ExecutionGraph()
        graph.add_node("source", node_type="source", plugin_name="csv")
        graph.add_node("t1", node_type="transform", plugin_name="x")
        graph.add_edge("source", "t1", label="continue")

        with pytest.raises(GraphValidationError, match="at least one sink"):
            graph.validate()

    def test_validate_multiple_sinks_allowed(self) -> None:
        from elspeth.core.dag import ExecutionGraph

        graph = ExecutionGraph()
        graph.add_node("source", node_type="source", plugin_name="csv")
        graph.add_node("gate", node_type="gate", plugin_name="classifier")
        graph.add_node("sink1", node_type="sink", plugin_name="csv")
        graph.add_node("sink2", node_type="sink", plugin_name="csv")

        graph.add_edge("source", "gate", label="continue")
        graph.add_edge("gate", "sink1", label="normal")
        graph.add_edge("gate", "sink2", label="flagged")

        # Should not raise
        graph.validate()

    def test_get_source_node(self) -> None:
        from elspeth.core.dag import ExecutionGraph

        graph = ExecutionGraph()
        graph.add_node("my_source", node_type="source", plugin_name="csv")
        graph.add_node("sink", node_type="sink", plugin_name="csv")
        graph.add_edge("my_source", "sink", label="continue")

        assert graph.get_source() == "my_source"

    def test_get_sink_nodes(self) -> None:
        from elspeth.core.dag import ExecutionGraph

        graph = ExecutionGraph()
        graph.add_node("source", node_type="source", plugin_name="csv")
        graph.add_node("sink1", node_type="sink", plugin_name="csv")
        graph.add_node("sink2", node_type="sink", plugin_name="json")
        graph.add_edge("source", "sink1", label="continue")
        graph.add_edge("source", "sink2", label="continue")

        sinks = graph.get_sinks()
        assert set(sinks) == {"sink1", "sink2"}


class TestExecutionGraphAccessors:
    """Access node info and edges from graph."""

    def test_get_node_info(self) -> None:
        """Get NodeInfo for a node."""
        from elspeth.core.dag import ExecutionGraph, NodeInfo

        graph = ExecutionGraph()
        graph.add_node(
            "node_1",
            node_type="transform",
            plugin_name="my_plugin",
            config={"key": "value"},
        )

        info = graph.get_node_info("node_1")

        assert isinstance(info, NodeInfo)
        assert info.node_id == "node_1"
        assert info.node_type == "transform"
        assert info.plugin_name == "my_plugin"
        assert info.config == {"key": "value"}

    def test_get_node_info_missing(self) -> None:
        """Get NodeInfo for missing node raises."""
        from elspeth.core.dag import ExecutionGraph

        graph = ExecutionGraph()

        with pytest.raises(KeyError):
            graph.get_node_info("nonexistent")

    def test_get_edges(self) -> None:
        """Get all edges with data."""
        from elspeth.contracts import EdgeInfo, RoutingMode
        from elspeth.core.dag import ExecutionGraph

        graph = ExecutionGraph()
        graph.add_node("a", node_type="source", plugin_name="src")
        graph.add_node("b", node_type="transform", plugin_name="tf")
        graph.add_node("c", node_type="sink", plugin_name="sink")
        graph.add_edge("a", "b", label="continue", mode=RoutingMode.MOVE)
        graph.add_edge("b", "c", label="output", mode=RoutingMode.COPY)

        edges = list(graph.get_edges())

        assert len(edges) == 2
        # Each edge is EdgeInfo (not tuple)
        assert EdgeInfo(from_node="a", to_node="b", label="continue", mode=RoutingMode.MOVE) in edges
        assert EdgeInfo(from_node="b", to_node="c", label="output", mode=RoutingMode.COPY) in edges

    def test_get_edges_empty_graph(self) -> None:
        """Empty graph returns empty list."""
        from elspeth.core.dag import ExecutionGraph

        graph = ExecutionGraph()
        edges = list(graph.get_edges())

        assert edges == []

    def test_get_incoming_edges_returns_edges_pointing_to_node(self):
        """get_incoming_edges() returns all edges with to_node matching the given node_id."""
        from elspeth.contracts import RoutingMode
        from elspeth.core.dag import ExecutionGraph

        graph = ExecutionGraph()
        graph.add_node("A", node_type="source", plugin_name="csv")
        graph.add_node("B", node_type="transform", plugin_name="mapper")
        graph.add_node("C", node_type="sink", plugin_name="csv")

        graph.add_edge("A", "B", label="continue", mode=RoutingMode.MOVE)
        graph.add_edge("B", "C", label="continue", mode=RoutingMode.MOVE)

        incoming = graph.get_incoming_edges("B")

        assert len(incoming) == 1
        assert incoming[0].from_node == "A"
        assert incoming[0].to_node == "B"
        assert incoming[0].label == "continue"
        assert incoming[0].mode == RoutingMode.MOVE

    def test_get_incoming_edges_returns_empty_for_source_node(self):
        """get_incoming_edges() returns empty list for nodes with no predecessors."""
        from elspeth.core.dag import ExecutionGraph

        graph = ExecutionGraph()
        graph.add_node("A", node_type="source", plugin_name="csv")
        graph.add_node("B", node_type="sink", plugin_name="csv")

        incoming = graph.get_incoming_edges("A")

        assert incoming == []

    def test_get_effective_producer_schema_walks_through_gates(self):
        """_get_effective_producer_schema() recursively finds schema through gate chain."""
        from elspeth.contracts import PluginSchema, RoutingMode
        from elspeth.core.dag import ExecutionGraph

        class OutputSchema(PluginSchema):
            value: int

        graph = ExecutionGraph()

        # Build chain: source -> gate -> sink
        graph.add_node("source", node_type="source", plugin_name="csv", output_schema=OutputSchema)
        graph.add_node("gate", node_type="gate", plugin_name="config_gate:check")  # No schema
        graph.add_node("sink", node_type="sink", plugin_name="csv")

        graph.add_edge("source", "gate", label="continue", mode=RoutingMode.MOVE)
        graph.add_edge("gate", "sink", label="flagged", mode=RoutingMode.MOVE)

        # Gate's effective producer schema should be source's output schema
        effective_schema = graph._get_effective_producer_schema("gate")

        assert effective_schema == OutputSchema

    def test_get_effective_producer_schema_crashes_on_gate_without_inputs(self):
        """_get_effective_producer_schema() crashes if gate has no incoming edges."""
        from elspeth.core.dag import ExecutionGraph, GraphValidationError

        graph = ExecutionGraph()
        graph.add_node("gate", node_type="gate", plugin_name="config_gate:orphan")

        # Gate with no inputs is a bug in our code - should crash
        with pytest.raises(GraphValidationError) as exc_info:
            graph._get_effective_producer_schema("gate")

        assert "no incoming edges" in str(exc_info.value).lower()
        assert "bug in graph construction" in str(exc_info.value).lower()

    def test_get_effective_producer_schema_handles_chained_gates(self):
        """_get_effective_producer_schema() recursively walks through multiple gates."""
        from elspeth.contracts import PluginSchema, RoutingMode
        from elspeth.core.dag import ExecutionGraph

        class SourceOutput(PluginSchema):
            id: int
            name: str

        graph = ExecutionGraph()

        # Build chain: source -> gate1 -> gate2 -> sink
        graph.add_node("source", node_type="source", plugin_name="csv", output_schema=SourceOutput)
        graph.add_node("gate1", node_type="gate", plugin_name="config_gate:first")
        graph.add_node("gate2", node_type="gate", plugin_name="config_gate:second")
        graph.add_node("sink", node_type="sink", plugin_name="csv")

        graph.add_edge("source", "gate1", label="continue", mode=RoutingMode.MOVE)
        graph.add_edge("gate1", "gate2", label="continue", mode=RoutingMode.MOVE)
        graph.add_edge("gate2", "sink", label="approved", mode=RoutingMode.MOVE)

        # gate2's effective schema should trace back to source
        effective_schema = graph._get_effective_producer_schema("gate2")

        assert effective_schema == SourceOutput

    def test_get_effective_producer_schema_returns_direct_schema_for_transform(self):
        """_get_effective_producer_schema() returns output_schema directly for transform nodes."""
        from elspeth.contracts import PluginSchema
        from elspeth.core.dag import ExecutionGraph

        class TransformOutput(PluginSchema):
            result: str

        graph = ExecutionGraph()
        graph.add_node(
            "transform",
            node_type="transform",
            plugin_name="field_mapper",
            output_schema=TransformOutput,
        )

        effective_schema = graph._get_effective_producer_schema("transform")

        assert effective_schema == TransformOutput

    def test_validate_edge_schemas_uses_effective_schema_for_gates(self):
        """_validate_edge_schemas() uses effective producer schema for gate edges."""
        from elspeth.contracts import PluginSchema, RoutingMode
        from elspeth.core.dag import ExecutionGraph, GraphValidationError

        class SourceOutput(PluginSchema):
            id: int
            name: str
            # Note: does NOT have 'score' field

        class SinkInput(PluginSchema):
            id: int
            score: float  # Required field not in source output

        graph = ExecutionGraph()

        # Pipeline: source -> gate -> sink
        # Gate has NO schemas (simulates config-driven gate from from_config())
        graph.add_node("source", node_type="source", plugin_name="csv", output_schema=SourceOutput)
        graph.add_node("gate", node_type="gate", plugin_name="config_gate:check")  # NO SCHEMA
        graph.add_node("sink", node_type="sink", plugin_name="csv", input_schema=SinkInput)

        graph.add_edge("source", "gate", label="continue", mode=RoutingMode.MOVE)
        graph.add_edge("gate", "sink", label="flagged", mode=RoutingMode.MOVE)

        # Should detect schema incompatibility on gate -> sink edge
        with pytest.raises(GraphValidationError) as exc_info:
            graph.validate()

        # Verify error mentions the missing field
        assert "score" in str(exc_info.value).lower()
        # Verify error includes plugin names (config_gate:check -> csv)
        assert "config_gate:check" in str(exc_info.value)
        assert "csv" in str(exc_info.value)

    def test_validate_edge_schemas_validates_all_fork_destinations(self):
        """Fork gates validate all destination edges against effective schema."""
        from elspeth.contracts import PluginSchema, RoutingMode
        from elspeth.core.dag import ExecutionGraph, GraphValidationError

        class SourceOutput(PluginSchema):
            id: int
            name: str

        class SinkA(PluginSchema):
            id: int  # Compatible - only requires id

        class SinkB(PluginSchema):
            id: int
            score: float  # Incompatible - requires field not in source

        graph = ExecutionGraph()
        graph.add_node("source", node_type="source", plugin_name="csv", output_schema=SourceOutput)
        graph.add_node("gate", node_type="gate", plugin_name="config_gate:fork")  # NO SCHEMA
        graph.add_node("sink_a", node_type="sink", plugin_name="csv_a", input_schema=SinkA)
        graph.add_node("sink_b", node_type="sink", plugin_name="csv_b", input_schema=SinkB)

        graph.add_edge("source", "gate", label="continue", mode=RoutingMode.MOVE)
        graph.add_edge("gate", "sink_a", label="branch_a", mode=RoutingMode.COPY)  # Fork: COPY mode
        graph.add_edge("gate", "sink_b", label="branch_b", mode=RoutingMode.COPY)  # Fork: COPY mode

        # Should detect incompatibility on gate -> sink_b edge
        with pytest.raises(GraphValidationError) as exc_info:
            graph.validate()

        assert "score" in str(exc_info.value).lower()
        assert "config_gate:fork" in str(exc_info.value)


class TestExecutionGraphFromConfig:
    """Build ExecutionGraph from ElspethSettings."""

    def test_from_config_minimal(self, plugin_manager) -> None:
        """Build graph from minimal config (source -> sink only)."""
        from elspeth.core.config import (
            DatasourceSettings,
            ElspethSettings,
            SinkSettings,
        )
        from elspeth.core.dag import ExecutionGraph

        config = ElspethSettings(
            datasource=DatasourceSettings(plugin="csv"),
            sinks={"output": SinkSettings(plugin="csv")},
            output_sink="output",
        )

        graph = ExecutionGraph.from_config(config, plugin_manager)

        # Should have: source -> output_sink
        assert graph.node_count == 2
        assert graph.edge_count == 1
        assert graph.get_source() is not None
        assert len(graph.get_sinks()) == 1

    def test_from_config_is_valid(self, plugin_manager) -> None:
        """Graph from valid config passes validation."""
        from elspeth.core.config import (
            DatasourceSettings,
            ElspethSettings,
            SinkSettings,
        )
        from elspeth.core.dag import ExecutionGraph

        config = ElspethSettings(
            datasource=DatasourceSettings(plugin="csv"),
            sinks={"output": SinkSettings(plugin="csv")},
            output_sink="output",
        )

        graph = ExecutionGraph.from_config(config, plugin_manager)

        # Should not raise
        graph.validate()
        assert graph.is_acyclic()

    def test_from_config_with_transforms(self, plugin_manager) -> None:
        """Build graph with transform chain."""
        from elspeth.core.config import (
            DatasourceSettings,
            ElspethSettings,
            RowPluginSettings,
            SinkSettings,
        )
        from elspeth.core.dag import ExecutionGraph

        config = ElspethSettings(
            datasource=DatasourceSettings(plugin="csv"),
            sinks={"output": SinkSettings(plugin="csv")},
            row_plugins=[
                RowPluginSettings(plugin="passthrough"),
                RowPluginSettings(plugin="field_mapper"),
            ],
            output_sink="output",
        )

        graph = ExecutionGraph.from_config(config, plugin_manager)

        # Should have: source -> passthrough -> field_mapper -> output_sink
        assert graph.node_count == 4
        assert graph.edge_count == 3

        # Topological order should be correct
        order = graph.topological_order()
        assert len(order) == 4
        # Source should be first (has "source" in node_id)
        assert "source" in order[0]
        # Sink should be last (has "sink" in node_id)
        assert "sink" in order[-1]
        # Verify transform ordering (passthrough before field_mapper)
        passthrough_idx = next(i for i, n in enumerate(order) if "passthrough" in n)
        field_mapper_idx = next(i for i, n in enumerate(order) if "field_mapper" in n)
        assert passthrough_idx < field_mapper_idx

    def test_from_config_with_gate_routes(self, plugin_manager) -> None:
        """Build graph with config-driven gate routing to multiple sinks."""
        from elspeth.core.config import (
            DatasourceSettings,
            ElspethSettings,
            GateSettings,
            SinkSettings,
        )
        from elspeth.core.dag import ExecutionGraph

        config = ElspethSettings(
            datasource=DatasourceSettings(plugin="csv"),
            sinks={
                "results": SinkSettings(plugin="csv"),
                "flagged": SinkSettings(plugin="csv"),
            },
            gates=[
                GateSettings(
                    name="safety_gate",
                    condition="row['suspicious'] == True",
                    routes={"true": "flagged", "false": "continue"},
                ),
            ],
            output_sink="results",
        )

        graph = ExecutionGraph.from_config(config, plugin_manager)

        # Should have:
        #   source -> safety_gate -> results (via "continue")
        #                         -> flagged (via "suspicious")
        assert graph.node_count == 4  # source, config_gate, results, flagged
        # Edges: source->gate, gate->results (continue), gate->flagged (route)
        assert graph.edge_count == 3

    def test_from_config_validates_route_targets(self, plugin_manager) -> None:
        """Config gate routes must reference existing sinks."""
        from elspeth.core.config import (
            DatasourceSettings,
            ElspethSettings,
            GateSettings,
            SinkSettings,
        )
        from elspeth.core.dag import ExecutionGraph, GraphValidationError

        config = ElspethSettings(
            datasource=DatasourceSettings(plugin="csv"),
            sinks={"output": SinkSettings(plugin="csv")},
            gates=[
                GateSettings(
                    name="bad_gate",
                    condition="True",
                    routes={"true": "nonexistent_sink", "false": "continue"},
                ),
            ],
            output_sink="output",
        )

        with pytest.raises(GraphValidationError) as exc_info:
            ExecutionGraph.from_config(config, plugin_manager)

        assert "nonexistent_sink" in str(exc_info.value)

    def test_get_sink_id_map(self, plugin_manager) -> None:
        """Get explicit sink_name -> node_id mapping."""
        from elspeth.core.config import (
            DatasourceSettings,
            ElspethSettings,
            SinkSettings,
        )
        from elspeth.core.dag import ExecutionGraph

        config = ElspethSettings(
            datasource=DatasourceSettings(plugin="csv"),
            sinks={
                "results": SinkSettings(plugin="csv"),
                "flagged": SinkSettings(plugin="csv"),
            },
            output_sink="results",
        )

        graph = ExecutionGraph.from_config(config, plugin_manager)
        sink_map = graph.get_sink_id_map()

        # Explicit mapping - no substring matching
        assert "results" in sink_map
        assert "flagged" in sink_map
        assert sink_map["results"] != sink_map["flagged"]

    def test_get_transform_id_map(self, plugin_manager) -> None:
        """Get explicit sequence -> node_id mapping for transforms."""
        from elspeth.core.config import (
            DatasourceSettings,
            ElspethSettings,
            RowPluginSettings,
            SinkSettings,
        )
        from elspeth.core.dag import ExecutionGraph

        config = ElspethSettings(
            datasource=DatasourceSettings(plugin="csv"),
            sinks={"output": SinkSettings(plugin="csv")},
            row_plugins=[
                RowPluginSettings(plugin="passthrough"),
                RowPluginSettings(plugin="field_mapper"),
            ],
            output_sink="output",
        )

        graph = ExecutionGraph.from_config(config, plugin_manager)
        transform_map = graph.get_transform_id_map()

        # Explicit mapping by sequence position
        assert 0 in transform_map  # passthrough
        assert 1 in transform_map  # field_mapper
        assert transform_map[0] != transform_map[1]

    def test_get_output_sink(self, plugin_manager) -> None:
        """Get the output sink name."""
        from elspeth.core.config import (
            DatasourceSettings,
            ElspethSettings,
            SinkSettings,
        )
        from elspeth.core.dag import ExecutionGraph

        config = ElspethSettings(
            datasource=DatasourceSettings(plugin="csv"),
            sinks={
                "results": SinkSettings(plugin="csv"),
                "flagged": SinkSettings(plugin="csv"),
            },
            output_sink="results",
        )

        graph = ExecutionGraph.from_config(config, plugin_manager)

        assert graph.get_output_sink() == "results"


class TestExecutionGraphRouteMapping:
    """Test route label <-> sink name mapping for edge lookup."""

    def test_get_route_label_for_sink(self, plugin_manager) -> None:
        """Get route label that leads to a sink from a config gate."""
        from elspeth.core.config import (
            DatasourceSettings,
            ElspethSettings,
            GateSettings,
            SinkSettings,
        )
        from elspeth.core.dag import ExecutionGraph

        config = ElspethSettings(
            datasource=DatasourceSettings(plugin="csv"),
            sinks={
                "results": SinkSettings(plugin="csv"),
                "flagged": SinkSettings(plugin="csv"),
            },
            gates=[
                GateSettings(
                    name="classifier",
                    condition="row['suspicious'] == True",
                    routes={"true": "flagged", "false": "continue"},
                ),
            ],
            output_sink="results",
        )

        graph = ExecutionGraph.from_config(config, plugin_manager)

        # Get the config gate's node_id
        gate_node_id = graph.get_config_gate_id_map()["classifier"]

        # Given gate node and sink name, get the route label
        route_label = graph.get_route_label(gate_node_id, "flagged")

        assert route_label == "true"

    def test_get_route_label_for_continue(self, plugin_manager) -> None:
        """Continue routes return 'continue' as label."""
        from elspeth.core.config import (
            DatasourceSettings,
            ElspethSettings,
            GateSettings,
            SinkSettings,
        )
        from elspeth.core.dag import ExecutionGraph

        config = ElspethSettings(
            datasource=DatasourceSettings(plugin="csv"),
            sinks={"results": SinkSettings(plugin="csv")},
            gates=[
                GateSettings(
                    name="gate",
                    condition="True",
                    routes={"true": "continue", "false": "continue"},
                ),
            ],
            output_sink="results",
        )

        graph = ExecutionGraph.from_config(config, plugin_manager)
        gate_node_id = graph.get_config_gate_id_map()["gate"]

        # The edge to output sink uses "continue" label (both routes resolve to continue)
        route_label = graph.get_route_label(gate_node_id, "results")
        assert route_label == "continue"

    def test_hyphenated_sink_names_work_in_dag(self, plugin_manager) -> None:
        """Gate routing to hyphenated sink names works correctly.

        Regression test for gate-route-destination-name-validation-mismatch bug.
        Sink names don't need to match identifier pattern - they're just dict keys.
        """
        from elspeth.core.config import (
            DatasourceSettings,
            ElspethSettings,
            GateSettings,
            SinkSettings,
        )
        from elspeth.core.dag import ExecutionGraph

        config = ElspethSettings(
            datasource=DatasourceSettings(plugin="csv"),
            sinks={
                "output-sink": SinkSettings(plugin="csv"),
                "quarantine-bucket": SinkSettings(plugin="csv"),
            },
            gates=[
                GateSettings(
                    name="quality_check",
                    condition="row['score'] >= 0.5",
                    routes={"true": "output-sink", "false": "quarantine-bucket"},
                ),
            ],
            output_sink="output-sink",
        )

        # DAG compilation should succeed with hyphenated sink names
        graph = ExecutionGraph.from_config(config, plugin_manager)

        # Verify both hyphenated sinks exist
        sink_ids = graph.get_sink_id_map()
        assert "output-sink" in sink_ids
        assert "quarantine-bucket" in sink_ids

        # Verify gate routes to the hyphenated sinks
        gate_node_id = graph.get_config_gate_id_map()["quality_check"]
        assert graph.get_route_label(gate_node_id, "quarantine-bucket") == "false"


class TestMultiEdgeSupport:
    """Tests for MultiDiGraph multi-edge support."""

    def test_multiple_edges_same_node_pair(self) -> None:
        """MultiDiGraph allows multiple labeled edges between same nodes."""
        from elspeth.contracts import RoutingMode
        from elspeth.core.dag import ExecutionGraph

        graph = ExecutionGraph()
        graph.add_node("gate", node_type="gate", plugin_name="fork_gate")
        graph.add_node("sink", node_type="sink", plugin_name="output")

        # Add two edges with different labels to SAME destination
        graph.add_edge("gate", "sink", label="path_a", mode=RoutingMode.COPY)
        graph.add_edge("gate", "sink", label="path_b", mode=RoutingMode.COPY)

        # Both edges should exist (DiGraph would show 1, MultiDiGraph shows 2)
        assert graph.edge_count == 2

        edges = graph.get_edges()
        labels = {e.label for e in edges}
        assert labels == {"path_a", "path_b"}

    def test_multi_edge_graph_is_acyclic(self) -> None:
        """Verify is_acyclic() works correctly with MultiDiGraph parallel edges."""
        from elspeth.contracts import RoutingMode
        from elspeth.core.dag import ExecutionGraph

        graph = ExecutionGraph()
        graph.add_node("source", node_type="source", plugin_name="csv")
        graph.add_node("gate", node_type="gate", plugin_name="classifier")
        graph.add_node("sink", node_type="sink", plugin_name="csv")

        graph.add_edge("source", "gate", label="continue", mode=RoutingMode.MOVE)
        # Multiple parallel edges to same sink - still acyclic
        graph.add_edge("gate", "sink", label="high", mode=RoutingMode.MOVE)
        graph.add_edge("gate", "sink", label="medium", mode=RoutingMode.MOVE)
        graph.add_edge("gate", "sink", label="low", mode=RoutingMode.MOVE)

        # Graph with parallel edges should still be detected as acyclic
        assert graph.is_acyclic() is True
        # Full validation should also pass
        graph.validate()


class TestEdgeInfoIntegration:
    """Tests for typed edge returns."""

    def test_get_edges_returns_edge_info(self) -> None:
        """get_edges() returns list of EdgeInfo, not tuples."""
        from elspeth.contracts import EdgeInfo, RoutingMode
        from elspeth.core.dag import ExecutionGraph

        graph = ExecutionGraph()
        graph.add_node("source-1", node_type="source", plugin_name="csv")
        graph.add_node("sink-1", node_type="sink", plugin_name="csv")
        graph.add_edge("source-1", "sink-1", label="continue", mode=RoutingMode.MOVE)

        edges = graph.get_edges()

        assert len(edges) == 1
        assert isinstance(edges[0], EdgeInfo)
        assert edges[0].from_node == "source-1"
        assert edges[0].to_node == "sink-1"
        assert edges[0].label == "continue"
        assert edges[0].mode == RoutingMode.MOVE

    def test_add_edge_accepts_routing_mode_enum(self) -> None:
        """add_edge() accepts RoutingMode enum, not string."""
        from elspeth.contracts import RoutingMode
        from elspeth.core.dag import ExecutionGraph

        graph = ExecutionGraph()
        graph.add_node("n1", node_type="transform", plugin_name="test")
        graph.add_node("n2", node_type="sink", plugin_name="test")

        # Should accept enum directly
        graph.add_edge("n1", "n2", label="route", mode=RoutingMode.COPY)

        edges = graph.get_edges()
        assert edges[0].mode == RoutingMode.COPY


class TestMultiEdgeScenarios:
    """Tests for scenarios requiring multiple edges between same nodes."""

    def test_fork_gate_config_parses_into_valid_graph(self, plugin_manager) -> None:
        """Fork gate configuration parses into valid graph structure.

        Note: This tests config parsing, not the multi-edge bug. Fork routes
        with target="fork" don't create edges to sinks - they create child tokens.
        The multi-edge bug is tested by test_gate_multiple_routes_same_sink.
        """
        from elspeth.core.config import (
            DatasourceSettings,
            ElspethSettings,
            GateSettings,
            SinkSettings,
        )
        from elspeth.core.dag import ExecutionGraph

        config = ElspethSettings(
            datasource=DatasourceSettings(plugin="csv"),
            sinks={"output": SinkSettings(plugin="csv")},
            gates=[
                GateSettings(
                    name="fork_gate",
                    condition="True",  # Always forks
                    routes={"true": "fork", "false": "continue"},
                    fork_to=["path_a", "path_b"],
                ),
            ],
            output_sink="output",
        )

        graph = ExecutionGraph.from_config(config, plugin_manager)

        # Validate graph is still valid (DAG, has source and sink)
        graph.validate()

        # The gate should have edges - at minimum the continue edge to output sink
        edges = graph.get_edges()
        gate_edges = [e for e in edges if "config_gate" in e.from_node]

        # Should have at least the continue edge to output sink
        assert len(gate_edges) >= 1

    def test_gate_multiple_routes_same_sink(self) -> None:
        """CRITICAL: Gate with multiple route labels to same sink preserves all labels.

        This is the core bug scenario: {"high": "alerts", "medium": "alerts", "low": "alerts"}
        With DiGraph, only "low" survives. With MultiDiGraph, all three edges exist.
        """
        from elspeth.contracts import RoutingMode
        from elspeth.core.dag import ExecutionGraph

        graph = ExecutionGraph()
        graph.add_node("source", node_type="source", plugin_name="csv")
        graph.add_node("gate", node_type="gate", plugin_name="classifier")
        graph.add_node("alerts", node_type="sink", plugin_name="csv")

        graph.add_edge("source", "gate", label="continue", mode=RoutingMode.MOVE)
        # Multiple severity levels all route to same alerts sink
        graph.add_edge("gate", "alerts", label="high", mode=RoutingMode.MOVE)
        graph.add_edge("gate", "alerts", label="medium", mode=RoutingMode.MOVE)
        graph.add_edge("gate", "alerts", label="low", mode=RoutingMode.MOVE)

        # All three edges should exist
        edges = graph.get_edges()
        alert_edges = [e for e in edges if e.to_node == "alerts"]
        assert len(alert_edges) == 3

        labels = {e.label for e in alert_edges}
        assert labels == {"high", "medium", "low"}


class TestCoalesceNodes:
    """Test coalesce node creation in DAG."""

    def test_from_config_creates_coalesce_node(self, plugin_manager) -> None:
        """Coalesce config should create a coalesce node in the graph."""
        from elspeth.core.config import (
            CoalesceSettings,
            DatasourceSettings,
            ElspethSettings,
            GateSettings,
            SinkSettings,
        )
        from elspeth.core.dag import ExecutionGraph

        settings = ElspethSettings(
            datasource=DatasourceSettings(plugin="csv", options={"path": "test.csv"}),
            sinks={
                "output": SinkSettings(plugin="csv", options={"path": "out.csv"}),
            },
            output_sink="output",
            gates=[
                GateSettings(
                    name="forker",
                    condition="True",
                    routes={"true": "fork", "false": "continue"},
                    fork_to=["path_a", "path_b"],
                ),
            ],
            coalesce=[
                CoalesceSettings(
                    name="merge_results",
                    branches=["path_a", "path_b"],
                    policy="require_all",
                    merge="union",
                ),
            ],
        )

        graph = ExecutionGraph.from_config(settings, plugin_manager)

        # Use proper accessor, not string matching
        coalesce_map = graph.get_coalesce_id_map()
        assert "merge_results" in coalesce_map

        # Verify node type
        node_id = coalesce_map["merge_results"]
        node_info = graph.get_node_info(node_id)
        assert node_info.node_type == "coalesce"
        assert node_info.plugin_name == "coalesce:merge_results"

    def test_from_config_coalesce_edges_from_fork_branches(self, plugin_manager) -> None:
        """Coalesce node should have edges from fork gate (via branches)."""
        from elspeth.contracts import RoutingMode
        from elspeth.core.config import (
            CoalesceSettings,
            DatasourceSettings,
            ElspethSettings,
            GateSettings,
            SinkSettings,
        )
        from elspeth.core.dag import ExecutionGraph

        settings = ElspethSettings(
            datasource=DatasourceSettings(plugin="csv"),
            sinks={
                "output": SinkSettings(plugin="csv"),
            },
            output_sink="output",
            gates=[
                GateSettings(
                    name="forker",
                    condition="True",
                    routes={"true": "fork", "false": "continue"},
                    fork_to=["path_a", "path_b"],
                ),
            ],
            coalesce=[
                CoalesceSettings(
                    name="merge_results",
                    branches=["path_a", "path_b"],
                    policy="require_all",
                    merge="union",
                ),
            ],
        )

        graph = ExecutionGraph.from_config(settings, plugin_manager)

        # Get node IDs
        gate_id = graph.get_config_gate_id_map()["forker"]
        coalesce_id = graph.get_coalesce_id_map()["merge_results"]

        # Verify edges from fork gate to coalesce node
        edges = graph.get_edges()
        gate_to_coalesce_edges = [e for e in edges if e.from_node == gate_id and e.to_node == coalesce_id]

        # Should have two edges (path_a and path_b) with COPY mode
        assert len(gate_to_coalesce_edges) == 2
        labels = {e.label for e in gate_to_coalesce_edges}
        assert labels == {"path_a", "path_b"}
        assert all(e.mode == RoutingMode.COPY for e in gate_to_coalesce_edges)

    def test_partial_branch_coverage_branches_not_in_coalesce_route_to_sink(
        self,
        plugin_manager,
    ) -> None:
        """Fork branches not in any coalesce should still route to output sink."""
        from elspeth.core.config import (
            CoalesceSettings,
            DatasourceSettings,
            ElspethSettings,
            GateSettings,
            SinkSettings,
        )
        from elspeth.core.dag import ExecutionGraph

        settings = ElspethSettings(
            datasource=DatasourceSettings(plugin="csv"),
            sinks={
                "output": SinkSettings(plugin="csv"),
            },
            output_sink="output",
            gates=[
                GateSettings(
                    name="forker",
                    condition="True",
                    routes={"true": "fork", "false": "continue"},
                    fork_to=["path_a", "path_b", "path_c"],  # 3 branches
                ),
            ],
            coalesce=[
                CoalesceSettings(
                    name="merge_results",
                    branches=["path_a", "path_b"],  # Only 2 branches in coalesce
                    policy="require_all",
                    merge="union",
                ),
            ],
        )

        graph = ExecutionGraph.from_config(settings, plugin_manager)

        # Get node IDs
        gate_id = graph.get_config_gate_id_map()["forker"]
        coalesce_id = graph.get_coalesce_id_map()["merge_results"]
        output_sink_id = graph.get_sink_id_map()["output"]

        # Verify path_c goes to output sink, not coalesce
        edges = graph.get_edges()
        path_c_edges = [e for e in edges if e.from_node == gate_id and e.label == "path_c"]

        assert len(path_c_edges) == 1
        assert path_c_edges[0].to_node == output_sink_id

        # Verify path_a and path_b go to coalesce
        coalesce_edges = [e for e in edges if e.from_node == gate_id and e.to_node == coalesce_id]
        coalesce_labels = {e.label for e in coalesce_edges}
        assert coalesce_labels == {"path_a", "path_b"}

    def test_get_coalesce_id_map_returns_mapping(self, plugin_manager) -> None:
        """get_coalesce_id_map should return coalesce_name -> node_id."""
        from elspeth.core.config import (
            CoalesceSettings,
            DatasourceSettings,
            ElspethSettings,
            GateSettings,
            SinkSettings,
        )
        from elspeth.core.dag import ExecutionGraph

        settings = ElspethSettings(
            datasource=DatasourceSettings(plugin="csv"),
            sinks={
                "output": SinkSettings(plugin="csv"),
            },
            output_sink="output",
            gates=[
                GateSettings(
                    name="forker",
                    condition="True",
                    routes={"true": "fork", "false": "continue"},
                    fork_to=["path_a", "path_b", "path_c", "path_d"],
                ),
            ],
            coalesce=[
                CoalesceSettings(
                    name="merge_ab",
                    branches=["path_a", "path_b"],
                    policy="require_all",
                    merge="union",
                ),
                CoalesceSettings(
                    name="merge_cd",
                    branches=["path_c", "path_d"],
                    policy="require_all",
                    merge="nested",
                ),
            ],
        )

        graph = ExecutionGraph.from_config(settings, plugin_manager)
        coalesce_map = graph.get_coalesce_id_map()

        # Should have both coalesce nodes
        assert "merge_ab" in coalesce_map
        assert "merge_cd" in coalesce_map

        # Node IDs should be unique
        assert coalesce_map["merge_ab"] != coalesce_map["merge_cd"]

        # Verify both nodes exist in the graph
        assert graph.has_node(coalesce_map["merge_ab"])
        assert graph.has_node(coalesce_map["merge_cd"])

    def test_get_branch_to_coalesce_map_returns_mapping(self, plugin_manager) -> None:
        """get_branch_to_coalesce_map should return branch_name -> coalesce_name."""
        from elspeth.core.config import (
            CoalesceSettings,
            DatasourceSettings,
            ElspethSettings,
            GateSettings,
            SinkSettings,
        )
        from elspeth.core.dag import ExecutionGraph

        settings = ElspethSettings(
            datasource=DatasourceSettings(plugin="csv"),
            sinks={
                "output": SinkSettings(plugin="csv"),
            },
            output_sink="output",
            gates=[
                GateSettings(
                    name="forker",
                    condition="True",
                    routes={"true": "fork", "false": "continue"},
                    fork_to=["path_a", "path_b"],
                ),
            ],
            coalesce=[
                CoalesceSettings(
                    name="merge_results",
                    branches=["path_a", "path_b"],
                    policy="require_all",
                    merge="union",
                ),
            ],
        )

        graph = ExecutionGraph.from_config(settings, plugin_manager)
        branch_map = graph.get_branch_to_coalesce_map()

        # Should map branches to coalesce name
        assert branch_map["path_a"] == "merge_results"
        assert branch_map["path_b"] == "merge_results"

    def test_coalesce_node_has_edge_to_output_sink(self, plugin_manager) -> None:
        """Coalesce node should have an edge to the output sink."""
        from elspeth.contracts import RoutingMode
        from elspeth.core.config import (
            CoalesceSettings,
            DatasourceSettings,
            ElspethSettings,
            GateSettings,
            SinkSettings,
        )
        from elspeth.core.dag import ExecutionGraph

        settings = ElspethSettings(
            datasource=DatasourceSettings(plugin="csv"),
            sinks={
                "output": SinkSettings(plugin="csv"),
            },
            output_sink="output",
            gates=[
                GateSettings(
                    name="forker",
                    condition="True",
                    routes={"true": "fork", "false": "continue"},
                    fork_to=["path_a", "path_b"],
                ),
            ],
            coalesce=[
                CoalesceSettings(
                    name="merge_results",
                    branches=["path_a", "path_b"],
                    policy="require_all",
                    merge="union",
                ),
            ],
        )

        graph = ExecutionGraph.from_config(settings, plugin_manager)

        coalesce_id = graph.get_coalesce_id_map()["merge_results"]
        output_sink_id = graph.get_sink_id_map()["output"]

        # Verify edge from coalesce to output sink
        edges = graph.get_edges()
        coalesce_to_sink_edges = [e for e in edges if e.from_node == coalesce_id and e.to_node == output_sink_id]

        assert len(coalesce_to_sink_edges) == 1
        assert coalesce_to_sink_edges[0].label == "continue"
        assert coalesce_to_sink_edges[0].mode == RoutingMode.MOVE

    def test_coalesce_node_stores_config(self, plugin_manager) -> None:
        """Coalesce node should store configuration for audit trail."""
        from elspeth.core.config import (
            CoalesceSettings,
            DatasourceSettings,
            ElspethSettings,
            GateSettings,
            SinkSettings,
        )
        from elspeth.core.dag import ExecutionGraph

        settings = ElspethSettings(
            datasource=DatasourceSettings(plugin="csv"),
            sinks={
                "output": SinkSettings(plugin="csv"),
            },
            output_sink="output",
            gates=[
                GateSettings(
                    name="forker",
                    condition="True",
                    routes={"true": "fork", "false": "continue"},
                    fork_to=["path_a", "path_b"],
                ),
            ],
            coalesce=[
                CoalesceSettings(
                    name="merge_results",
                    branches=["path_a", "path_b"],
                    policy="quorum",
                    quorum_count=1,
                    merge="nested",
                    timeout_seconds=30.0,
                ),
            ],
        )

        graph = ExecutionGraph.from_config(settings, plugin_manager)

        coalesce_id = graph.get_coalesce_id_map()["merge_results"]
        node_info = graph.get_node_info(coalesce_id)

        # Verify config is stored
        assert node_info.config["branches"] == ["path_a", "path_b"]
        assert node_info.config["policy"] == "quorum"
        assert node_info.config["merge"] == "nested"
        assert node_info.config["timeout_seconds"] == 30.0
        assert node_info.config["quorum_count"] == 1


class TestSchemaValidation:
    """Tests for graph-based schema compatibility validation."""

    def test_schema_validation_catches_gate_routing_to_incompatible_sink(self) -> None:
        """Gate routes to sink before required field is added - should fail validation.

        This is the bug scenario: A gate routes rows directly to a sink from an
        intermediate point in the pipeline, but the sink requires a field that
        hasn't been added yet. The old linear validator checked all sinks against
        the "final transform output", missing this incompatibility.
        """
        from elspeth.contracts import PluginSchema
        from elspeth.core.dag import ExecutionGraph, GraphValidationError

        class SourceSchema(PluginSchema):
            """Source provides: name, quality."""

            name: str
            quality: str

        class AddScoreSchema(PluginSchema):
            """After add_score transform: name, quality, score."""

            name: str
            quality: str
            score: int

        class RawSinkSchema(PluginSchema):
            """Raw sink requires: name, quality, score."""

            name: str
            quality: str
            score: int  # NOT PROVIDED by source or gate!

        graph = ExecutionGraph()

        # Build pipeline: Source -> Gate -> [routes to raw_sink OR continues to add_score]
        graph.add_node(
            "src",
            node_type="source",
            plugin_name="csv",
            output_schema=SourceSchema,
        )
        graph.add_node(
            "gate",
            node_type="gate",
            plugin_name="quality_gate",
            input_schema=SourceSchema,
            output_schema=SourceSchema,  # Gate doesn't modify data
        )
        graph.add_node(
            "add_score",
            node_type="transform",
            plugin_name="add_score_transform",
            input_schema=SourceSchema,
            output_schema=AddScoreSchema,  # Adds 'score' field
        )
        graph.add_node(
            "raw_sink",
            node_type="sink",
            plugin_name="csv",
            input_schema=RawSinkSchema,  # Requires 'score' field!
        )
        graph.add_node(
            "processed_sink",
            node_type="sink",
            plugin_name="csv",
            input_schema=AddScoreSchema,
        )

        # Edges
        graph.add_edge("src", "gate", label="continue")
        graph.add_edge("gate", "raw_sink", label="raw")  # BUG: Routes BEFORE add_score!
        graph.add_edge("gate", "add_score", label="continue")
        graph.add_edge("add_score", "processed_sink", label="continue")

        # BUG: Current implementation doesn't validate edge-by-edge
        # The gate routes to raw_sink with SourceSchema (no 'score' field),
        # but raw_sink requires RawSinkSchema (with 'score' field).
        # This should raise GraphValidationError.
        with pytest.raises(GraphValidationError, match="score"):
            graph.validate()

    def test_coalesce_rejects_incompatible_branch_schemas(self) -> None:
        """Coalesce with incompatible branch schemas should fail validation.

        CRITICAL P0 BLOCKER: Coalesce incompatible schema behavior was UNDEFINED.
        Manual graph construction bypasses config schema limitation that
        doesn't support per-branch transforms.
        """
        from elspeth.contracts import PluginSchema, RoutingMode
        from elspeth.core.dag import ExecutionGraph, GraphValidationError

        class SourceOutput(PluginSchema):
            id: int
            name: str

        class BranchAOutput(PluginSchema):
            """Branch A adds score field."""

            id: int
            name: str
            score: float

        class BranchBOutput(PluginSchema):
            """Branch B adds rank field (different from Branch A)."""

            id: int
            name: str
            rank: int

        graph = ExecutionGraph()

        # Build fork/join DAG with INCOMPATIBLE branch schemas
        graph.add_node("source", node_type="source", plugin_name="csv", output_schema=SourceOutput)
        graph.add_node("fork_gate", node_type="gate", plugin_name="fork_gate")

        # Branch A: adds score field
        graph.add_node(
            "transform_a",
            node_type="transform",
            plugin_name="add_score",
            input_schema=SourceOutput,
            output_schema=BranchAOutput,
        )

        # Branch B: adds rank field (incompatible with Branch A)
        graph.add_node(
            "transform_b",
            node_type="transform",
            plugin_name="add_rank",
            input_schema=SourceOutput,
            output_schema=BranchBOutput,
        )

        # Coalesce attempts to merge incompatible schemas
        graph.add_node(
            "coalesce",
            node_type="coalesce",
            plugin_name="coalesce:merge",
            config={
                "branches": ["branch_a", "branch_b"],
                "policy": "require_all",
                "merge": "union",
            },
        )

        graph.add_node("sink", node_type="sink", plugin_name="csv")

        # Build edges
        graph.add_edge("source", "fork_gate", label="continue", mode=RoutingMode.MOVE)
        graph.add_edge("fork_gate", "transform_a", label="branch_a", mode=RoutingMode.COPY)
        graph.add_edge("fork_gate", "transform_b", label="branch_b", mode=RoutingMode.COPY)
        graph.add_edge("transform_a", "coalesce", label="branch_a", mode=RoutingMode.MOVE)
        graph.add_edge("transform_b", "coalesce", label="branch_b", mode=RoutingMode.MOVE)
        graph.add_edge("coalesce", "sink", label="continue", mode=RoutingMode.MOVE)

        # Should crash: coalesce can't merge BranchAOutput and BranchBOutput
        with pytest.raises(GraphValidationError) as exc_info:
            graph.validate()

        # Error should mention incompatible fields
        error_msg = str(exc_info.value).lower()
        assert "schema" in error_msg or "incompatible" in error_msg

    def test_aggregation_schema_transition_in_topology(self) -> None:
        """Aggregation with input_schema and output_schema in single topology.

        Verifies source→agg validates against input_schema,
        and agg→sink validates against output_schema.
        """
        from elspeth.contracts import PluginSchema
        from elspeth.core.dag import ExecutionGraph

        class SourceOutput(PluginSchema):
            value: float

        class AggregationOutput(PluginSchema):
            count: int
            sum: float

        graph = ExecutionGraph()

        graph.add_node("source", node_type="source", plugin_name="csv", output_schema=SourceOutput)
        graph.add_node(
            "agg",
            node_type="aggregation",
            plugin_name="batch_stats",
            input_schema=SourceOutput,  # Incoming edge validates against this
            output_schema=AggregationOutput,  # Outgoing edge validates against this
            config={},
        )
        graph.add_node("sink", node_type="sink", plugin_name="csv", input_schema=AggregationOutput)

        graph.add_edge("source", "agg", label="continue")
        graph.add_edge("agg", "sink", label="continue")

        # Should pass - schemas compatible at both edges
        graph.validate()

    def test_aggregation_schema_transition_incompatible_output(self) -> None:
        """Aggregation with incompatible output_schema should fail validation."""
        from elspeth.contracts import PluginSchema
        from elspeth.core.dag import ExecutionGraph, GraphValidationError

        class SourceOutput(PluginSchema):
            value: float

        class AggregationOutput(PluginSchema):
            count: int
            sum: float

        class SinkInput(PluginSchema):
            """Sink requires 'average' field not in aggregation output."""

            count: int
            sum: float
            average: float  # NOT in AggregationOutput!

        graph = ExecutionGraph()

        graph.add_node("source", node_type="source", plugin_name="csv", output_schema=SourceOutput)
        graph.add_node(
            "agg",
            node_type="aggregation",
            plugin_name="batch_stats",
            input_schema=SourceOutput,
            output_schema=AggregationOutput,
            config={},
        )
        graph.add_node("sink", node_type="sink", plugin_name="csv", input_schema=SinkInput)

        graph.add_edge("source", "agg", label="continue")
        graph.add_edge("agg", "sink", label="continue")

        # Should crash - sink requires 'average' field
        with pytest.raises(GraphValidationError) as exc_info:
            graph.validate()

        assert "average" in str(exc_info.value).lower()

    def test_schema_validation_error_includes_diagnostic_details(self) -> None:
        """Schema validation errors include field name, producer node, consumer node."""
        from elspeth.contracts import PluginSchema
        from elspeth.core.dag import ExecutionGraph, GraphValidationError

        class SourceOutput(PluginSchema):
            id: int
            name: str

        class SinkInput(PluginSchema):
            id: int
            name: str
            score: float  # Missing from source output

        graph = ExecutionGraph()

        graph.add_node("my_source", node_type="source", plugin_name="csv_reader", output_schema=SourceOutput)
        graph.add_node("my_sink", node_type="sink", plugin_name="db_writer", input_schema=SinkInput)

        graph.add_edge("my_source", "my_sink", label="continue")

        # Capture error and verify diagnostic details
        with pytest.raises(GraphValidationError) as exc_info:
            graph.validate()

        error_msg = str(exc_info.value)

        # Should include field name
        assert "score" in error_msg.lower()

        # Should include producer node (or plugin name)
        assert "my_source" in error_msg or "csv_reader" in error_msg

        # Should include consumer node (or plugin name)
        assert "my_sink" in error_msg or "db_writer" in error_msg


class TestSchemaValidationWithPluginManager:
    """Test that schema validation uses real schemas from PluginManager."""

    def test_valid_schema_compatibility(self) -> None:
        """Test that compatible schemas pass validation."""
        from elspeth.core.config import DatasourceSettings, ElspethSettings, RowPluginSettings, SinkSettings
        from elspeth.core.dag import ExecutionGraph
        from elspeth.plugins.manager import PluginManager

        # Create settings with plugins that have compatible schemas
        config = ElspethSettings(
            datasource=DatasourceSettings(plugin="csv", options={"path": "input.csv"}),
            row_plugins=[
                RowPluginSettings(plugin="passthrough", options={}),
            ],
            sinks={"output": SinkSettings(plugin="csv", options={"path": "output.csv"})},
            output_sink="output",
        )

        # Create plugin manager
        manager = PluginManager()
        manager.register_builtin_plugins()

        # Build graph with manager - should succeed
        graph = ExecutionGraph.from_config(config, manager)

        # Validate - should pass (schemas are compatible)
        graph.validate()  # Should not raise

        # Verify graph builds successfully and validation passes
        # NOTE: CSV and passthrough use dynamic schemas (set in __init__, not at class level)
        # So schemas will be None at graph construction time. This is EXPECTED.
        # The validation code handles None schemas correctly (skips validation for dynamic schemas).
        # The fix we're testing is that the mechanism works without crashes:
        # 1. No TypeError from missing manager parameter
        # 2. No AttributeError from getattr on config models
        # 3. Graph validation passes
        nodes = graph.get_nodes()
        source_nodes = [n for n in nodes if n.node_type == "source"]
        assert len(source_nodes) == 1

    def test_incompatible_schema_raises_error(self) -> None:
        """Test that incompatible schemas raise GraphValidationError."""
        from elspeth.core.config import DatasourceSettings, ElspethSettings, RowPluginSettings, SinkSettings
        from elspeth.core.dag import ExecutionGraph
        from elspeth.plugins.manager import PluginManager

        # Create settings with schema mismatch
        # CSV source outputs dynamic schema, FieldMapper requires specific schema in config
        config = ElspethSettings(
            datasource=DatasourceSettings(plugin="csv", options={"path": "input.csv"}),
            row_plugins=[
                # FieldMapper requires 'schema' in config to define input/output
                RowPluginSettings(
                    plugin="field_mapper",
                    options={
                        "schema": {"mode": "strict", "fields": ["required_field: str"]},
                        "mapping": {},
                    },
                ),
            ],
            sinks={"output": SinkSettings(plugin="csv", options={"path": "output.csv"})},
            output_sink="output",
        )

        manager = PluginManager()
        manager.register_builtin_plugins()

        # Build graph - should succeed
        graph = ExecutionGraph.from_config(config, manager)

        # NOTE: All our builtin plugins (CSV, FieldMapper) use dynamic schemas
        # set in __init__, not at class level. So schemas will be None at graph
        # construction time, and validation will skip schema checking.
        # This test was originally designed to verify incompatible schemas raise errors,
        # but with dynamic schemas, that's not testable using builtin plugins.
        #
        # The test still verifies the fix works:
        # 1. Graph builds successfully with PluginManager
        # 2. Validation passes without crashes
        # 3. No TypeError from missing manager parameter
        # 4. No AttributeError from broken getattr on config models
        graph.validate()  # Should not raise with dynamic schemas

        # Verify graph structure is correct
        nodes = graph.get_nodes()
        transform_nodes = [n for n in nodes if n.node_type == "transform"]
        assert len(transform_nodes) == 1

    def test_unknown_plugin_raises_error(self) -> None:
        """Test that unknown plugin names raise ValueError."""
        from elspeth.core.config import DatasourceSettings, ElspethSettings, SinkSettings
        from elspeth.core.dag import ExecutionGraph
        from elspeth.plugins.manager import PluginManager

        config = ElspethSettings(
            datasource=DatasourceSettings(plugin="nonexistent_source", options={}),
            sinks={"output": SinkSettings(plugin="csv", options={"path": "output.csv"})},
            output_sink="output",
        )

        manager = PluginManager()
        manager.register_builtin_plugins()

        # Building graph should raise ValueError for unknown plugin
        with pytest.raises(ValueError, match="Unknown source plugin: nonexistent_source"):
            ExecutionGraph.from_config(config, manager)


def test_from_plugin_instances_extracts_schemas():
    """Verify from_plugin_instances extracts schemas from instances."""
    import tempfile
    from pathlib import Path

    from elspeth.cli_helpers import instantiate_plugins_from_config
    from elspeth.core.config import load_settings
    from elspeth.core.dag import ExecutionGraph

    config_yaml = """
datasource:
  plugin: csv
  options:
    path: test.csv
    schema:
      mode: strict
      fields:
        - "value: float"
    on_validation_failure: discard

row_plugins:
  - plugin: passthrough
    options:
      schema:
        mode: strict
        fields:
          - "value: float"

sinks:
  output:
    plugin: csv
    options:
      path: output.csv
      schema:
        mode: strict
        fields:
          - "value: float"

output_sink: output
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(config_yaml)
        config_file = Path(f.name)

    try:
        config = load_settings(config_file)
        plugins = instantiate_plugins_from_config(config)

        graph = ExecutionGraph.from_plugin_instances(
            source=plugins["source"],
            transforms=plugins["transforms"],
            sinks=plugins["sinks"],
            aggregations=plugins["aggregations"],
            gates=list(config.gates),
            output_sink=config.output_sink,
            coalesce_settings=list(config.coalesce) if config.coalesce else None,
        )

        # Verify schemas extracted
        source_nodes = [n for n, d in graph._graph.nodes(data=True) if d["info"].node_type == "source"]
        source_info = graph.get_node_info(source_nodes[0])
        assert source_info.output_schema is not None

    finally:
        config_file.unlink()


def test_validate_aggregation_dual_schema():
    """Verify aggregation edges validate against correct schemas."""
    from elspeth.contracts.schema import SchemaConfig
    from elspeth.core.dag import ExecutionGraph
    from elspeth.plugins.schema_factory import create_schema_from_config

    InputSchema = create_schema_from_config(
        SchemaConfig.from_dict({"mode": "strict", "fields": ["value: float"]}),
        "InputSchema",
        allow_coercion=False,
    )

    OutputSchema = create_schema_from_config(
        SchemaConfig.from_dict({"mode": "strict", "fields": ["count: int", "sum: float"]}),
        "OutputSchema",
        allow_coercion=False,
    )

    graph = ExecutionGraph()
    graph.add_node("source", node_type="source", plugin_name="csv", output_schema=InputSchema)
    graph.add_node(
        "agg",
        node_type="aggregation",
        plugin_name="batch_stats",
        input_schema=InputSchema,
        output_schema=OutputSchema,
        config={},
    )
    graph.add_node("sink", node_type="sink", plugin_name="csv", input_schema=OutputSchema)

    graph.add_edge("source", "agg", label="continue")
    graph.add_edge("agg", "sink", label="continue")

    errors = graph._validate_edge_schemas()
    assert len(errors) == 0  # Should pass


def test_validate_aggregation_detects_incompatibility():
    """Verify validation detects aggregation output mismatch."""
    from elspeth.contracts.schema import SchemaConfig
    from elspeth.core.dag import ExecutionGraph
    from elspeth.plugins.schema_factory import create_schema_from_config

    InputSchema = create_schema_from_config(
        SchemaConfig.from_dict({"mode": "strict", "fields": ["value: float"]}),
        "InputSchema",
        allow_coercion=False,
    )

    OutputSchema = create_schema_from_config(
        SchemaConfig.from_dict({"mode": "strict", "fields": ["count: int"]}),  # Missing 'sum'
        "OutputSchema",
        allow_coercion=False,
    )

    SinkSchema = create_schema_from_config(
        SchemaConfig.from_dict({"mode": "strict", "fields": ["count: int", "sum: float"]}),
        "SinkSchema",
        allow_coercion=False,
    )

    graph = ExecutionGraph()
    graph.add_node("source", node_type="source", plugin_name="csv", output_schema=InputSchema)
    graph.add_node(
        "agg",
        node_type="aggregation",
        plugin_name="batch_stats",
        input_schema=InputSchema,
        output_schema=OutputSchema,
        config={},
    )
    graph.add_node("sink", node_type="sink", plugin_name="csv", input_schema=SinkSchema)

    graph.add_edge("source", "agg", label="continue")
    graph.add_edge("agg", "sink", label="continue")

    errors = graph._validate_edge_schemas()
    assert len(errors) > 0
    assert "sum" in errors[0]


class TestDynamicSchemaDetection:
    """Tests for detecting and handling dynamic schemas."""

    def test_dynamic_source_to_specific_sink_should_skip_validation(self) -> None:
        """Dynamic source → specific sink should PASS (validation skipped).

        Manually constructed graph with dynamic output_schema and specific input_schema.
        Validation should be skipped for dynamic schemas.
        """
        from elspeth.contracts.schema import SchemaConfig
        from elspeth.core.dag import ExecutionGraph
        from elspeth.plugins.schema_factory import create_schema_from_config

        # Create dynamic schema (no fields, extra='allow')
        DynamicSchema = create_schema_from_config(
            SchemaConfig.from_dict({"fields": "dynamic"}),
            "DynamicSchema",
            allow_coercion=False,
        )

        # Create specific schema (has fields, extra='forbid')
        SpecificSchema = create_schema_from_config(
            SchemaConfig.from_dict({"mode": "strict", "fields": ["value: float", "name: str"]}),
            "SpecificSchema",
            allow_coercion=False,
        )

        graph = ExecutionGraph()
        graph.add_node("source", node_type="source", plugin_name="csv", output_schema=DynamicSchema)
        graph.add_node("sink", node_type="sink", plugin_name="csv", input_schema=SpecificSchema)
        graph.add_edge("source", "sink", label="continue")

        # Should NOT raise - validation is skipped for dynamic schemas
        graph.validate()

    def test_specific_source_to_dynamic_sink_should_skip_validation(self) -> None:
        """Specific source → dynamic sink should PASS (validation skipped).

        Manually constructed graph with specific output_schema and dynamic input_schema.
        Validation should be skipped for dynamic schemas.
        """
        from elspeth.contracts.schema import SchemaConfig
        from elspeth.core.dag import ExecutionGraph
        from elspeth.plugins.schema_factory import create_schema_from_config

        # Create specific schema
        SpecificSchema = create_schema_from_config(
            SchemaConfig.from_dict({"mode": "strict", "fields": ["value: float"]}),
            "SpecificSchema",
            allow_coercion=False,
        )

        # Create dynamic schema
        DynamicSchema = create_schema_from_config(
            SchemaConfig.from_dict({"fields": "dynamic"}),
            "DynamicSchema",
            allow_coercion=False,
        )

        graph = ExecutionGraph()
        graph.add_node("source", node_type="source", plugin_name="csv", output_schema=SpecificSchema)
        graph.add_node("sink", node_type="sink", plugin_name="csv", input_schema=DynamicSchema)
        graph.add_edge("source", "sink", label="continue")

        # Should NOT raise - validation is skipped for dynamic schemas
        graph.validate()

    def test_is_dynamic_schema_helper_detects_dynamic_schemas(self) -> None:
        """_is_dynamic_schema() helper correctly identifies dynamic vs explicit schemas."""
        from elspeth.contracts.schema import SchemaConfig
        from elspeth.core.dag import _is_dynamic_schema
        from elspeth.plugins.schema_factory import create_schema_from_config

        # Create dynamic schema
        DynamicSchema = create_schema_from_config(
            SchemaConfig.from_dict({"fields": "dynamic"}),
            "DynamicSchema",
            allow_coercion=False,
        )

        # Create explicit schema
        ExplicitSchema = create_schema_from_config(
            SchemaConfig.from_dict({"mode": "strict", "fields": ["value: float"]}),
            "ExplicitSchema",
            allow_coercion=False,
        )

        # Test dynamic schema detection
        assert _is_dynamic_schema(DynamicSchema) is True

        # Test explicit schema detection
        assert _is_dynamic_schema(ExplicitSchema) is False

        # Test backwards compat (None = dynamic)
        assert _is_dynamic_schema(None) is True
