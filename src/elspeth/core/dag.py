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
    from elspeth.core.config import AggregationSettings, CoalesceSettings, GateSettings
    from elspeth.plugins.protocols import SinkProtocol, SourceProtocol, TransformProtocol


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
        """Validate the execution graph structure.

        Validates:
        1. Graph is acyclic (no cycles)
        2. Exactly one source node exists
        3. At least one sink node exists
        4. Edge labels are unique per source node

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
        transforms: list[TransformProtocol],
        sinks: dict[str, SinkProtocol],
        aggregations: dict[str, tuple[TransformProtocol, AggregationSettings]],
        gates: list[GateSettings],
        output_sink: str,
        coalesce_settings: list[CoalesceSettings] | None = None,
    ) -> ExecutionGraph:
        """Build ExecutionGraph from plugin instances.

        CORRECT method for graph construction - enables schema validation.
        Schemas extracted directly from instance attributes.

        Args:
            source: Instantiated source plugin
            transforms: Instantiated transforms (row_plugins only, NOT aggregations)
            sinks: Dict of sink_name -> instantiated sink
            aggregations: Dict of agg_name -> (transform_instance, AggregationSettings)
            gates: Config-driven gate settings
            output_sink: Default output sink name
            coalesce_settings: Coalesce configs for fork/join patterns

        Returns:
            ExecutionGraph with schemas populated

        Raises:
            GraphValidationError: If gate routes reference unknown sinks
        """
        import hashlib

        from elspeth.core.canonical import canonical_json

        graph = cls()

        def node_id(prefix: str, name: str, config: dict[str, Any], sequence: int | None = None) -> str:
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
                return f"{prefix}_{name}_{config_hash}_{sequence}"
            return f"{prefix}_{name}_{config_hash}"

        # Add source - extract schema from instance
        source_config = source.config  # type: ignore[attr-defined]
        source_id = node_id("source", source.name, source_config)
        graph.add_node(
            source_id,
            node_type="source",
            plugin_name=source.name,
            config=source_config,
            output_schema=source.output_schema,  # SourceProtocol requires this
        )

        # Add sinks
        sink_ids: dict[str, str] = {}
        for sink_name, sink in sinks.items():
            sink_config = sink.config  # type: ignore[attr-defined]
            sid = node_id("sink", sink_name, sink_config)
            sink_ids[sink_name] = sid
            graph.add_node(
                sid,
                node_type="sink",
                plugin_name=sink.name,
                config=sink_config,
                input_schema=sink.input_schema,  # SinkProtocol requires this
            )

        graph._sink_id_map = dict(sink_ids)
        graph._output_sink = output_sink

        # Build transform chain
        transform_ids: dict[int, str] = {}
        prev_node_id = source_id

        for i, transform in enumerate(transforms):
            transform_config = transform.config  # type: ignore[attr-defined]
            # Include sequence to prevent ID collisions when configs are identical
            tid = node_id("transform", transform.name, transform_config, sequence=i)
            transform_ids[i] = tid

            graph.add_node(
                tid,
                node_type="transform",
                plugin_name=transform.name,
                config=transform_config,
                input_schema=transform.input_schema,  # TransformProtocol requires this
                output_schema=transform.output_schema,  # TransformProtocol requires this
            )

            graph.add_edge(prev_node_id, tid, label="continue", mode=RoutingMode.MOVE)
            prev_node_id = tid

        graph._transform_id_map = transform_ids

        # Build aggregations - dual schemas
        aggregation_ids: dict[str, str] = {}
        for agg_name, (transform, agg_config) in aggregations.items():
            agg_node_config = {
                "trigger": agg_config.trigger.model_dump(),
                "output_mode": agg_config.output_mode,
                "options": dict(agg_config.options),
            }
            aid = node_id("aggregation", agg_name, agg_node_config)
            aggregation_ids[agg_name] = aid

            graph.add_node(
                aid,
                node_type="aggregation",
                plugin_name=agg_config.plugin,
                config=agg_node_config,
                input_schema=transform.input_schema,  # TransformProtocol requires this (aggregations use transforms)
                output_schema=transform.output_schema,  # TransformProtocol requires this (aggregations use transforms)
            )

            graph.add_edge(prev_node_id, aid, label="continue", mode=RoutingMode.MOVE)
            prev_node_id = aid

        graph._aggregation_id_map = aggregation_ids

        # Build gates (config-driven, no instances)
        config_gate_ids: dict[str, str] = {}
        gate_sequence: list[tuple[str, GateSettings]] = []

        for gate_config in gates:
            gate_node_config = {
                "condition": gate_config.condition,
                "routes": dict(gate_config.routes),
            }
            if gate_config.fork_to:
                gate_node_config["fork_to"] = list(gate_config.fork_to)

            gid = node_id("config_gate", gate_config.name, gate_node_config)
            config_gate_ids[gate_config.name] = gid

            graph.add_node(
                gid,
                node_type="gate",
                plugin_name=f"config_gate:{gate_config.name}",
                config=gate_node_config,
            )

            graph.add_edge(prev_node_id, gid, label="continue", mode=RoutingMode.MOVE)
            prev_node_id = gid  # Advance chain to this gate

            # Gate routes to sinks
            for route_label, target in gate_config.routes.items():
                if target == "continue":
                    graph._route_resolution_map[(gid, route_label)] = "continue"
                elif target == "fork":
                    # Fork is a special routing mode - handled by fork_to branches
                    graph._route_resolution_map[(gid, route_label)] = "fork"
                else:
                    if target not in sink_ids:
                        raise GraphValidationError(f"Gate '{gate_config.name}' route '{route_label}' references unknown sink '{target}'")
                    target_sink_id = sink_ids[target]
                    graph.add_edge(gid, target_sink_id, label=route_label, mode=RoutingMode.MOVE)
                    graph._route_label_map[(gid, target)] = route_label
                    graph._route_resolution_map[(gid, route_label)] = target

            gate_sequence.append((gid, gate_config))

        graph._config_gate_id_map = config_gate_ids

        # ===== COALESCE IMPLEMENTATION (BUILD NODES AND MAPPINGS FIRST) =====
        # Build coalesce nodes BEFORE connecting gates (needed for branch routing)
        if coalesce_settings:
            coalesce_ids: dict[str, str] = {}
            branch_to_coalesce: dict[str, str] = {}

            for coalesce_config in coalesce_settings:
                # Coalesce merges - no schema transformation
                # Note: Pydantic validates min_length=2 for branches field
                config_dict: dict[str, Any] = {
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
                coalesce_ids[coalesce_config.name] = cid

                # Map branches to this coalesce - check for duplicates
                for branch_name in coalesce_config.branches:
                    if branch_name in branch_to_coalesce:
                        # Branch already mapped to another coalesce
                        existing_coalesce = branch_to_coalesce[branch_name]
                        raise GraphValidationError(
                            f"Duplicate branch name '{branch_name}' found in coalesce settings.\n"
                            f"Branch '{branch_name}' is already mapped to coalesce '{existing_coalesce}', "
                            f"but coalesce '{coalesce_config.name}' also declares it.\n"
                            f"Each fork branch can only merge at one coalesce point."
                        )
                    branch_to_coalesce[branch_name] = coalesce_config.name

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
        for gate_id, gate_config in gate_sequence:
            if gate_config.fork_to:
                for branch_name in gate_config.fork_to:
                    if branch_name in branch_to_coalesce:
                        # Explicit coalesce destination
                        coalesce_name = branch_to_coalesce[branch_name]
                        coalesce_id = coalesce_ids[coalesce_name]
                        graph.add_edge(gate_id, coalesce_id, label=branch_name, mode=RoutingMode.COPY)
                    elif branch_name in sink_ids:
                        # Explicit sink destination (branch name matches sink name)
                        graph.add_edge(gate_id, sink_ids[branch_name], label=branch_name, mode=RoutingMode.COPY)
                    else:
                        # NO FALLBACK - this is a configuration error
                        raise GraphValidationError(
                            f"Gate '{gate_config.name}' has fork branch '{branch_name}' with no destination.\n"
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
            for _gate_id, gate_config in gate_sequence:
                if gate_config.fork_to:
                    produced_branches.update(gate_config.fork_to)

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

        # ===== CONNECT GATE CONTINUE ROUTES =====
        # CRITICAL FIX: Handle ALL continue routes, not just "true"
        for i, (gid, gate_config) in enumerate(gate_sequence):
            # Check if ANY route resolves to "continue"
            has_continue_route = any(target == "continue" for target in gate_config.routes.values())

            if has_continue_route:
                # Determine next node in chain
                if i + 1 < len(gate_sequence):
                    next_node_id = gate_sequence[i + 1][0]
                else:
                    if output_sink not in sink_ids:
                        raise GraphValidationError(
                            f"Gate '{gate_config.name}' has 'continue' route but is the last gate "
                            f"and output_sink '{output_sink}' is not in configured sinks. "
                            f"Available sinks: {sorted(sink_ids.keys())}"
                        )
                    next_node_id = sink_ids[output_sink]

                if not graph._graph.has_edge(gid, next_node_id, key="continue"):
                    graph.add_edge(gid, next_node_id, label="continue", mode=RoutingMode.MOVE)

        # ===== CONNECT FINAL NODE TO OUTPUT (NO GATES CASE) =====
        if not gates and output_sink in sink_ids:
            graph.add_edge(prev_node_id, sink_ids[output_sink], label="continue", mode=RoutingMode.MOVE)

        # ===== CONNECT COALESCE TO OUTPUT =====
        if coalesce_settings:
            for coalesce_id in coalesce_ids.values():
                if output_sink in sink_ids:
                    graph.add_edge(coalesce_id, sink_ids[output_sink], label="continue", mode=RoutingMode.MOVE)

        # PHASE 2 VALIDATION: Validate schema compatibility AFTER graph is built
        graph.validate_edge_compatibility()

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
        # Validate each edge
        for from_id, to_id, _edge_data in self._graph.edges(data=True):
            self._validate_single_edge(from_id, to_id)

        # Validate all coalesce nodes (must have compatible schemas from all branches)
        coalesce_nodes = [node_id for node_id, data in self._graph.nodes(data=True) if data["info"].node_type == "coalesce"]
        for coalesce_id in coalesce_nodes:
            self._validate_coalesce_compatibility(coalesce_id)

    def _validate_single_edge(self, from_node_id: str, to_node_id: str) -> None:
        """Validate schema compatibility for a single edge.

        Args:
            from_node_id: Source node ID
            to_node_id: Destination node ID

        Raises:
            ValueError: If schemas are incompatible
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

        # Get EFFECTIVE producer schema (walks through gates if needed)
        producer_schema = self._get_effective_producer_schema(from_node_id)
        consumer_schema = to_info.input_schema

        # Rule 1: Dynamic schemas (None) bypass validation
        if producer_schema is None or consumer_schema is None:
            return  # Dynamic schema - compatible with anything

        # Rule 2: Check field compatibility
        missing_fields = self._get_missing_required_fields(producer_schema, consumer_schema)
        if missing_fields:
            raise ValueError(
                f"Edge from '{from_node_id}' to '{to_node_id}' invalid: "
                f"producer schema '{producer_schema.__name__}' missing required fields "
                f"for consumer schema '{consumer_schema.__name__}': {missing_fields}"
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

            # Get effective schema from first input (recursive for chained pass-through nodes)
            first_edge_source = incoming[0][0]
            first_schema = self._get_effective_producer_schema(first_edge_source)

            # For multi-input nodes, verify all inputs have same schema
            if len(incoming) > 1:
                for from_id, _, _ in incoming[1:]:
                    other_schema = self._get_effective_producer_schema(from_id)
                    if first_schema != other_schema:
                        # Multi-input pass-through nodes with incompatible schemas - CRASH
                        raise ValueError(
                            f"{node_info.node_type.capitalize()} '{node_id}' receives incompatible schemas from "
                            f"multiple inputs - this is a graph construction bug. "
                            f"First input schema: {first_schema}, "
                            f"Other input schema: {other_schema}"
                        )

            return first_schema

        # Not a pass-through node and no schema - return None (dynamic)
        return None

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

        # Verify all other branches have same schema
        for from_id, _, _ in incoming[1:]:
            other_schema = self._get_effective_producer_schema(from_id)
            if first_schema != other_schema:
                raise ValueError(
                    f"Coalesce '{coalesce_id}' receives incompatible schemas from "
                    f"multiple branches: "
                    f"first branch has {first_schema.__name__ if first_schema else 'dynamic'}, "
                    f"branch from '{from_id}' has {other_schema.__name__ if other_schema else 'dynamic'}"
                )

    def _get_missing_required_fields(
        self,
        producer_schema: type[PluginSchema] | None,
        consumer_schema: type[PluginSchema] | None,
    ) -> list[str]:
        """Get required fields that producer doesn't provide.

        Args:
            producer_schema: Schema of data producer
            consumer_schema: Schema of data consumer

        Returns:
            List of field names missing from producer
        """
        if producer_schema is None or consumer_schema is None:
            return []  # Dynamic schema

        # Check if either schema is dynamic (no fields + extra='allow')
        # Dynamic schemas created by _create_dynamic_schema have no fields and extra='allow'
        producer_is_dynamic = len(producer_schema.model_fields) == 0 and producer_schema.model_config.get("extra") == "allow"
        consumer_is_dynamic = len(consumer_schema.model_fields) == 0 and consumer_schema.model_config.get("extra") == "allow"

        if producer_is_dynamic or consumer_is_dynamic:
            return []  # Dynamic schema - compatible with anything

        producer_fields = set(producer_schema.model_fields.keys())
        consumer_required = {name for name, field in consumer_schema.model_fields.items() if field.is_required()}

        return sorted(consumer_required - producer_fields)
