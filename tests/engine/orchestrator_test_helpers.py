# tests/engine/orchestrator_test_helpers.py
"""Shared helpers for orchestrator tests.

Extracted from test_orchestrator.py to support split test modules.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from elspeth.contracts import RoutingMode
from elspeth.plugins.base import BaseGate

if TYPE_CHECKING:
    from elspeth.core.dag import ExecutionGraph
    from elspeth.engine.orchestrator import PipelineConfig


def build_test_graph(config: PipelineConfig) -> ExecutionGraph:
    """Build a simple graph for testing (temporary until from_config is wired).

    Creates a linear graph matching the PipelineConfig structure:
    source -> transforms... -> config gates... -> sinks

    For gates, creates additional edges to all sinks (gates can route anywhere).
    Route labels use sink names for simplicity in tests.
    """
    from elspeth.core.dag import ExecutionGraph

    graph = ExecutionGraph()

    # Add source
    graph.add_node("source", node_type="source", plugin_name=config.source.name)

    # Add transforms and populate transform_id_map
    transform_ids: dict[int, str] = {}
    prev = "source"
    for i, t in enumerate(config.transforms):
        node_id = f"transform_{i}"
        transform_ids[i] = node_id
        is_gate = isinstance(t, BaseGate)
        graph.add_node(
            node_id,
            node_type="gate" if is_gate else "transform",
            plugin_name=t.name,
        )
        graph.add_edge(prev, node_id, label="continue", mode=RoutingMode.MOVE)
        prev = node_id

    # Add sinks first (need sink_ids for gate routing)
    sink_ids: dict[str, str] = {}
    for sink_name, sink in config.sinks.items():
        node_id = f"sink_{sink_name}"
        sink_ids[sink_name] = node_id
        graph.add_node(node_id, node_type="sink", plugin_name=sink.name)

    # Populate route resolution map: (gate_id, label) -> sink_name
    route_resolution_map: dict[tuple[str, str], str] = {}

    # Handle plugin-based gates in transforms
    for i, t in enumerate(config.transforms):
        if isinstance(t, BaseGate):  # It's a gate
            gate_id = f"transform_{i}"
            for sink_name in sink_ids:
                route_resolution_map[(gate_id, sink_name)] = sink_name

    # Add config-driven gates (from config.gates)
    config_gate_ids: dict[str, str] = {}
    for gate_config in config.gates:
        gate_id = f"config_gate_{gate_config.name}"
        config_gate_ids[gate_config.name] = gate_id

        # Store condition in node config for audit trail
        gate_node_config = {
            "condition": gate_config.condition,
            "routes": dict(gate_config.routes),
        }
        if gate_config.fork_to:
            gate_node_config["fork_to"] = list(gate_config.fork_to)

        graph.add_node(
            gate_id,
            node_type="gate",
            plugin_name=f"config_gate:{gate_config.name}",
            config=gate_node_config,
        )

        # Edge from previous node
        graph.add_edge(prev, gate_id, label="continue", mode=RoutingMode.MOVE)

        # Config gate routes to sinks
        for route_label, target in gate_config.routes.items():
            route_resolution_map[(gate_id, route_label)] = target

            if target == "continue":
                continue  # Not a sink route - no edge to create
            if target in sink_ids:
                graph.add_edge(gate_id, sink_ids[target], label=route_label, mode=RoutingMode.MOVE)

        prev = gate_id

    # Add edges from transforms to sinks (for plugin-based gates and linear flow)
    for sink_name in sink_ids:
        node_id = sink_ids[sink_name]
        # Gates can route to any sink
        for i, t in enumerate(config.transforms):
            if isinstance(t, BaseGate):
                gate_id = f"transform_{i}"
                graph.add_edge(gate_id, node_id, label=sink_name, mode=RoutingMode.MOVE)

    # Edge from last node to output sink
    if "default" in sink_ids:
        output_sink = "default"
    elif sink_ids:
        output_sink = next(iter(sink_ids))
    else:
        output_sink = ""

    if output_sink:
        graph.add_edge(prev, sink_ids[output_sink], label="continue", mode=RoutingMode.MOVE)

    # Populate internal ID maps
    graph._sink_id_map = sink_ids
    graph._transform_id_map = transform_ids
    graph._config_gate_id_map = config_gate_ids
    graph._route_resolution_map = route_resolution_map
    graph._output_sink = output_sink

    return graph


def build_fork_test_graph(
    config: PipelineConfig,
    fork_paths: dict[int, list[str]],  # transform_index -> list of fork path names
) -> ExecutionGraph:
    """Build a test graph that supports fork operations.

    Args:
        config: Pipeline configuration
        fork_paths: Maps transform index to list of fork path names
                   e.g., {0: ["path_a", "path_b"]} means transform_0 forks to those paths
    """
    from elspeth.core.dag import ExecutionGraph

    graph = ExecutionGraph()

    # Add source
    graph.add_node("source", node_type="source", plugin_name=config.source.name)

    # Add transforms
    transform_ids: dict[int, str] = {}
    prev = "source"
    for i, t in enumerate(config.transforms):
        node_id = f"transform_{i}"
        transform_ids[i] = node_id
        is_gate = isinstance(t, BaseGate)
        graph.add_node(
            node_id,
            node_type="gate" if is_gate else "transform",
            plugin_name=t.name,
        )
        graph.add_edge(prev, node_id, label="continue", mode=RoutingMode.MOVE)
        prev = node_id

    # Add sinks
    sink_ids: dict[str, str] = {}
    for sink_name, sink in config.sinks.items():
        node_id = f"sink_{sink_name}"
        sink_ids[sink_name] = node_id
        graph.add_node(node_id, node_type="sink", plugin_name=sink.name)

    # Add edge from last transform to default sink
    if "default" in sink_ids:
        graph.add_edge(prev, sink_ids["default"], label="continue", mode=RoutingMode.MOVE)

    # Populate internal maps
    graph._sink_id_map = sink_ids
    graph._transform_id_map = transform_ids
    graph._output_sink = "default" if "default" in sink_ids else next(iter(sink_ids))

    # Build route resolution map with fork support
    route_resolution_map: dict[tuple[str, str], str] = {}
    for i, paths in fork_paths.items():
        gate_id = f"transform_{i}"
        for path_name in paths:
            # Fork paths resolve to "fork" (special handling in executor)
            route_resolution_map[(gate_id, path_name)] = "fork"
            # Add edge for each fork path (needed for edge_map lookup)
            # Fork paths go to the NEXT transform (or sink if last)
            next_node = f"transform_{i + 1}" if i + 1 < len(config.transforms) else sink_ids["default"]
            graph.add_edge(gate_id, next_node, label=path_name, mode=RoutingMode.COPY)

    graph._route_resolution_map = route_resolution_map

    return graph
