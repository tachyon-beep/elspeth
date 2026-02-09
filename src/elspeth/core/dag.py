# src/elspeth/core/dag.py
"""DAG (Directed Acyclic Graph) operations for execution planning.

Uses NetworkX for graph operations including:
- Acyclicity validation
- Topological sorting
- Path finding for lineage queries
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast

import networkx as nx
from networkx import MultiDiGraph

from elspeth.contracts import (
    EdgeInfo,
    RouteDestination,
    RoutingMode,
    check_compatibility,
    error_edge_label,
)
from elspeth.contracts.schema import SchemaConfig
from elspeth.contracts.types import (
    AggregationName,
    BranchName,
    CoalesceName,
    GateName,
    NodeID,
    SinkName,
)

if TYPE_CHECKING:
    from elspeth.contracts import PluginSchema
    from elspeth.core.config import (
        AggregationSettings,
        CoalesceSettings,
        GateSettings,
        SourceSettings,
        TransformSettings,
    )
    from elspeth.plugins.protocols import SinkProtocol, SourceProtocol, TransformProtocol


class GraphValidationError(Exception):
    """Raised when graph validation fails."""

    pass


# Config stored on graph nodes varies by node type:
# - Source/Transform/Sink: raw plugin config dict (arbitrary keys per plugin)
# - Gate: {schema, routes, condition, fork_to?}
# - Aggregation: {schema, trigger, output_mode, options}
# - Coalesce: {branches, policy, merge, timeout_seconds?, quorum_count?, select_branch?}
# Only "schema" is accessed cross-type. Other keys are opaque to the graph layer.
# dict[str, Any] is intentional: plugin configs are validated by each plugin's
# Pydantic model, not by the graph. The graph only hashes them for node IDs.
type NodeConfig = dict[str, Any]


@dataclass
class NodeInfo:
    """Information about a node in the execution graph.

    Schemas are immutable after graph construction. Even dynamic schemas
    (determined by data inspection) are locked at launch and never change
    during the run. This guarantees audit trail consistency.

    Schema Contracts:
        input_schema_config and output_schema_config store the original
        SchemaConfig from plugin configuration. These contain contract
        declarations (guaranteed_fields, required_fields) used for DAG
        validation. The input_schema and output_schema are the generated
        Pydantic model types used for runtime validation.
    """

    node_id: NodeID
    node_type: str  # source, transform, gate, aggregation, coalesce, sink
    plugin_name: str
    config: NodeConfig = field(default_factory=dict)
    input_schema: type[PluginSchema] | None = None  # Immutable after graph construction
    output_schema: type[PluginSchema] | None = None  # Immutable after graph construction
    # Schema configs for contract validation (guaranteed/required fields)
    input_schema_config: SchemaConfig | None = None
    output_schema_config: SchemaConfig | None = None


@dataclass(frozen=True)
class _GateEntry:
    """Internal gate metadata for coalesce and routing wiring."""

    node_id: NodeID
    name: str
    fork_to: list[str] | None
    routes: dict[str, str]


@dataclass(frozen=True, slots=True)
class WiredTransform:
    """Pair a transform plugin instance with its wiring settings."""

    plugin: TransformProtocol
    settings: TransformSettings


def _suggest_similar(name: str, candidates: list[str], max_distance: int = 3) -> list[str]:
    """Suggest similar names for wiring validation errors."""
    import difflib

    del max_distance  # Reserved for future distance-based matcher.
    return difflib.get_close_matches(name, candidates, n=3, cutoff=0.6)


class ExecutionGraph:
    """Execution graph for pipeline configuration.

    Wraps NetworkX MultiDiGraph with domain-specific operations.
    Uses MultiDiGraph to support multiple edges between the same node pair
    (e.g., fork gates routing multiple labels to the same sink).
    """

    def __init__(self) -> None:
        self._graph: MultiDiGraph[str] = nx.MultiDiGraph()
        self._sink_id_map: dict[SinkName, NodeID] = {}
        self._transform_id_map: dict[int, NodeID] = {}
        self._config_gate_id_map: dict[GateName, NodeID] = {}  # gate_name -> node_id
        self._aggregation_id_map: dict[AggregationName, NodeID] = {}  # agg_name -> node_id
        self._coalesce_id_map: dict[CoalesceName, NodeID] = {}  # coalesce_name -> node_id
        self._branch_to_coalesce: dict[BranchName, CoalesceName] = {}  # branch_name -> coalesce_name
        self._route_label_map: dict[tuple[NodeID, str], str] = {}  # (gate_node, sink_name) -> route_label
        self._route_resolution_map: dict[tuple[NodeID, str], RouteDestination] = {}
        self._coalesce_gate_index: dict[CoalesceName, int] = {}  # coalesce_name -> gate pipeline index
        self._pipeline_nodes: list[NodeID] = []  # Ordered processing nodes (no source/sinks)
        self._node_step_map: dict[NodeID, int] = {}  # node_id -> audit step (source=0)

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

    def get_nx_graph(self) -> MultiDiGraph[str]:
        """Return the underlying NetworkX graph for advanced operations.

        Use this for topology analysis, subgraph operations, and other
        NetworkX algorithms that require direct graph access.

        Returns:
            The underlying NetworkX MultiDiGraph.

        Warning:
            Direct graph manipulation should be avoided. Use ExecutionGraph
            methods (add_node, add_edge) to ensure integrity constraints.
        """
        return self._graph

    def add_node(
        self,
        node_id: str,
        *,
        node_type: str,
        plugin_name: str,
        config: NodeConfig | None = None,
        input_schema: type[PluginSchema] | None = None,
        output_schema: type[PluginSchema] | None = None,
        input_schema_config: SchemaConfig | None = None,
        output_schema_config: SchemaConfig | None = None,
    ) -> None:
        """Add a node to the execution graph.

        Args:
            node_id: Unique node identifier
            node_type: One of: source, transform, gate, aggregation, coalesce, sink
            plugin_name: Plugin identifier
            config: Node configuration (see NodeConfig type alias for per-node-type structure)
            input_schema: Input schema Pydantic type (None for dynamic or N/A like sources)
            output_schema: Output schema Pydantic type (None for dynamic or N/A like sinks)
            input_schema_config: Input schema config for contract validation
            output_schema_config: Output schema config for contract validation
        """
        info = NodeInfo(
            node_id=NodeID(node_id),
            node_type=node_type,
            plugin_name=plugin_name,
            config=config or {},
            input_schema=input_schema,
            output_schema=output_schema,
            input_schema_config=input_schema_config,
            output_schema_config=output_schema_config,
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
            mode: Routing mode (MOVE, COPY, or DIVERT)
        """
        # Use label as key to allow multiple edges between same nodes
        self._graph.add_edge(from_node, to_node, key=label, label=label, mode=mode)

    def is_acyclic(self) -> bool:
        """Check if the graph is acyclic (a valid DAG)."""
        return nx.is_directed_acyclic_graph(self._graph)

    def validate(self) -> None:
        """Validate the execution graph structure.

        Validates:
        1. Graph is acyclic (no cycles)
        2. Exactly one source node exists
        3. At least one sink node exists
        4. All nodes are reachable from source (no disconnected/orphaned nodes)
        5. Edge labels are unique per source node

        Does NOT check schema compatibility - plugins validate their own
        schemas during construction.

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

        # Check for unreachable nodes (nodes not reachable from source)
        source_id = sources[0]  # We already validated exactly one source exists
        reachable = nx.descendants(self._graph, source_id)
        reachable.add(source_id)  # Include source itself in reachable set

        all_nodes = set(self._graph.nodes())
        unreachable = all_nodes - reachable

        if unreachable:
            # Build detailed error message with node types
            unreachable_details = [f"{node_id} ({self._graph.nodes[node_id]['info'].node_type})" for node_id in sorted(unreachable)]
            raise GraphValidationError(
                f"Graph validation failed: {len(unreachable)} unreachable node(s) detected:\n"
                f"  {', '.join(unreachable_details)}\n"
                f"All nodes must be reachable from the source node '{source_id}'."
            )

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

    def get_source(self) -> NodeID | None:
        """Get the source node ID.

        Returns:
            The source node ID, or None if not exactly one source exists.
        """
        # All nodes have "info" - added via add_node(), direct access is safe
        sources = [NodeID(node_id) for node_id, data in self._graph.nodes(data=True) if data["info"].node_type == "source"]
        return sources[0] if len(sources) == 1 else None

    def get_sinks(self) -> list[NodeID]:
        """Get all sink node IDs.

        Returns:
            List of sink node IDs.
        """
        # All nodes have "info" - added via add_node(), direct access is safe
        return [NodeID(node_id) for node_id, data in self._graph.nodes(data=True) if data["info"].node_type == "sink"]

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

    def is_sink_node(self, node_id: NodeID) -> bool:
        """Check if a node is a sink node."""
        if not self._graph.has_node(node_id):
            return False
        return self.get_node_info(node_id).node_type == "sink"

    def get_first_transform_node(self) -> NodeID | None:
        """Get the first processing node after source via continue edge.

        Returns:
            Node ID of the first processing node (transform/gate/aggregation),
            or None for source-only pipelines.
        """
        source_id = self.get_source()
        if source_id is None:
            return None
        return self.get_next_node(source_id)

    def get_next_node(self, node_id: NodeID) -> NodeID | None:
        """Follow the continue MOVE edge to the next processing node.

        Returns:
            Next processing node ID, or None if node is terminal.
        """
        next_nodes: list[NodeID] = []
        for _from_id, to_id, edge_key, edge_data in self._graph.out_edges(node_id, keys=True, data=True):
            if edge_key != "continue":
                continue
            if edge_data["mode"] != RoutingMode.MOVE:
                continue
            next_node_id = NodeID(to_id)
            if self.is_sink_node(next_node_id):
                continue
            next_nodes.append(next_node_id)

        if len(next_nodes) > 1:
            raise GraphValidationError(f"Node '{node_id}' has multiple continue MOVE edges to processing nodes: {sorted(next_nodes)}")
        if len(next_nodes) == 1:
            return next_nodes[0]
        return None

    def get_pipeline_node_sequence(self) -> list[NodeID]:
        """Get ordered processing nodes in pipeline traversal order."""
        if self._pipeline_nodes:
            return list(self._pipeline_nodes)

        first_node = self.get_first_transform_node()
        if first_node is None:
            return []

        reachable: set[NodeID] = set()
        pending: list[NodeID] = [first_node]
        while pending:
            current = pending.pop()
            if current in reachable:
                continue
            reachable.add(current)

            for _from_id, to_id, _edge_key, edge_data in self._graph.out_edges(current, keys=True, data=True):
                if edge_data["mode"] != RoutingMode.MOVE:
                    continue
                target = NodeID(to_id)
                if self.is_sink_node(target):
                    continue
                pending.append(target)

        return [node_id for node_id in (NodeID(node) for node in self.topological_order()) if node_id in reachable]

    def build_step_map(self) -> dict[NodeID, int]:
        """Build node -> audit step map (source=0, processing nodes start at 1)."""
        source_id = self.get_source()
        if source_id is None:
            return {}

        step_map: dict[NodeID, int] = {source_id: 0}
        for idx, node_id in enumerate(self.get_pipeline_node_sequence(), start=1):
            step_map[node_id] = idx

        self._node_step_map = dict(step_map)
        return dict(step_map)

    def get_nodes(self) -> list[NodeInfo]:
        """Get all nodes as NodeInfo objects.

        Returns:
            List of NodeInfo objects for all nodes in the graph.
        """
        return [cast(NodeInfo, attrs["info"]) for _node_id, attrs in self._graph.nodes(data=True)]

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
    def from_plugin_instances(
        cls,
        source: SourceProtocol,
        source_settings: SourceSettings,
        transforms: list[WiredTransform],
        sinks: dict[str, SinkProtocol],
        aggregations: dict[str, tuple[TransformProtocol, AggregationSettings]],
        gates: list[GateSettings],
        coalesce_settings: list[CoalesceSettings] | None = None,
    ) -> ExecutionGraph:
        """Build ExecutionGraph from plugin instances.

        CORRECT method for graph construction - enables schema validation.
        Schemas extracted directly from instance attributes.

        Routing is explicit: terminal transforms and sources declare their
        output sink via on_success. There is no default_sink fallback.

        Args:
            source: Instantiated source plugin
            source_settings: Source settings (wiring metadata)
            transforms: Wired transforms (plugin instance + settings metadata)
            sinks: Dict of sink_name -> instantiated sink
            aggregations: Dict of agg_name -> (transform_instance, AggregationSettings)
            gates: Config-driven gate settings
            coalesce_settings: Coalesce configs for fork/join patterns

        Returns:
            ExecutionGraph with schemas populated

        Raises:
            GraphValidationError: If gate routes reference unknown sinks,
                terminal nodes lack on_success, or on_success references
                unknown sinks.
        """
        import hashlib

        from elspeth.core.canonical import canonical_json
        from elspeth.plugins.protocols import GateProtocol

        graph = cls()

        def node_id(prefix: str, name: str, config: NodeConfig, sequence: int | None = None) -> NodeID:
            """Generate deterministic node ID based on plugin type and config.

            Node IDs must be deterministic for checkpoint/resume compatibility.
            If a pipeline is checkpointed and later resumed, the node IDs must
            be identical so checkpoint state can be restored correctly.

            For nodes that can appear multiple times with identical configs
            (transforms, aggregations), include sequence number to ensure uniqueness.

            Args:
                prefix: Node type prefix (source_, transform_, sink_, etc.)
                name: Plugin name
                config: Plugin configuration dict
                sequence: Optional sequence number for duplicate configs (transforms, aggregations)

            Returns:
                Deterministic node ID
            """
            # Create stable hash of config using RFC 8785 canonical JSON
            # CRITICAL: Must use canonical_json() not json.dumps() for true determinism
            # (floats, nested dicts, datetime serialization must be consistent)
            config_str = canonical_json(config)
            config_hash = hashlib.sha256(config_str.encode()).hexdigest()[:12]  # 48 bits

            # Include sequence number for nodes that can have duplicates
            if sequence is not None:
                return NodeID(f"{prefix}_{name}_{config_hash}_{sequence}")
            return NodeID(f"{prefix}_{name}_{config_hash}")

        def _sink_name_set() -> set[str]:
            return {str(name) for name in sink_ids}

        # Add source
        source_config = source.config
        source_id = node_id("source", source.name, source_config)
        graph.add_node(
            source_id,
            node_type="source",
            plugin_name=source.name,
            config=source_config,
            output_schema=source.output_schema,  # SourceProtocol requires this
        )

        # Add sinks
        sink_ids: dict[SinkName, NodeID] = {}
        for sink_name, sink in sinks.items():
            sink_config = sink.config
            sid = node_id("sink", sink_name, sink_config)
            sink_ids[SinkName(sink_name)] = sid
            graph.add_node(
                sid,
                node_type="sink",
                plugin_name=sink.name,
                config=sink_config,
                input_schema=sink.input_schema,  # SinkProtocol requires this
            )

        graph._sink_id_map = dict(sink_ids)

        # Build transforms (including plugin gates)
        transform_ids_by_name: dict[str, NodeID] = {}
        transform_ids_by_seq: dict[int, NodeID] = {}
        gate_entries: list[_GateEntry] = []
        gate_route_connections: list[tuple[NodeID, str, str]] = []
        plugin_gate_schema_inputs: list[tuple[NodeID, str, str, object | None]] = []

        for seq, wired in enumerate(transforms):
            transform = wired.plugin
            transform_config = transform.config
            is_gate = isinstance(transform, GateProtocol)
            tid = node_id("transform", wired.settings.name, transform_config)
            transform_ids_by_name[wired.settings.name] = tid
            transform_ids_by_seq[seq] = tid

            node_config = dict(transform_config)
            node_type = "gate" if is_gate else "transform"

            if is_gate:
                # Type narrowing: we know it's a GateProtocol from isinstance check
                gate = cast(GateProtocol, transform)
                if "schema" in node_config:  # noqa: SIM401
                    declared_schema = node_config["schema"]
                else:
                    declared_schema = None
                plugin_gate_schema_inputs.append((tid, gate.name, wired.settings.input, declared_schema))
                node_config["routes"] = dict(gate.routes)
                if gate.fork_to is not None:
                    node_config["fork_to"] = list(gate.fork_to)

            # Extract computed output schema config if available (e.g., LLM transforms
            # compute guaranteed_fields and audit_fields from their configuration)
            output_schema_config = getattr(transform, "_output_schema_config", None)

            graph.add_node(
                tid,
                node_type=node_type,
                plugin_name=transform.name,
                config=node_config,
                input_schema=transform.input_schema,  # TransformProtocol requires this
                output_schema=transform.output_schema,  # TransformProtocol requires this
                output_schema_config=output_schema_config,
            )

            if is_gate:
                # Type narrowing: we know it's a GateProtocol from isinstance check
                gate = cast(GateProtocol, transform)
                gate_entries.append(
                    _GateEntry(
                        node_id=tid,
                        name=gate.name,
                        fork_to=list(gate.fork_to) if gate.fork_to is not None else None,
                        routes=dict(gate.routes),
                    )
                )

                # Gate routes to sinks via route labels; connection-name routes are deferred.
                for route_label, target in gate.routes.items():
                    if target == "fork":
                        raise GraphValidationError(
                            f"Gate '{transform.name}' route '{route_label}' resolves to 'fork'. "
                            "Plugin gates must use RoutingAction.fork_to_paths() for forks."
                        )
                    if SinkName(target) in sink_ids:
                        target_sink_id = sink_ids[SinkName(target)]
                        graph.add_edge(tid, target_sink_id, label=route_label, mode=RoutingMode.MOVE)
                        graph._route_label_map[(tid, target)] = route_label
                        graph._route_resolution_map[(tid, route_label)] = RouteDestination.sink(target)
                    else:
                        gate_route_connections.append((tid, route_label, target))

        graph._transform_id_map = transform_ids_by_seq

        # Build aggregations
        aggregation_ids: dict[AggregationName, NodeID] = {}
        for agg_name, (transform, agg_config) in aggregations.items():
            transform_config = transform.config
            agg_node_config = {
                "trigger": agg_config.trigger.model_dump(),
                "output_mode": agg_config.output_mode,
                "options": dict(agg_config.options),
                "schema": transform_config["schema"],
            }
            aid = node_id("aggregation", agg_name, agg_node_config)
            aggregation_ids[AggregationName(agg_name)] = aid

            # Extract computed output schema config if available (e.g., LLM aggregations
            # compute guaranteed_fields and audit_fields from their configuration)
            agg_output_schema_config = getattr(transform, "_output_schema_config", None)

            graph.add_node(
                aid,
                node_type="aggregation",
                plugin_name=agg_config.plugin,
                config=agg_node_config,
                input_schema=transform.input_schema,  # TransformProtocol requires this (aggregations use transforms)
                output_schema=transform.output_schema,  # TransformProtocol requires this (aggregations use transforms)
                output_schema_config=agg_output_schema_config,
            )

        graph._aggregation_id_map = aggregation_ids

        # Build config gates (no plugin instances)
        config_gate_ids: dict[GateName, NodeID] = {}
        config_gate_schema_inputs: list[tuple[NodeID, str, str]] = []

        for gate_config in gates:
            gate_node_config = {
                "condition": gate_config.condition,
                "routes": dict(gate_config.routes),
            }
            if gate_config.fork_to:
                gate_node_config["fork_to"] = list(gate_config.fork_to)

            gid = node_id("config_gate", gate_config.name, gate_node_config)
            config_gate_ids[GateName(gate_config.name)] = gid

            graph.add_node(
                gid,
                node_type="gate",
                plugin_name=f"config_gate:{gate_config.name}",
                config=gate_node_config,
            )

            config_gate_schema_inputs.append((gid, gate_config.name, gate_config.input))

            # Gate routes to sinks; connection-name routes are deferred.
            for route_label, target in gate_config.routes.items():
                if target == "fork":
                    # Fork is a special routing mode - handled by fork_to branches
                    graph._route_resolution_map[(gid, route_label)] = RouteDestination.fork()
                elif SinkName(target) in sink_ids:
                    target_sink_id = sink_ids[SinkName(target)]
                    graph.add_edge(gid, target_sink_id, label=route_label, mode=RoutingMode.MOVE)
                    graph._route_label_map[(gid, target)] = route_label
                    graph._route_resolution_map[(gid, route_label)] = RouteDestination.sink(target)
                else:
                    gate_route_connections.append((gid, route_label, target))

            gate_entries.append(
                _GateEntry(
                    node_id=gid,
                    name=gate_config.name,
                    fork_to=list(gate_config.fork_to) if gate_config.fork_to is not None else None,
                    routes=dict(gate_config.routes),
                )
            )

        graph._config_gate_id_map = config_gate_ids

        # ===== COALESCE IMPLEMENTATION (BUILD NODES AND MAPPINGS FIRST) =====
        # Build coalesce nodes BEFORE connecting gates (needed for branch routing)
        coalesce_ids: dict[CoalesceName, NodeID] = {}
        if coalesce_settings:
            branch_to_coalesce: dict[BranchName, CoalesceName] = {}

            for coalesce_config in coalesce_settings:
                # Coalesce merges - no schema transformation
                # Note: Pydantic validates min_length=2 for branches field
                config_dict: NodeConfig = {
                    "branches": list(coalesce_config.branches),
                    "policy": coalesce_config.policy,
                    "merge": coalesce_config.merge,
                }
                if coalesce_config.timeout_seconds is not None:
                    config_dict["timeout_seconds"] = coalesce_config.timeout_seconds
                if coalesce_config.quorum_count is not None:
                    config_dict["quorum_count"] = coalesce_config.quorum_count
                if coalesce_config.select_branch is not None:
                    config_dict["select_branch"] = coalesce_config.select_branch

                cid = node_id("coalesce", coalesce_config.name, config_dict)
                coalesce_ids[CoalesceName(coalesce_config.name)] = cid

                # Map branches to this coalesce - check for duplicates
                for branch_name in coalesce_config.branches:
                    if BranchName(branch_name) in branch_to_coalesce:
                        # Branch already mapped to another coalesce
                        existing_coalesce = branch_to_coalesce[BranchName(branch_name)]
                        raise GraphValidationError(
                            f"Duplicate branch name '{branch_name}' found in coalesce settings.\n"
                            f"Branch '{branch_name}' is already mapped to coalesce '{existing_coalesce}', "
                            f"but coalesce '{coalesce_config.name}' also declares it.\n"
                            f"Each fork branch can only merge at one coalesce point."
                        )
                    branch_to_coalesce[BranchName(branch_name)] = CoalesceName(coalesce_config.name)

                graph.add_node(
                    cid,
                    node_type="coalesce",
                    plugin_name=f"coalesce:{coalesce_config.name}",
                    config=config_dict,
                )

            graph._coalesce_id_map = coalesce_ids
            graph._branch_to_coalesce = branch_to_coalesce
        else:
            branch_to_coalesce = {}

        # ===== CONNECT FORK GATES - EXPLICIT DESTINATIONS ONLY =====
        # CRITICAL: No fallback behavior. All fork branches must have explicit destinations.
        # This prevents silent configuration bugs (typos, missing destinations).
        for gate_entry in gate_entries:
            if gate_entry.fork_to:
                branch_counts = Counter(gate_entry.fork_to)
                duplicates = sorted([branch for branch, count in branch_counts.items() if count > 1])
                if duplicates:
                    raise GraphValidationError(
                        f"Gate '{gate_entry.name}' has duplicate fork branches: {duplicates}. Each fork branch name must be unique."
                    )
                for branch_name in gate_entry.fork_to:
                    if BranchName(branch_name) in branch_to_coalesce:
                        # Explicit coalesce destination
                        coalesce_name = branch_to_coalesce[BranchName(branch_name)]
                        coalesce_id = coalesce_ids[coalesce_name]
                        graph.add_edge(gate_entry.node_id, coalesce_id, label=branch_name, mode=RoutingMode.COPY)
                    elif SinkName(branch_name) in sink_ids:
                        # Explicit sink destination (branch name matches sink name)
                        graph.add_edge(
                            gate_entry.node_id,
                            sink_ids[SinkName(branch_name)],
                            label=branch_name,
                            mode=RoutingMode.COPY,
                        )
                    else:
                        # NO FALLBACK - this is a configuration error
                        raise GraphValidationError(
                            f"Gate '{gate_entry.name}' has fork branch '{branch_name}' with no destination.\n"
                            f"Fork branches must either:\n"
                            f"  1. Be listed in a coalesce 'branches' list, or\n"
                            f"  2. Match a sink name exactly\n"
                            f"\n"
                            f"Available coalesce branches: {sorted(branch_to_coalesce.keys())}\n"
                            f"Available sinks: {sorted(sink_ids.keys())}"
                        )

        # ===== VALIDATE COALESCE BRANCHES ARE PRODUCED BY GATES =====
        # All branches declared in coalesce settings must be produced by some fork gate
        if coalesce_settings and branch_to_coalesce:
            # Collect all branches produced by gates
            produced_branches: set[str] = set()
            for gate_entry in gate_entries:
                if gate_entry.fork_to:
                    produced_branches.update(gate_entry.fork_to)

            # Check that all coalesce branches are produced
            for branch_name, coalesce_name in branch_to_coalesce.items():
                if branch_name not in produced_branches:
                    raise GraphValidationError(
                        f"Coalesce '{coalesce_name}' declares branch '{branch_name}', "
                        f"but no gate produces this branch.\n"
                        f"Branches must be listed in a gate's fork_to list to be valid.\n"
                        f"\n"
                        f"Branches produced by gates: {sorted(produced_branches) if produced_branches else '(none)'}\n"
                        f"Coalesce '{coalesce_name}' expects branches: "
                        f"{sorted([b for b, c in branch_to_coalesce.items() if c == coalesce_name])}"
                    )

        # ===== BUILD PRODUCER REGISTRY =====
        producers: dict[str, tuple[NodeID, str]] = {}
        producer_desc: dict[str, str] = {}

        def register_producer(connection_name: str, node_id: NodeID, label: str, description: str) -> None:
            if connection_name in producers:
                existing_node, _existing_label = producers[connection_name]
                raise GraphValidationError(
                    f"Duplicate producer for connection '{connection_name}': "
                    f"{producer_desc[connection_name]} ({existing_node}) and {description} ({node_id})."
                )
            producers[connection_name] = (node_id, label)
            producer_desc[connection_name] = description

        source_on_success = source_settings.on_success
        if SinkName(source_on_success) not in sink_ids:
            register_producer(
                source_on_success,
                source_id,
                "continue",
                f"source '{source.name}'",
            )

        for wired in transforms:
            if isinstance(wired.plugin, GateProtocol):
                continue
            tid = transform_ids_by_name[wired.settings.name]
            on_success = wired.settings.on_success
            if on_success is None:
                register_producer(wired.settings.name, tid, "continue", f"transform '{wired.settings.name}'")
            elif SinkName(on_success) not in sink_ids:
                register_producer(on_success, tid, "continue", f"transform '{wired.settings.name}'")

        for agg_name, (_transform, agg_settings) in aggregations.items():
            aid = aggregation_ids[AggregationName(agg_name)]
            if agg_settings.on_success is None:
                register_producer(agg_settings.name, aid, "continue", f"aggregation '{agg_settings.name}'")
            elif SinkName(agg_settings.on_success) not in sink_ids:
                register_producer(agg_settings.on_success, aid, "continue", f"aggregation '{agg_settings.name}'")

        if coalesce_settings:
            for coalesce_config in coalesce_settings:
                if coalesce_config.on_success is None:
                    coalesce_id = coalesce_ids[CoalesceName(coalesce_config.name)]
                    register_producer(
                        coalesce_config.name,
                        coalesce_id,
                        "continue",
                        f"coalesce '{coalesce_config.name}'",
                    )

        for gate_id, route_label, target in gate_route_connections:
            register_producer(target, gate_id, route_label, f"gate route '{route_label}' from '{gate_id}'")

        # ===== BUILD CONSUMER REGISTRY =====
        consumers: dict[str, NodeID] = {}
        consumer_desc: dict[str, str] = {}

        def register_consumer(connection_name: str, node_id: NodeID, description: str) -> None:
            if connection_name in consumers:
                raise GraphValidationError(
                    f"Duplicate consumer for connection '{connection_name}': "
                    f"{consumer_desc[connection_name]} ({consumers[connection_name]}) and {description} ({node_id}). "
                    "Use a gate for fan-out."
                )
            consumers[connection_name] = node_id
            consumer_desc[connection_name] = description

        for wired in transforms:
            register_consumer(
                wired.settings.input,
                transform_ids_by_name[wired.settings.name],
                f"transform '{wired.settings.name}'",
            )

        for agg_name, (_transform, agg_settings) in aggregations.items():
            register_consumer(
                agg_settings.input,
                aggregation_ids[AggregationName(agg_name)],
                f"aggregation '{agg_settings.name}'",
            )

        for gate_settings in gates:
            register_consumer(
                gate_settings.input,
                config_gate_ids[GateName(gate_settings.name)],
                f"gate '{gate_settings.name}'",
            )

        # ===== VALIDATE DISJOINT NAMESPACES =====
        connection_names = set(producers.keys()) | set(consumers.keys())
        overlap = connection_names & _sink_name_set()
        if overlap:
            raise GraphValidationError(
                f"Connection names overlap with sink names: {sorted(overlap)}. Connection names and sink names must be disjoint."
            )

        # Resolve gate schema from explicit input connection.
        for gate_id, gate_name, input_connection, declared_schema in plugin_gate_schema_inputs:
            if input_connection not in producers:
                suggestions = _suggest_similar(input_connection, sorted(producers.keys()))
                hint = f" Did you mean: {suggestions}?" if suggestions else ""
                raise GraphValidationError(
                    f"Gate '{gate_name}' input '{input_connection}' has no producer.{hint}\n"
                    f"Available connections: {sorted(producers.keys())}"
                )
            producer_id, _producer_label = producers[input_connection]
            upstream_schema = graph.get_node_info(producer_id).config["schema"]
            if declared_schema is not None and declared_schema != upstream_schema:
                raise GraphValidationError(
                    f"Gate '{gate_name}' declares schema config that differs from upstream. "
                    f"Upstream schema config: {upstream_schema}, gate schema config: {declared_schema}"
                )
            graph.get_node_info(gate_id).config["schema"] = upstream_schema

        for gate_id, gate_name, input_connection in config_gate_schema_inputs:
            if input_connection not in producers:
                suggestions = _suggest_similar(input_connection, sorted(producers.keys()))
                hint = f" Did you mean: {suggestions}?" if suggestions else ""
                raise GraphValidationError(
                    f"Gate '{gate_name}' input '{input_connection}' has no producer.{hint}\n"
                    f"Available connections: {sorted(producers.keys())}"
                )
            producer_id, _producer_label = producers[input_connection]
            upstream_schema = graph.get_node_info(producer_id).config["schema"]
            graph.get_node_info(gate_id).config["schema"] = upstream_schema

        # ===== MATCH PRODUCERS TO CONSUMERS =====
        gate_node_ids = {entry.node_id for entry in gate_entries}

        for connection_name, consumer_id in consumers.items():
            if connection_name not in producers:
                suggestions = _suggest_similar(connection_name, sorted(producers.keys()))
                hint = f" Did you mean: {suggestions}?" if suggestions else ""
                raise GraphValidationError(
                    f"No producer for connection '{connection_name}'.{hint}\nAvailable connections: {sorted(producers.keys())}"
                )

            producer_id, producer_label = producers[connection_name]
            if producer_id in gate_node_ids and producer_label != "continue":
                # Preserve "destination: continue" semantics (continue edge label).
                # Other connection targets keep route-label edges for unambiguous audit mapping.
                if connection_name == "continue":
                    graph.add_edge(producer_id, consumer_id, label="continue", mode=RoutingMode.MOVE)
                else:
                    graph.add_edge(producer_id, consumer_id, label=producer_label, mode=RoutingMode.MOVE)
            else:
                graph.add_edge(producer_id, consumer_id, label="continue", mode=RoutingMode.MOVE)

        # ===== RESOLVE DEFERRED GATE ROUTES =====
        for gate_id, route_label, target in gate_route_connections:
            if target == "continue":
                graph._route_resolution_map[(gate_id, route_label)] = RouteDestination.continue_()
                continue
            if target not in consumers:
                suggestions = _suggest_similar(target, sorted(consumers.keys()))
                hint = f" Did you mean: {suggestions}?" if suggestions else ""
                raise GraphValidationError(f"Gate route target '{target}' is neither a sink nor a known connection name.{hint}")
            graph._route_resolution_map[(gate_id, route_label)] = RouteDestination.processing_node(consumers[target])

        # ===== TERMINAL ROUTING (on_success -> sinks) =====
        for wired in transforms:
            if isinstance(wired.plugin, GateProtocol):
                continue
            on_success = wired.settings.on_success
            if on_success is None:
                continue
            tid = transform_ids_by_name[wired.settings.name]
            if SinkName(on_success) in sink_ids:
                graph.add_edge(tid, sink_ids[SinkName(on_success)], label="on_success", mode=RoutingMode.MOVE)
            elif on_success not in consumers:
                suggestions = _suggest_similar(on_success, sorted(consumers.keys()))
                hint = f" Did you mean: {suggestions}?" if suggestions else ""
                raise GraphValidationError(
                    f"Transform '{wired.settings.name}' on_success '{on_success}' is neither a sink nor a known connection.{hint}"
                )

        for agg_name, (_transform, agg_settings) in aggregations.items():
            on_success = agg_settings.on_success
            if on_success is None:
                continue
            aid = aggregation_ids[AggregationName(agg_name)]
            if SinkName(on_success) in sink_ids:
                graph.add_edge(aid, sink_ids[SinkName(on_success)], label="on_success", mode=RoutingMode.MOVE)
            elif on_success not in consumers:
                suggestions = _suggest_similar(on_success, sorted(consumers.keys()))
                hint = f" Did you mean: {suggestions}?" if suggestions else ""
                raise GraphValidationError(
                    f"Aggregation '{agg_settings.name}' on_success '{on_success}' is neither a sink nor a known connection.{hint}"
                )

        if coalesce_settings:
            for coalesce_config in coalesce_settings:
                if coalesce_config.on_success is None:
                    continue
                if coalesce_config.on_success in consumers:
                    raise GraphValidationError(
                        f"Coalesce '{coalesce_config.name}' has on_success='{coalesce_config.on_success}'. "
                        "Coalesce on_success must point to a sink when configured."
                    )
                on_success_sink = SinkName(coalesce_config.on_success)
                if on_success_sink not in sink_ids:
                    raise GraphValidationError(
                        f"Coalesce '{coalesce_config.name}' on_success references unknown sink "
                        f"'{coalesce_config.on_success}'. Available sinks: {sorted(sink_ids.keys())}"
                    )
                graph.add_edge(
                    coalesce_ids[CoalesceName(coalesce_config.name)],
                    sink_ids[on_success_sink],
                    label="on_success",
                    mode=RoutingMode.MOVE,
                )

        if SinkName(source_on_success) in sink_ids:
            # For source-only pipelines, create direct source -> sink edge.
            if not transforms and not gates and not aggregations:
                graph.add_edge(
                    source_id,
                    sink_ids[SinkName(source_on_success)],
                    label="on_success",
                    mode=RoutingMode.MOVE,
                )
        elif source_on_success not in consumers:
            suggestions = _suggest_similar(source_on_success, sorted(consumers.keys()))
            hint = f" Did you mean: {suggestions}?" if suggestions else ""
            raise GraphValidationError(
                f"Source '{source.name}' on_success '{source_on_success}' is neither a sink nor a known connection.{hint}"
            )

        dangling_connections = sorted(set(producers.keys()) - set(consumers.keys()))
        if dangling_connections:
            raise GraphValidationError(
                f"Dangling output connections with no consumer: {dangling_connections}. "
                "Every produced connection must be consumed or routed to a sink."
            )

        # ===== ADD DIVERT EDGES (quarantine/error sinks) =====
        # Divert edges represent error/quarantine data flows that bypass the
        # normal DAG execution path. They make quarantine/error sinks reachable
        # in the graph (required for node_ids and audit trail).
        #
        # These are STRUCTURAL markers, not execution paths. Rows reach these
        # sinks via exception handling (processor.py) or source validation
        # failures (orchestrator.py), not by traversing the edge during
        # normal processing.

        # Source quarantine edge
        # _on_validation_failure is defined on SourceProtocol (protocols.py:78)
        quarantine_dest = source._on_validation_failure
        if quarantine_dest != "discard" and SinkName(quarantine_dest) in sink_ids:
            graph.add_edge(
                source_id,
                sink_ids[SinkName(quarantine_dest)],
                label="__quarantine__",
                mode=RoutingMode.DIVERT,
            )

        # Transform error edges
        # GateProtocol does NOT define _on_error, so skip gates.
        # The isinstance check is framework-boundary type narrowing — the
        # transforms list contains both TransformProtocol and GateProtocol
        # instances.
        for wired in transforms:
            if isinstance(wired.plugin, GateProtocol):
                continue
            on_error = wired.settings.on_error
            if on_error is not None and on_error != "discard" and SinkName(on_error) in sink_ids:
                graph.add_edge(
                    transform_ids_by_name[wired.settings.name],
                    sink_ids[SinkName(on_error)],
                    label=error_edge_label(wired.settings.name),
                    mode=RoutingMode.DIVERT,
                )

        # ===== PIPELINE ORDERING (TOPOLOGICAL) =====
        processing_node_ids: set[NodeID] = set()
        processing_node_ids.update(transform_ids_by_name.values())
        processing_node_ids.update(aggregation_ids.values())
        processing_node_ids.update(config_gate_ids.values())
        processing_node_ids.update(coalesce_ids.values())

        topo_order = [NodeID(node_id) for node_id in nx.topological_sort(graph._graph)]
        pipeline_nodes = [node_id for node_id in topo_order if node_id in processing_node_ids]

        expected_yaml_nodes: list[NodeID] = []
        expected_yaml_nodes.extend(transform_ids_by_seq[idx] for idx in sorted(transform_ids_by_seq))
        expected_yaml_nodes.extend(aggregation_ids[AggregationName(agg_name)] for agg_name in aggregations)
        expected_yaml_nodes.extend(config_gate_ids[GateName(gate_settings.name)] for gate_settings in gates)
        expected_yaml_set = set(expected_yaml_nodes)
        topo_yaml_nodes = [node_id for node_id in pipeline_nodes if node_id in expected_yaml_set]

        if topo_yaml_nodes != expected_yaml_nodes:
            raise GraphValidationError(
                "YAML declaration order does not match graph topological order. "
                f"Expected processing order: {expected_yaml_nodes}. "
                f"Topological order: {topo_yaml_nodes}."
            )

        pipeline_index: dict[NodeID, int] = {node_id: idx for idx, node_id in enumerate(pipeline_nodes)}
        coalesce_gate_index: dict[CoalesceName, int] = {}
        if coalesce_settings:
            for gate_entry in gate_entries:
                if gate_entry.fork_to is None:
                    continue
                gate_idx = pipeline_index[gate_entry.node_id]
                for branch_name in gate_entry.fork_to:
                    branch_key = BranchName(branch_name)
                    if branch_key not in branch_to_coalesce:
                        continue
                    coalesce_name = branch_to_coalesce[branch_key]
                    if coalesce_name in coalesce_gate_index:  # noqa: SIM401
                        existing_idx = coalesce_gate_index[coalesce_name]
                    else:
                        existing_idx = None
                    if existing_idx is None or gate_idx > existing_idx:
                        coalesce_gate_index[coalesce_name] = gate_idx

            for coalesce_name in coalesce_ids:
                if coalesce_name not in coalesce_gate_index:
                    raise GraphValidationError(
                        f"Coalesce '{coalesce_name}' has no producing gate. This should have been caught by branch validation."
                    )
        graph._coalesce_gate_index = coalesce_gate_index

        # ===== POPULATE COALESCE SCHEMA CONFIG =====
        # Coalesce nodes are structural pass-throughs; record the upstream schema
        # so audit logs reflect the actual data contract at the merge point.
        for coalesce_id in coalesce_ids.values():
            incoming_edges = list(graph._graph.in_edges(coalesce_id))
            if not incoming_edges:
                raise GraphValidationError(f"Coalesce node '{coalesce_id}' has no incoming branches; cannot determine schema for audit.")

            first_from_node = incoming_edges[0][0]
            first_schema = graph.get_node_info(first_from_node).config["schema"]

            for from_node, _to_node in incoming_edges[1:]:
                other_schema = graph.get_node_info(from_node).config["schema"]
                if other_schema != first_schema:
                    raise GraphValidationError(
                        f"Coalesce node '{coalesce_id}' receives mismatched schema configs from branches. "
                        "Schemas must be identical at merge points."
                    )

            graph.get_node_info(coalesce_id).config["schema"] = first_schema

        # PHASE 2 VALIDATION: Validate schema compatibility AFTER graph is built
        graph.validate_edge_compatibility()

        # Step maps and node sequence support node_id-based processor traversal.
        graph._pipeline_nodes = list(pipeline_nodes)
        graph._node_step_map = graph.build_step_map()

        return graph

    def get_sink_id_map(self) -> dict[SinkName, NodeID]:
        """Get explicit sink_name -> node_id mapping.

        Returns:
            Dict mapping each sink's logical name to its graph node ID.
            No substring matching required - use this for direct lookup.
        """
        return dict(self._sink_id_map)

    def get_transform_id_map(self) -> dict[int, NodeID]:
        """Get explicit sequence -> node_id mapping for transforms.

        Returns:
            Dict mapping transform sequence position (0-indexed) to node ID.
        """
        return dict(self._transform_id_map)

    def get_config_gate_id_map(self) -> dict[GateName, NodeID]:
        """Get explicit gate_name -> node_id mapping for config-driven gates.

        Returns:
            Dict mapping gate name to its graph node ID.
        """
        return dict(self._config_gate_id_map)

    def get_aggregation_id_map(self) -> dict[AggregationName, NodeID]:
        """Get explicit agg_name -> node_id mapping for aggregations.

        Returns:
            Dict mapping aggregation name to its graph node ID.
        """
        return dict(self._aggregation_id_map)

    def get_coalesce_id_map(self) -> dict[CoalesceName, NodeID]:
        """Get explicit coalesce_name -> node_id mapping.

        Returns:
            Dict mapping coalesce name to its graph node ID.
        """
        return dict(self._coalesce_id_map)

    def get_branch_to_coalesce_map(self) -> dict[BranchName, CoalesceName]:
        """Get branch_name -> coalesce_name mapping.

        Returns:
            Dict mapping fork branch names to their coalesce destination.
            Branches not in this map route to the output sink.
        """
        return dict(self._branch_to_coalesce)

    def get_branch_to_sink_map(self) -> dict[BranchName, SinkName]:
        """Get fork branches that route directly to sinks (not to coalesce).

        Scans COPY-mode edges from gate nodes to sink nodes to build the
        mapping. Branches that route to coalesce nodes are excluded — they
        are handled by the coalesce executor, not terminal sink routing.

        Returns:
            Dict mapping branch names to their target sink names.
            Empty dict if no fork-to-sink branches exist.
        """
        result: dict[BranchName, SinkName] = {}
        sink_node_to_name: dict[NodeID, SinkName] = {nid: name for name, nid in self._sink_id_map.items()}
        for _from_id, to_id, _key, data in self._graph.edges(data=True, keys=True):
            if data.get("mode") == RoutingMode.COPY and NodeID(to_id) in sink_node_to_name:
                result[BranchName(data["label"])] = sink_node_to_name[NodeID(to_id)]
        return result

    def get_coalesce_gate_index(self) -> dict[CoalesceName, int]:
        """Get coalesce_name -> producing gate pipeline index mapping.

        Returns the pipeline index of the gate that produces each coalesce's
        branches.

        Returns:
            Dict mapping coalesce name to the pipeline index of its producing
            fork gate. Empty dict if no coalesce configured.
        """
        return dict(self._coalesce_gate_index)  # Return copy to prevent mutation

    def get_terminal_sink_map(self) -> dict[NodeID, SinkName]:
        """Get mapping of terminal node IDs to their on_success sink names.

        Scans outgoing edges labelled "on_success" with MOVE mode to build
        the mapping. Terminal nodes are transforms or coalesce nodes that
        route completed rows directly to a sink.

        Returns:
            Dict mapping terminal node IDs to their declared sink names.
            Empty dict if no terminal nodes (e.g., all paths end at gates).
        """
        result: dict[NodeID, SinkName] = {}
        # Invert the sink_id_map for reverse lookup
        sink_node_to_name: dict[NodeID, SinkName] = {node_id: sink_name for sink_name, node_id in self._sink_id_map.items()}
        for from_id, to_id, _key, data in self._graph.edges(data=True, keys=True):
            if data.get("label") == "on_success" and data.get("mode") == RoutingMode.MOVE and NodeID(to_id) in sink_node_to_name:
                result[NodeID(from_id)] = sink_node_to_name[NodeID(to_id)]
        return result

    def get_route_label(self, from_node_id: str, sink_name: str) -> str:
        """Get the route label for an edge from a gate to a sink.

        Args:
            from_node_id: The gate node ID
            sink_name: The sink name (not node ID)

        Returns:
            The route label (e.g., "suspicious") or "continue" for default path
        """
        # Check explicit route mapping first
        if (NodeID(from_node_id), sink_name) in self._route_label_map:
            return self._route_label_map[(NodeID(from_node_id), sink_name)]

        # Default path uses "continue" label
        return "continue"

    def get_route_resolution_map(self) -> dict[tuple[NodeID, str], RouteDestination]:
        """Get the route resolution map for all gates.

        Returns:
            Dict mapping (gate_node_id, route_label) -> destination.
            Destination can be continue, fork, sink, or a processing node.
            Used by the executor to resolve route labels from gates.
        """
        return dict(self._route_resolution_map)

    def validate_edge_compatibility(self) -> None:
        """Validate schema compatibility for all edges in the graph.

        Called AFTER graph construction is complete. Validates that each edge
        connects compatible schemas.

        Raises:
            ValueError: If any edge has incompatible schemas

        Note:
            This is PHASE 2 validation (cross-plugin compatibility). Plugin
            SELF-validation happens in PHASE 1 during plugin construction.
        """
        # Validate each edge (skip divert edges — quarantine/error data doesn't
        # conform to producer schemas because it failed validation or errored)
        for from_id, to_id, edge_data in self._graph.edges(data=True):
            if edge_data["mode"] == RoutingMode.DIVERT:
                continue
            self._validate_single_edge(from_id, to_id)

        # Validate all coalesce nodes (must have compatible schemas from all branches)
        coalesce_nodes = [node_id for node_id, data in self._graph.nodes(data=True) if data["info"].node_type == "coalesce"]
        for coalesce_id in coalesce_nodes:
            self._validate_coalesce_compatibility(coalesce_id)

    def _validate_single_edge(self, from_node_id: str, to_node_id: str) -> None:
        """Validate schema compatibility for a single edge.

        Validation is performed in two phases:
        1. CONTRACT VALIDATION: Check required/guaranteed field names
        2. TYPE VALIDATION: Check field type compatibility

        Contract validation catches missing fields even for dynamic schemas,
        which is critical for template-based transforms (e.g., LLM) that
        reference specific row fields.

        Args:
            from_node_id: Source node ID
            to_node_id: Destination node ID

        Raises:
            ValueError: If schemas are incompatible or contracts violated
        """
        to_info = self.get_node_info(to_node_id)

        # Skip edge validation for coalesce nodes - they have special validation
        # that checks all incoming branches together
        if to_info.node_type == "coalesce":
            return

        # Rule 0: Gates must preserve schema (input == output)
        if (
            to_info.node_type == "gate"
            and to_info.input_schema is not None
            and to_info.output_schema is not None
            and to_info.input_schema != to_info.output_schema
        ):
            raise ValueError(
                f"Gate '{to_node_id}' must preserve schema: "
                f"input_schema={to_info.input_schema.__name__}, "
                f"output_schema={to_info.output_schema.__name__}"
            )

        # ===== PHASE 1: CONTRACT VALIDATION (field name requirements) =====
        # This catches missing fields even for dynamic schemas
        consumer_required = self._get_required_fields(to_node_id)

        if consumer_required:
            # Get effective guaranteed fields (walks through pass-through nodes)
            producer_guaranteed = self._get_effective_guaranteed_fields(from_node_id)

            missing = consumer_required - producer_guaranteed
            if missing:
                # Build actionable error message
                from_info = self.get_node_info(from_node_id)
                raise ValueError(
                    f"Schema contract violation: edge '{from_node_id}' → '{to_node_id}'\n"
                    f"  Consumer ({to_info.plugin_name}) requires fields: {sorted(consumer_required)}\n"
                    f"  Producer ({from_info.plugin_name}) guarantees: "
                    f"{sorted(producer_guaranteed) if producer_guaranteed else '(none - dynamic schema)'}\n"
                    f"  Missing fields: {sorted(missing)}\n"
                    f"\n"
                    f"Fix: Either:\n"
                    f"  1. Add missing fields to producer's schema or guaranteed_fields, or\n"
                    f"  2. Remove from consumer's required_input_fields if truly optional"
                )

        # ===== PHASE 2: TYPE VALIDATION (schema compatibility) =====
        # Get EFFECTIVE producer schema (walks through gates if needed)
        producer_schema = self._get_effective_producer_schema(from_node_id)
        consumer_schema = to_info.input_schema

        # Rule 1: Dynamic schemas (None) bypass type validation
        if producer_schema is None or consumer_schema is None:
            return  # Observed schema - compatible with anything

        # Handle observed schemas (no explicit fields + extra='allow')
        # These are created by _create_dynamic_schema and accept anything
        # NOTE: We control all schemas via PluginSchema base class which sets model_config["extra"].
        # Direct access is correct per Tier 1 trust model - missing key would be our bug.
        producer_is_observed = len(producer_schema.model_fields) == 0 and producer_schema.model_config["extra"] == "allow"
        consumer_is_observed = len(consumer_schema.model_fields) == 0 and consumer_schema.model_config["extra"] == "allow"
        if producer_is_observed or consumer_is_observed:
            return  # Observed schemas bypass static type validation

        # Rule 2: Full compatibility check (missing fields, type mismatches, extra fields)
        result = check_compatibility(producer_schema, consumer_schema)
        if not result.compatible:
            raise ValueError(
                f"Edge from '{from_node_id}' to '{to_node_id}' invalid: "
                f"producer schema '{producer_schema.__name__}' incompatible with "
                f"consumer schema '{consumer_schema.__name__}': {result.error_message}"
            )

    def _get_effective_producer_schema(self, node_id: str) -> type[PluginSchema] | None:
        """Get effective output schema, walking through pass-through nodes (gates, coalesce).

        Gates and coalesce nodes don't transform data - they inherit schema from their
        upstream producers. This method walks backwards through the graph to find the
        nearest schema-carrying producer.

        Args:
            node_id: Node to get effective schema for

        Returns:
            Output schema type, or None if dynamic

        Raises:
            ValueError: If pass-through node has no incoming edges (graph construction bug)
        """
        node_info = self.get_node_info(node_id)

        # If node has output_schema, return it directly
        if node_info.output_schema is not None:
            return node_info.output_schema

        # Node has no schema - check if it's a pass-through type (gate or coalesce)
        if node_info.node_type in ("gate", "coalesce"):
            # Pass-through nodes inherit schema from upstream producers
            incoming = list(self._graph.in_edges(node_id, data=True))

            if not incoming:
                # Pass-through node with no inputs is a graph construction bug - CRASH
                raise ValueError(
                    f"{node_info.node_type.capitalize()} node '{node_id}' has no incoming edges - "
                    f"this indicates a bug in graph construction"
                )

            # Gather all input schemas for validation
            all_schemas: list[tuple[str, type[PluginSchema] | None]] = []
            for from_id, _, _ in incoming:
                schema = self._get_effective_producer_schema(from_id)
                all_schemas.append((from_id, schema))

            # For multi-input nodes, check for mixed observed/explicit schemas first
            # BUG FIX: P2-2026-02-01-dynamic-branch-schema-mismatch-not-detected
            # Mixed observed/explicit branches create semantic mismatches that cause runtime failures
            if len(all_schemas) > 1:
                observed_branches = [(nid, s) for nid, s in all_schemas if self._is_observed_schema(s)]
                explicit_branches = [(nid, s) for nid, s in all_schemas if not self._is_observed_schema(s)]

                if observed_branches and explicit_branches:
                    # Mixed observed/explicit - reject with clear error
                    observed_names = [nid for nid, _ in observed_branches]
                    # Schema is guaranteed non-None here (explicit_branches filtered out observed/None)
                    explicit_names = [f"{nid} ({s.__name__})" for nid, s in explicit_branches if s is not None]
                    raise ValueError(
                        f"{node_info.node_type.capitalize()} '{node_id}' has mixed observed/explicit schemas - "
                        f"this is not allowed because observed branches may produce rows missing fields "
                        f"expected by downstream consumers. "
                        f"Observed branches: {observed_names}, explicit branches: {explicit_names}. "
                        f"Fix: ensure all branches produce explicit schemas with compatible fields, "
                        f"or all branches produce observed schemas."
                    )

                # All explicit - verify structural compatibility
                if len(explicit_branches) > 1:
                    _first_id, first_schema = explicit_branches[0]
                    for _other_id, other_schema in explicit_branches[1:]:
                        compatible, error_msg = self._schemas_structurally_compatible(first_schema, other_schema)
                        if not compatible:
                            # Schemas are guaranteed non-None here (explicit_branches filtered out observed/None)
                            first_name = first_schema.__name__ if first_schema is not None else "observed"
                            other_name = other_schema.__name__ if other_schema is not None else "observed"
                            raise ValueError(
                                f"{node_info.node_type.capitalize()} '{node_id}' receives incompatible schemas from "
                                f"multiple inputs - this is a graph construction bug. "
                                f"First input: {first_name}, other input: {other_name}. {error_msg}"
                            )

            # Return first schema (all are now either all-observed or all-explicit-compatible)
            return all_schemas[0][1]

        # Not a pass-through node and no schema - return None (observed)
        return None

    def _is_observed_schema(self, schema: type[PluginSchema] | None) -> bool:
        """Check if a schema is observed (accepts any fields, types inferred from data).

        A schema is observed if:
        - It is None (unspecified output_schema)
        - It has no fields and allows extra fields (structural observed)

        Args:
            schema: Schema class or None

        Returns:
            True if schema is observed, False if explicit (fixed/flexible)
        """
        if schema is None:
            return True

        # Structural observed: no fields + extra="allow"
        # NOTE: We control all schemas via PluginSchema base class which sets model_config["extra"].
        # Direct access is correct per Tier 1 trust model - missing key would be our bug.
        return len(schema.model_fields) == 0 and schema.model_config["extra"] == "allow"

    def _schemas_structurally_compatible(
        self, schema_a: type[PluginSchema] | None, schema_b: type[PluginSchema] | None
    ) -> tuple[bool, str]:
        """Check if two schemas are structurally compatible (not by class identity).

        Uses check_compatibility() for structural comparison. Handles observed schemas
        which are compatible with anything.

        Args:
            schema_a: First schema (or None for observed)
            schema_b: Second schema (or None for observed)

        Returns:
            Tuple of (is_compatible, error_message). If compatible, error_message is empty.
        """
        # Both observed - compatible
        if self._is_observed_schema(schema_a) and self._is_observed_schema(schema_b):
            return True, ""

        # One observed, one explicit - for general compatibility, allow this
        # (Pass-through nodes use stricter checking via _check_passthrough_schema_homogeneity)
        if self._is_observed_schema(schema_a) or self._is_observed_schema(schema_b):
            return True, ""

        # Both explicit schemas - same class is trivially compatible
        if schema_a is schema_b:
            return True, ""

        # At this point both schemas are explicit (not None, not dynamic)
        # Type narrowing for mypy: we've already returned if either is dynamic/None
        assert schema_a is not None and schema_b is not None

        # Both explicit schemas - use bidirectional structural comparison
        # For coalesce/pass-through nodes, schemas must be mutually compatible
        result_ab = check_compatibility(schema_a, schema_b)
        result_ba = check_compatibility(schema_b, schema_a)

        if result_ab.compatible and result_ba.compatible:
            return True, ""

        # Build error message showing what's incompatible
        errors = []
        if not result_ab.compatible:
            errors.append(f"{schema_a.__name__} -> {schema_b.__name__}: {result_ab.error_message}")
        if not result_ba.compatible:
            errors.append(f"{schema_b.__name__} -> {schema_a.__name__}: {result_ba.error_message}")
        return False, "; ".join(errors)

    def _validate_coalesce_compatibility(self, coalesce_id: str) -> None:
        """Validate all inputs to coalesce node have compatible schemas.

        Args:
            coalesce_id: Coalesce node ID

        Raises:
            ValueError: If branches have incompatible schemas
        """
        incoming = list(self._graph.in_edges(coalesce_id, data=True))

        if len(incoming) < 2:
            return  # Degenerate case (1 branch) - always compatible

        # Get effective schema from first branch
        first_edge_source = incoming[0][0]
        first_schema = self._get_effective_producer_schema(first_edge_source)

        # Verify all other branches have structurally compatible schemas
        # Note: Uses structural comparison, not class identity (P2-2026-01-30 fix)
        for from_id, _, _ in incoming[1:]:
            other_schema = self._get_effective_producer_schema(from_id)
            compatible, error_msg = self._schemas_structurally_compatible(first_schema, other_schema)
            if not compatible:
                first_name = first_schema.__name__ if first_schema else "observed"
                other_name = other_schema.__name__ if other_schema else "observed"
                raise ValueError(
                    f"Coalesce '{coalesce_id}' receives incompatible schemas from "
                    f"multiple branches: first branch has {first_name}, "
                    f"branch from '{from_id}' has {other_name}. {error_msg}"
                )

    # ===== CONTRACT VALIDATION HELPERS =====

    def _get_schema_config_from_node(self, node_id: str) -> SchemaConfig | None:
        """Extract SchemaConfig from node.

        Priority:
        1. output_schema_config from NodeInfo (computed by transform)
        2. schema from config dict (raw config)

        Transforms may compute their schema config dynamically (e.g., LLM transforms
        determine guaranteed_fields and audit_fields from their configuration). When
        this computed schema config is available in NodeInfo, it takes precedence
        over the raw config dict.

        Args:
            node_id: Node ID to get schema config from

        Returns:
            SchemaConfig if available, None if schema not in config
        """
        node_info = self.get_node_info(node_id)

        # First check if we have computed schema config in NodeInfo
        # (populated by from_plugin_instances when transform has _output_schema_config)
        if node_info.output_schema_config is not None:
            return node_info.output_schema_config

        # Fall back to parsing from raw config dict
        schema_dict = node_info.config.get("schema")
        if schema_dict is None:
            return None

        # Parse the schema dict into SchemaConfig
        # Handle raw dict form (schema_dict should always be a dict now)
        if isinstance(schema_dict, dict):
            return SchemaConfig.from_dict(schema_dict)

        return None

    def _get_guaranteed_fields(self, node_id: str) -> frozenset[str]:
        """Get fields that a node guarantees in its output.

        Priority:
        1. Explicit guaranteed_fields in schema config
        2. Declared fields in flexible/fixed mode schemas
        3. Empty set for observed schemas

        Args:
            node_id: Node ID to get guarantees from

        Returns:
            Frozenset of field names the node guarantees to output
        """
        schema_config = self._get_schema_config_from_node(node_id)

        if schema_config is None:
            return frozenset()

        return schema_config.get_effective_guaranteed_fields()

    def _get_required_fields(self, node_id: str) -> frozenset[str]:
        """Get fields that a node EXPLICITLY requires in its input.

        This returns only explicit contract declarations, not implicit
        requirements from typed schemas. The existing type validation
        handles typed schema compatibility separately.

        Priority:
        1. Explicit required_input_fields from plugin config (TransformDataConfig)
        2. Explicit required_fields in schema config

        Note: This deliberately does NOT include implicit requirements from
        strict/free mode schemas. Those are handled by type validation, which
        correctly skips validation when either side is dynamic.

        Args:
            node_id: Node ID to get requirements from

        Returns:
            Frozenset of field names explicitly required
        """
        node_info = self.get_node_info(node_id)

        # Check plugin config for required_input_fields (highest priority)
        # This is the explicit declaration from TransformDataConfig
        required_input = node_info.config.get("required_input_fields")
        if required_input is not None and len(required_input) > 0:
            return frozenset(required_input)

        # For aggregation nodes, also check inside "options" where transform config is nested
        if node_info.node_type == "aggregation":
            options = node_info.config["options"]
            if not isinstance(options, dict):
                raise TypeError(f"Aggregation node config 'options' must be dict, got {type(options).__name__}")
            if "required_input_fields" in options:
                required_input = options["required_input_fields"]
                if required_input is not None and len(required_input) > 0:
                    return frozenset(required_input)

        # Check for explicit required_fields in schema config
        schema_config = self._get_schema_config_from_node(node_id)

        if schema_config is None:
            return frozenset()

        # Only return explicit required_fields declaration, NOT implicit from typed schemas
        if schema_config.required_fields is not None:
            return frozenset(schema_config.required_fields)

        return frozenset()

    def _get_effective_guaranteed_fields(self, node_id: str) -> frozenset[str]:
        """Get effective output guarantees, walking through pass-through nodes.

        Gates and coalesce nodes don't transform data - they inherit guarantees
        from their upstream producers. This method walks backwards through the
        graph to find actual guarantees.

        For coalesce nodes, returns the intersection of all branch guarantees
        (only fields guaranteed by ALL branches are guaranteed after merge).

        IMPORTANT: Gates ALWAYS inherit from upstream, even if they have raw schema
        guarantees. This is because gates copy raw config["schema"] from upstream,
        which may not include computed guarantees from output_schema_config
        (e.g., LLM transforms compute additional guaranteed_fields like *_usage).
        See P1-2026-01-31-gate-drops-computed-schema-guarantees for details.

        Args:
            node_id: Node to get effective guarantees for

        Returns:
            Frozenset of field names effectively guaranteed at this point
        """
        node_info = self.get_node_info(node_id)

        # Gates ALWAYS inherit from upstream - they don't compute schemas.
        # Their raw config["schema"] may miss computed guarantees from upstream's
        # output_schema_config (e.g., LLM *_usage fields).
        if node_info.node_type == "gate":
            incoming = list(self._graph.in_edges(node_id, data=True))
            if not incoming:
                return frozenset()
            # Gates pass through - inherit from single upstream
            return self._get_effective_guaranteed_fields(incoming[0][0])

        # Coalesce nodes return intersection of branch guarantees
        if node_info.node_type == "coalesce":
            incoming = list(self._graph.in_edges(node_id, data=True))
            if not incoming:
                return frozenset()
            # Coalesce guarantees the INTERSECTION of branch guarantees
            branch_guarantees = [self._get_effective_guaranteed_fields(from_id) for from_id, _, _ in incoming]
            if not branch_guarantees:
                return frozenset()
            # Start with first, intersect with rest
            result = branch_guarantees[0]
            for guarantees in branch_guarantees[1:]:
                result = result & guarantees
            return result

        # Non-pass-through nodes return their own guarantees
        return self._get_guaranteed_fields(node_id)
