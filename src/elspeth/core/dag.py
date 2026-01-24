# src/elspeth/core/dag.py
"""DAG (Directed Acyclic Graph) operations for execution planning.

Uses NetworkX for graph operations including:
- Acyclicity validation
- Topological sorting
- Path finding for lineage queries
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast

import networkx as nx
from networkx import MultiDiGraph

from elspeth.contracts import EdgeInfo, RoutingMode

if TYPE_CHECKING:
    from elspeth.contracts import PluginSchema
    from elspeth.core.config import ElspethSettings, GateSettings


class GraphValidationError(Exception):
    """Raised when graph validation fails."""

    pass


@dataclass
class NodeInfo:
    """Information about a node in the execution graph.

    Schemas are immutable after graph construction. Even dynamic schemas
    (determined by data inspection) are locked at launch and never change
    during the run. This guarantees audit trail consistency.
    """

    node_id: str
    node_type: str  # source, transform, gate, aggregation, coalesce, sink
    plugin_name: str
    config: dict[str, Any] = field(default_factory=dict)
    input_schema: type[PluginSchema] | None = None  # Immutable after graph construction
    output_schema: type[PluginSchema] | None = None  # Immutable after graph construction


def _get_missing_required_fields(
    producer: type[PluginSchema],
    consumer: type[PluginSchema],
) -> set[str]:
    """Get required fields in consumer that are missing from producer.

    Args:
        producer: Schema that produces data
        consumer: Schema that consumes data

    Returns:
        Set of field names that are required by consumer but not in producer
    """
    producer_fields = set(producer.model_fields.keys())
    required_fields = {name for name, field in consumer.model_fields.items() if field.is_required()}
    return required_fields - producer_fields


class ExecutionGraph:
    """Execution graph for pipeline configuration.

    Wraps NetworkX MultiDiGraph with domain-specific operations.
    Uses MultiDiGraph to support multiple edges between the same node pair
    (e.g., fork gates routing multiple labels to the same sink).
    """

    def __init__(self) -> None:
        self._graph: MultiDiGraph[str] = nx.MultiDiGraph()
        self._sink_id_map: dict[str, str] = {}
        self._transform_id_map: dict[int, str] = {}
        self._config_gate_id_map: dict[str, str] = {}  # gate_name -> node_id
        self._aggregation_id_map: dict[str, str] = {}  # agg_name -> node_id
        self._coalesce_id_map: dict[str, str] = {}  # coalesce_name -> node_id
        self._branch_to_coalesce: dict[str, str] = {}  # branch_name -> coalesce_name
        self._output_sink: str = ""
        self._route_label_map: dict[tuple[str, str], str] = {}  # (gate_node, sink_name) -> route_label
        self._route_resolution_map: dict[tuple[str, str], str] = {}  # (gate_node, label) -> sink_name | "continue"

    @property
    def node_count(self) -> int:
        """Number of nodes in the graph."""
        return self._graph.number_of_nodes()

    @property
    def edge_count(self) -> int:
        """Number of edges in the graph."""
        return self._graph.number_of_edges()

    def has_node(self, node_id: str) -> bool:
        """Check if node exists."""
        return self._graph.has_node(node_id)

    def add_node(
        self,
        node_id: str,
        *,
        node_type: str,
        plugin_name: str,
        config: dict[str, Any] | None = None,
        input_schema: type[PluginSchema] | None = None,
        output_schema: type[PluginSchema] | None = None,
    ) -> None:
        """Add a node to the execution graph.

        Args:
            node_id: Unique node identifier
            node_type: One of: source, transform, gate, aggregation, coalesce, sink
            plugin_name: Plugin identifier
            config: Node configuration
            input_schema: Input schema (None for dynamic or N/A like sources)
            output_schema: Output schema (None for dynamic or N/A like sinks)
        """
        info = NodeInfo(
            node_id=node_id,
            node_type=node_type,
            plugin_name=plugin_name,
            config=config or {},
            input_schema=input_schema,
            output_schema=output_schema,
        )
        self._graph.add_node(node_id, info=info)

    def add_edge(
        self,
        from_node: str,
        to_node: str,
        *,
        label: str,
        mode: RoutingMode = RoutingMode.MOVE,
    ) -> None:
        """Add an edge between nodes.

        Args:
            from_node: Source node ID
            to_node: Target node ID
            label: Edge label (e.g., "continue", "suspicious") - also used as edge key
            mode: Routing mode (MOVE or COPY)
        """
        # Use label as key to allow multiple edges between same nodes
        self._graph.add_edge(from_node, to_node, key=label, label=label, mode=mode)

    def is_acyclic(self) -> bool:
        """Check if the graph is acyclic (a valid DAG)."""
        return nx.is_directed_acyclic_graph(self._graph)

    def validate(self) -> None:
        """Validate the execution graph.

        Validates:
        1. Graph is acyclic (no cycles)
        2. Exactly one source node exists
        3. At least one sink node exists
        4. Edge labels are unique per source node
        5. Schema compatibility across all edges

        Raises:
            GraphValidationError: If validation fails
        """
        # Check for cycles
        if not self.is_acyclic():
            try:
                cycle = nx.find_cycle(self._graph)
                # MultiDiGraph returns (u, v, key) tuples; extract just u for display
                cycle_str = " -> ".join(f"{edge[0]}" for edge in cycle)
                raise GraphValidationError(f"Graph contains a cycle: {cycle_str}")
            except nx.NetworkXNoCycle:
                raise GraphValidationError("Graph contains a cycle") from None

        # Check for exactly one source
        # All nodes have "info" - added via add_node(), direct access is safe
        sources = [node_id for node_id, data in self._graph.nodes(data=True) if data["info"].node_type == "source"]
        if len(sources) != 1:
            raise GraphValidationError(f"Graph must have exactly one source, found {len(sources)}")

        # Check for at least one sink
        sinks = self.get_sinks()
        if len(sinks) < 1:
            raise GraphValidationError("Graph must have at least one sink")

        # Check outgoing edge labels are unique per node.
        # The orchestrator's edge_map keys by (from_node, label), so duplicate
        # labels from the same node would cause silent overwrites, leading to
        # routing events recorded against the wrong edge (audit corruption).
        for node_id in self._graph.nodes():
            labels_seen: set[str] = set()
            # out_edges returns (from, to, key) for MultiDiGraph
            for _, _, edge_key in self._graph.out_edges(node_id, keys=True):
                if edge_key in labels_seen:
                    raise GraphValidationError(
                        f"Node '{node_id}' has duplicate outgoing edge label '{edge_key}'. "
                        "Edge labels must be unique per source node to ensure correct "
                        "routing event recording."
                    )
                labels_seen.add(edge_key)

        # Check schema compatibility across all edges
        schema_errors = self._validate_edge_schemas()
        if schema_errors:
            raise GraphValidationError("Schema incompatibilities:\n" + "\n".join(f"  - {e}" for e in schema_errors))

    def _validate_edge_schemas(self) -> list[str]:
        """Validate schema compatibility along all edges.

        For each edge (producer -> consumer):
        - Get producer's output_schema
        - Get consumer's input_schema
        - Check producer provides all required fields

        Skips validation if either side is None (dynamic schema).
        Dynamic schemas are immutable after evaluation at launch.

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        for edge in self.get_edges():
            from_info = self.get_node_info(edge.from_node)
            to_info = self.get_node_info(edge.to_node)

            # Skip if either side has dynamic schema
            if from_info.output_schema is None or to_info.input_schema is None:
                continue

            missing = _get_missing_required_fields(
                producer=from_info.output_schema,
                consumer=to_info.input_schema,
            )

            if missing:
                errors.append(
                    f"{from_info.plugin_name} -> {to_info.plugin_name} (route: {edge.label}): producer missing required fields {missing}"
                )

        return errors

    def _get_effective_producer_schema(self, node_id: str) -> type[PluginSchema] | None:
        """Get effective output schema for a node, walking through pass-through nodes.

        Gates and other pass-through nodes don't transform data - they inherit
        schema from their upstream producers. This method walks backwards through
        the graph to find the nearest schema-carrying producer.

        For gates with multiple incoming edges, all inputs must have compatible
        schemas (crashes if not - this is a graph construction bug).

        Args:
            node_id: Node to get effective schema for

        Returns:
            Output schema type, or None if node has no schema and no upstream producers

        Raises:
            GraphValidationError: If gate has no incoming edges or multiple inputs
                with incompatible schemas (graph construction bug)
        """
        node_info = self.get_node_info(node_id)

        # If node has output_schema, return it directly
        if node_info.output_schema is not None:
            return node_info.output_schema

        # Node has no schema - check if it's a pass-through type
        if node_info.node_type == "gate":
            # Gate passes data unchanged - inherit from upstream producer
            incoming = self.get_incoming_edges(node_id)

            if not incoming:
                # Gate with no inputs is a graph construction bug - CRASH
                raise GraphValidationError(f"Gate node '{node_id}' has no incoming edges - this indicates a bug in graph construction")

            # Get effective schema from first input
            first_schema = self._get_effective_producer_schema(incoming[0].from_node)

            # For multi-input gates, verify all inputs have same schema
            if len(incoming) > 1:
                for edge in incoming[1:]:
                    other_schema = self._get_effective_producer_schema(edge.from_node)
                    if first_schema != other_schema:
                        # Multi-input gates with incompatible schemas - CRASH
                        raise GraphValidationError(
                            f"Gate '{node_id}' receives incompatible schemas from "
                            f"multiple inputs - this is a graph construction bug. "
                            f"First input schema: {first_schema}, "
                            f"Other input schema: {other_schema}"
                        )

            return first_schema

        # Not a pass-through type and no schema - return None
        return None

    def topological_order(self) -> list[str]:
        """Return nodes in topological order.

        Returns:
            List of node IDs in execution order

        Raises:
            GraphValidationError: If graph has cycles
        """
        try:
            return list(nx.topological_sort(self._graph))
        except nx.NetworkXUnfeasible as e:
            raise GraphValidationError(f"Cannot sort graph: {e}") from e

    def get_source(self) -> str | None:
        """Get the source node ID.

        Returns:
            The source node ID, or None if not exactly one source exists.
        """
        # All nodes have "info" - added via add_node(), direct access is safe
        sources = [node_id for node_id, data in self._graph.nodes(data=True) if data["info"].node_type == "source"]
        return sources[0] if len(sources) == 1 else None

    def get_sinks(self) -> list[str]:
        """Get all sink node IDs.

        Returns:
            List of sink node IDs.
        """
        # All nodes have "info" - added via add_node(), direct access is safe
        return [node_id for node_id, data in self._graph.nodes(data=True) if data["info"].node_type == "sink"]

    def get_node_info(self, node_id: str) -> NodeInfo:
        """Get NodeInfo for a node.

        Args:
            node_id: The node ID

        Returns:
            NodeInfo for the node

        Raises:
            KeyError: If node doesn't exist
        """
        if not self._graph.has_node(node_id):
            raise KeyError(f"Node not found: {node_id}")
        return cast(NodeInfo, self._graph.nodes[node_id]["info"])

    def get_edges(self) -> list[EdgeInfo]:
        """Get all edges with their data as typed EdgeInfo.

        Returns:
            List of EdgeInfo contracts (not tuples)
        """
        # Note: _key is unused but required for MultiDiGraph iteration signature
        return [
            EdgeInfo(
                from_node=u,
                to_node=v,
                label=data["label"],
                mode=data["mode"],  # Already RoutingMode after add_edge change
            )
            for u, v, _key, data in self._graph.edges(data=True, keys=True)
        ]

    def get_incoming_edges(self, node_id: str) -> list[EdgeInfo]:
        """Get all edges pointing TO this node.

        Args:
            node_id: The target node ID

        Returns:
            List of EdgeInfo for edges where to_node == node_id
        """
        # NetworkX in_edges returns (from, to, key) tuples for MultiDiGraph
        return [
            EdgeInfo(
                from_node=u,
                to_node=v,
                label=data["label"],
                mode=data["mode"],
            )
            for u, v, _key, data in self._graph.in_edges(node_id, data=True, keys=True)
        ]

    @classmethod
    def from_config(cls, config: ElspethSettings) -> ExecutionGraph:
        """Build an ExecutionGraph from validated settings.

        Creates nodes for:
        - Source (from config.datasource)
        - Transforms (from config.row_plugins, in order)
        - Sinks (from config.sinks)

        Creates edges for:
        - Linear flow: source -> transforms -> output_sink
        - Gate routes: gate -> routed_sink

        Raises:
            GraphValidationError: If gate routes reference unknown sinks
        """
        import uuid

        graph = cls()

        def node_id(prefix: str, name: str) -> str:
            return f"{prefix}_{name}_{uuid.uuid4().hex[:8]}"

        # Add source node
        source_id = node_id("source", config.datasource.plugin)
        graph.add_node(
            source_id,
            node_type="source",
            plugin_name=config.datasource.plugin,
            config=config.datasource.options,
            output_schema=getattr(config.datasource, "output_schema", None),
        )

        # Add sink nodes
        sink_ids: dict[str, str] = {}
        for sink_name, sink_config in config.sinks.items():
            sid = node_id("sink", sink_name)
            sink_ids[sink_name] = sid
            graph.add_node(
                sid,
                node_type="sink",
                plugin_name=sink_config.plugin,
                config=sink_config.options,
                input_schema=getattr(sink_config, "input_schema", None),
            )

        # Store explicit mapping for get_sink_id_map() - NO substring matching
        graph._sink_id_map = dict(sink_ids)

        # Build transform chain
        # Note: Gate routing is now config-driven only (see gates section below).
        # Plugin-based gates were removed - row_plugins are all transforms now.
        transform_ids: dict[int, str] = {}
        prev_node_id = source_id
        for i, plugin_config in enumerate(config.row_plugins):
            tid = node_id("transform", plugin_config.plugin)

            # Track sequence -> node_id
            transform_ids[i] = tid

            graph.add_node(
                tid,
                node_type="transform",
                plugin_name=plugin_config.plugin,
                config=plugin_config.options,
                input_schema=getattr(plugin_config, "input_schema", None),
                output_schema=getattr(plugin_config, "output_schema", None),
            )

            # Edge from previous node
            graph.add_edge(prev_node_id, tid, label="continue", mode=RoutingMode.MOVE)

            prev_node_id = tid

        # Store explicit mapping for get_transform_id_map()
        graph._transform_id_map = transform_ids

        # Build aggregation transform nodes (processed AFTER row_plugins, BEFORE gates)
        # Aggregation uses batch-aware transforms. The engine buffers rows and calls
        # transform.process(rows: list[dict]) when the trigger fires.
        aggregation_ids: dict[str, str] = {}
        for agg_config in config.aggregations:
            aid = node_id("aggregation", agg_config.name)
            aggregation_ids[agg_config.name] = aid

            # Store trigger config in node for audit trail
            agg_node_config = {
                "trigger": agg_config.trigger.model_dump(),
                "output_mode": agg_config.output_mode,
                "options": dict(agg_config.options),
            }

            graph.add_node(
                aid,
                node_type="aggregation",
                plugin_name=agg_config.plugin,
                config=agg_node_config,
            )

            # Edge from previous node (last transform, or source if no transforms)
            graph.add_edge(prev_node_id, aid, label="continue", mode=RoutingMode.MOVE)

            prev_node_id = aid

        # Store explicit mapping for get_aggregation_id_map()
        graph._aggregation_id_map = aggregation_ids

        # Build config-driven gates (processed AFTER transforms and aggregations, BEFORE output sink)
        config_gate_ids: dict[str, str] = {}
        gate_sequence: list[tuple[str, GateSettings]] = []  # Track for continue edge creation
        for gate_config in config.gates:
            gid = node_id("config_gate", gate_config.name)
            config_gate_ids[gate_config.name] = gid

            # Store condition in node config for audit trail
            gate_node_config = {
                "condition": gate_config.condition,
                "routes": dict(gate_config.routes),
            }
            if gate_config.fork_to:
                gate_node_config["fork_to"] = list(gate_config.fork_to)

            graph.add_node(
                gid,
                node_type="gate",
                plugin_name=f"config_gate:{gate_config.name}",
                config=gate_node_config,
            )

            # Edge from previous node (last transform or source)
            graph.add_edge(prev_node_id, gid, label="continue", mode=RoutingMode.MOVE)

            # Config gate routes to sinks
            for route_label, target in gate_config.routes.items():
                # Store route resolution: (gate_node, route_label) -> target
                graph._route_resolution_map[(gid, route_label)] = target

                if target == "continue":
                    continue  # Not a sink route - no edge to create
                if target == "fork":
                    # Fork creates edges to each fork_to destination
                    # - If branch matches a sink name, edge goes to that sink
                    # - If branch doesn't match a sink, edge goes to output_sink (fallback)
                    if gate_config.fork_to:
                        output_sink_node = sink_ids[config.output_sink]
                        for branch in gate_config.fork_to:
                            if branch in sink_ids:
                                # Edge with COPY mode to matching sink
                                graph.add_edge(
                                    gid,
                                    sink_ids[branch],
                                    label=branch,
                                    mode=RoutingMode.COPY,
                                )
                            else:
                                # Fallback: edge to output_sink with branch label
                                graph.add_edge(
                                    gid,
                                    output_sink_node,
                                    label=branch,
                                    mode=RoutingMode.COPY,
                                )
                    # Do NOT modify _route_resolution_map - keep existing "fork" value
                    continue
                if target not in sink_ids:
                    raise GraphValidationError(
                        f"Config gate '{gate_config.name}' routes '{route_label}' "
                        f"to unknown sink '{target}'. "
                        f"Available sinks: {list(sink_ids.keys())}"
                    )
                # Edge label = route_label
                graph.add_edge(gid, sink_ids[target], label=route_label, mode=RoutingMode.MOVE)
                # Store reverse mapping: (gate_node, sink_name) -> route_label
                graph._route_label_map[(gid, target)] = route_label

            # Track gate for continue edge creation (done after output_sink_node is known)
            gate_sequence.append((gid, gate_config))
            prev_node_id = gid

        # Store explicit mapping for get_config_gate_id_map()
        graph._config_gate_id_map = config_gate_ids

        # Build coalesce nodes (processed AFTER config gates)
        # These merge tokens from parallel fork paths back into a single token.
        coalesce_ids: dict[str, str] = {}
        branch_to_coalesce: dict[str, str] = {}

        for coalesce_config in config.coalesce:
            cid = node_id("coalesce", coalesce_config.name)
            coalesce_ids[coalesce_config.name] = cid

            for branch in coalesce_config.branches:
                branch_to_coalesce[branch] = coalesce_config.name

            coalesce_node_config = {
                "branches": list(coalesce_config.branches),
                "policy": coalesce_config.policy,
                "merge": coalesce_config.merge,
                "timeout_seconds": coalesce_config.timeout_seconds,
                "quorum_count": coalesce_config.quorum_count,
                "select_branch": coalesce_config.select_branch,
            }

            graph.add_node(
                cid,
                node_type="coalesce",
                plugin_name=f"coalesce:{coalesce_config.name}",
                config=coalesce_node_config,
            )

        graph._coalesce_id_map = coalesce_ids
        graph._branch_to_coalesce = branch_to_coalesce

        # Store output_sink for reference
        graph._output_sink = config.output_sink
        output_sink_node = sink_ids[config.output_sink]

        # Create continue edges from gates to their next node (AUD-002: explicit continue routing)
        # This enables recording routing events when a gate evaluates to "continue"
        for i, (gate_id, gate_config) in enumerate(gate_sequence):
            # Check if any route resolves to "continue"
            has_continue_route = any(target == "continue" for target in gate_config.routes.values())

            if has_continue_route:
                # Determine next node: next gate or output sink
                if i + 1 < len(gate_sequence):
                    next_node = gate_sequence[i + 1][0]  # Next gate
                else:
                    next_node = output_sink_node  # Output sink

                # Create continue edge (only if not already exists)
                if not graph._graph.has_edge(gate_id, next_node, key="continue"):
                    graph.add_edge(gate_id, next_node, label="continue", mode=RoutingMode.MOVE)

        # Create edges from fork gates to coalesce nodes (for branches in coalesce)
        # This overwrites the fallback edges created during gate processing
        for gate_config in config.gates:
            if gate_config.fork_to:
                gate_id = config_gate_ids[gate_config.name]
                for branch in gate_config.fork_to:
                    if branch in branch_to_coalesce:
                        coalesce_name = branch_to_coalesce[branch]
                        coalesce_id = coalesce_ids[coalesce_name]
                        # Remove any existing edge with this label (fallback to output_sink)
                        if graph._graph.has_edge(gate_id, output_sink_node, key=branch):
                            graph._graph.remove_edge(gate_id, output_sink_node, key=branch)
                        # Add edge to coalesce node
                        graph.add_edge(
                            gate_id,
                            coalesce_id,
                            label=branch,
                            mode=RoutingMode.COPY,
                        )

        # Create edges from coalesce nodes to output sink
        for _coalesce_name, cid in coalesce_ids.items():
            graph.add_edge(
                cid,
                output_sink_node,
                label="continue",
                mode=RoutingMode.MOVE,
            )

        # Edge from last node (transform or config gate or source) to output sink
        # Only add if no edge already exists to this sink (gate routes may have created one)
        if not graph._graph.has_edge(prev_node_id, output_sink_node, key="continue"):
            graph.add_edge(
                prev_node_id,
                output_sink_node,
                label="continue",
                mode=RoutingMode.MOVE,
            )

        return graph

    def get_sink_id_map(self) -> dict[str, str]:
        """Get explicit sink_name -> node_id mapping.

        Returns:
            Dict mapping each sink's logical name to its graph node ID.
            No substring matching required - use this for direct lookup.
        """
        return dict(self._sink_id_map)

    def get_transform_id_map(self) -> dict[int, str]:
        """Get explicit sequence -> node_id mapping for transforms.

        Returns:
            Dict mapping transform sequence position (0-indexed) to node ID.
        """
        return dict(self._transform_id_map)

    def get_config_gate_id_map(self) -> dict[str, str]:
        """Get explicit gate_name -> node_id mapping for config-driven gates.

        Returns:
            Dict mapping gate name to its graph node ID.
        """
        return dict(self._config_gate_id_map)

    def get_aggregation_id_map(self) -> dict[str, str]:
        """Get explicit agg_name -> node_id mapping for aggregations.

        Returns:
            Dict mapping aggregation name to its graph node ID.
        """
        return dict(self._aggregation_id_map)

    def get_coalesce_id_map(self) -> dict[str, str]:
        """Get explicit coalesce_name -> node_id mapping.

        Returns:
            Dict mapping coalesce name to its graph node ID.
        """
        return dict(self._coalesce_id_map)

    def get_branch_to_coalesce_map(self) -> dict[str, str]:
        """Get branch_name -> coalesce_name mapping.

        Returns:
            Dict mapping fork branch names to their coalesce destination.
            Branches not in this map route to the output sink.
        """
        return dict(self._branch_to_coalesce)

    def get_output_sink(self) -> str:
        """Get the output sink name."""
        return self._output_sink

    def get_route_label(self, from_node_id: str, sink_name: str) -> str:
        """Get the route label for an edge from a gate to a sink.

        Args:
            from_node_id: The gate node ID
            sink_name: The sink name (not node ID)

        Returns:
            The route label (e.g., "suspicious") or "continue" for default path
        """
        # Check explicit route mapping first
        if (from_node_id, sink_name) in self._route_label_map:
            return self._route_label_map[(from_node_id, sink_name)]

        # Default path uses "continue" label
        return "continue"

    def get_route_resolution_map(self) -> dict[tuple[str, str], str]:
        """Get the route resolution map for all gates.

        Returns:
            Dict mapping (gate_node_id, route_label) -> destination.
            Destination is either "continue" or a sink name.
            Used by the executor to resolve route labels from gates.
        """
        return dict(self._route_resolution_map)
