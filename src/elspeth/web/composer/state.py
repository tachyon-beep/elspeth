"""CompositionState and supporting data models for pipeline composition.

All dataclasses are frozen with slots. Container fields (options, routes,
fork_to, branches) are deep-frozen via freeze_fields() in __post_init__.
Mutation methods return new instances — they never modify the original.

Layer: L3 (application). Imports from L0 (contracts.freeze) only.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any, Self

from elspeth.contracts.freeze import freeze_fields


@dataclass(frozen=True, slots=True)
class PipelineMetadata:
    """Pipeline-level metadata.

    All fields are scalars or None. frozen=True is sufficient.
    """

    name: str = "Untitled Pipeline"
    description: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Self:
        """Reconstruct from a plain dict (inverse of to_dict serialisation)."""
        return cls(
            name=d.get("name", "Untitled Pipeline"),
            description=d.get("description", ""),
        )


@dataclass(frozen=True, slots=True)
class SourceSpec:
    """Pipeline source configuration.

    Attributes:
        plugin: Source plugin name (e.g. "csv", "json", "dataverse").
        on_success: Named connection point for the first downstream node.
        options: Plugin-specific configuration (path, schema, etc.).
        on_validation_failure: How to handle rows that fail schema validation.
    """

    plugin: str
    on_success: str
    options: Mapping[str, Any]
    on_validation_failure: str

    def __post_init__(self) -> None:
        freeze_fields(self, "options")

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Self:
        """Reconstruct from a plain dict (inverse of to_dict serialisation)."""
        return cls(
            plugin=d["plugin"],
            on_success=d["on_success"],
            options=d["options"],
            on_validation_failure=d["on_validation_failure"],
        )


@dataclass(frozen=True, slots=True)
class NodeSpec:
    """Transform, gate, aggregation, or coalesce node.

    Attributes:
        id: Unique node identifier within the pipeline.
        node_type: One of "transform", "gate", "aggregation", "coalesce".
        plugin: Plugin name. None for gates and coalesces.
        input: Named connection point this node reads from.
        on_success: Named connection point for successful output. None for gates.
        on_error: Named connection point for error output. None if not diverted.
        options: Plugin-specific configuration.
        condition: Gate expression. None for non-gates.
        routes: Gate route mapping. None for non-gates.
        fork_to: Fork destinations for fork gates. None for non-fork nodes.
        branches: Branch inputs for coalesce nodes. None for non-coalesce nodes.
        policy: Coalesce policy. None for non-coalesce nodes.
        merge: Coalesce merge strategy. None for non-coalesce nodes.
    """

    id: str
    node_type: str
    plugin: str | None
    input: str
    on_success: str | None
    on_error: str | None
    options: Mapping[str, Any]
    condition: str | None
    routes: Mapping[str, str] | None
    fork_to: tuple[str, ...] | None
    branches: tuple[str, ...] | None
    policy: str | None
    merge: str | None

    def __post_init__(self) -> None:
        freeze_fields(self, "options")
        if self.routes is not None:
            freeze_fields(self, "routes")

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Self:
        """Reconstruct from a plain dict (inverse of to_dict serialisation).

        Optional fields (condition, routes, fork_to, branches, policy, merge)
        default to None when absent from the dict. fork_to and branches are
        converted from list to tuple since to_dict() serialises tuples as lists.
        """
        fork_to = d.get("fork_to")
        branches = d.get("branches")
        return cls(
            id=d["id"],
            node_type=d["node_type"],
            plugin=d["plugin"],
            input=d["input"],
            on_success=d["on_success"],
            on_error=d["on_error"],
            options=d["options"],
            condition=d.get("condition"),
            routes=d.get("routes"),
            fork_to=tuple(fork_to) if fork_to is not None else None,
            branches=tuple(branches) if branches is not None else None,
            policy=d.get("policy"),
            merge=d.get("merge"),
        )


@dataclass(frozen=True, slots=True)
class EdgeSpec:
    """Connection between two nodes.

    Attributes:
        id: Unique edge identifier.
        from_node: Source node ID (or "source" for the pipeline source).
        to_node: Destination node ID or sink name.
        edge_type: One of "on_success", "on_error", "route_true", "route_false", "fork".
        label: Display label (e.g. the route key for gate edges).
    """

    id: str
    from_node: str
    to_node: str
    edge_type: str
    label: str | None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Self:
        """Reconstruct from a plain dict (inverse of to_dict serialisation)."""
        return cls(
            id=d["id"],
            from_node=d["from_node"],
            to_node=d["to_node"],
            edge_type=d["edge_type"],
            label=d["label"],
        )


@dataclass(frozen=True, slots=True)
class OutputSpec:
    """Sink configuration.

    Attributes:
        name: Sink name (used as connection point in edges and routes).
        plugin: Sink plugin name (e.g. "csv", "json", "database").
        options: Plugin-specific configuration.
        on_write_failure: How to handle write failures ("discard" or "quarantine").
    """

    name: str
    plugin: str
    options: Mapping[str, Any]
    on_write_failure: str

    def __post_init__(self) -> None:
        freeze_fields(self, "options")

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Self:
        """Reconstruct from a plain dict (inverse of to_dict serialisation)."""
        return cls(
            name=d["name"],
            plugin=d["plugin"],
            options=d["options"],
            on_write_failure=d["on_write_failure"],
        )


@dataclass(frozen=True, slots=True)
class ValidationSummary:
    """Stage 1 validation result.

    errors is a tuple of human-readable strings. frozen=True is sufficient
    since tuples of strings are immutable.
    """

    is_valid: bool
    errors: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CompositionState:
    """Immutable, versioned snapshot of a pipeline under construction.

    Every edit produces a new instance with incremented version.
    All container fields are deep-frozen via freeze_fields().

    Attributes:
        source: The pipeline's single data source. None until set.
        nodes: Ordered tuple of transform, gate, aggregation, coalesce nodes.
        edges: Connections between nodes.
        outputs: Sink configurations.
        metadata: Pipeline name and description.
        version: Monotonically increasing per session, starting at 1.
    """

    source: SourceSpec | None
    nodes: tuple[NodeSpec, ...]
    edges: tuple[EdgeSpec, ...]
    outputs: tuple[OutputSpec, ...]
    metadata: PipelineMetadata
    version: int

    def __post_init__(self) -> None:
        # nodes, edges, outputs are tuples of frozen dataclasses — tuple is
        # already immutable and contents are individually frozen. No freeze
        # guard needed. metadata is a frozen dataclass with scalar-only fields.
        # Source is a frozen dataclass with its own freeze guard.
        # Nothing to freeze here beyond what frozen=True provides.
        pass

    # --- Mutation methods ---

    def with_source(self, source: SourceSpec) -> CompositionState:
        """Return new state with the given source, version incremented."""
        return replace(self, source=source, version=self.version + 1)

    def with_node(self, node: NodeSpec) -> CompositionState:
        """Add or replace a node (matched by id). Version incremented."""
        existing_ids = [n.id for n in self.nodes]
        if node.id in existing_ids:
            # Replace at original position to preserve order
            idx = existing_ids.index(node.id)
            node_list = list(self.nodes)
            node_list[idx] = node
            nodes = tuple(node_list)
        else:
            # Append new node
            nodes = (*self.nodes, node)
        return replace(self, nodes=nodes, version=self.version + 1)

    def without_node(self, node_id: str) -> CompositionState | None:
        """Remove node by id. Returns None if node not found."""
        if not any(n.id == node_id for n in self.nodes):
            return None
        nodes = tuple(n for n in self.nodes if n.id != node_id)
        # Also remove edges referencing this node
        edges = tuple(e for e in self.edges if e.from_node != node_id and e.to_node != node_id)
        return replace(self, nodes=nodes, edges=edges, version=self.version + 1)

    def with_edge(self, edge: EdgeSpec) -> CompositionState:
        """Add or replace an edge (matched by id). Version incremented."""
        edges = (*tuple(e for e in self.edges if e.id != edge.id), edge)
        return replace(self, edges=edges, version=self.version + 1)

    def without_edge(self, edge_id: str) -> CompositionState | None:
        """Remove edge by id. Returns None if edge not found."""
        if not any(e.id == edge_id for e in self.edges):
            return None
        edges = tuple(e for e in self.edges if e.id != edge_id)
        return replace(self, edges=edges, version=self.version + 1)

    def with_output(self, output: OutputSpec) -> CompositionState:
        """Add or replace an output (matched by name). Version incremented."""
        outputs = (*tuple(o for o in self.outputs if o.name != output.name), output)
        return replace(self, outputs=outputs, version=self.version + 1)

    def without_output(self, output_name: str) -> CompositionState | None:
        """Remove output by name. Returns None if output not found."""
        if not any(o.name == output_name for o in self.outputs):
            return None
        outputs = tuple(o for o in self.outputs if o.name != output_name)
        return replace(self, outputs=outputs, version=self.version + 1)

    def with_metadata(self, patch: dict[str, Any]) -> CompositionState:
        """Update metadata fields from partial dict. Version incremented."""
        current = self.metadata
        new_meta = PipelineMetadata(
            name=patch.get("name", current.name),
            description=patch.get("description", current.description),
        )
        return replace(self, metadata=new_meta, version=self.version + 1)

    # --- Serialization ---

    def to_dict(self) -> dict[str, Any]:
        """Recursively unwrap frozen containers to plain Python types.

        Converts MappingProxyType -> dict, tuple -> list recursively.
        The result is suitable for yaml.dump() and JSON serialization.
        """

        def _unfreeze(obj: Any) -> Any:
            if isinstance(obj, Mapping):
                return {k: _unfreeze(v) for k, v in obj.items()}
            if isinstance(obj, (tuple, list)):
                return [_unfreeze(item) for item in obj]
            return obj

        result: dict[str, Any] = {
            "version": self.version,
            "metadata": {
                "name": self.metadata.name,
                "description": self.metadata.description,
            },
            "source": None,
            "nodes": [],
            "edges": [],
            "outputs": [],
        }

        if self.source is not None:
            result["source"] = {
                "plugin": self.source.plugin,
                "on_success": self.source.on_success,
                "options": _unfreeze(self.source.options),
                "on_validation_failure": self.source.on_validation_failure,
            }

        for node in self.nodes:
            node_dict: dict[str, Any] = {
                "id": node.id,
                "node_type": node.node_type,
                "plugin": node.plugin,
                "input": node.input,
                "on_success": node.on_success,
                "on_error": node.on_error,
                "options": _unfreeze(node.options),
            }
            if node.condition is not None:
                node_dict["condition"] = node.condition
            if node.routes is not None:
                node_dict["routes"] = _unfreeze(node.routes)
            if node.fork_to is not None:
                node_dict["fork_to"] = list(node.fork_to)
            if node.branches is not None:
                node_dict["branches"] = list(node.branches)
            if node.policy is not None:
                node_dict["policy"] = node.policy
            if node.merge is not None:
                node_dict["merge"] = node.merge
            result["nodes"].append(node_dict)

        for edge in self.edges:
            result["edges"].append(
                {
                    "id": edge.id,
                    "from_node": edge.from_node,
                    "to_node": edge.to_node,
                    "edge_type": edge.edge_type,
                    "label": edge.label,
                }
            )

        for output in self.outputs:
            result["outputs"].append(
                {
                    "name": output.name,
                    "plugin": output.plugin,
                    "options": _unfreeze(output.options),
                    "on_write_failure": output.on_write_failure,
                }
            )

        return result

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Self:
        """Reconstruct from a plain dict (inverse of to_dict serialisation).

        Calls from_dict() on each nested Spec type. This is the only way
        to construct CompositionState from deserialised JSON (Spec AC #18).
        The round-trip invariant holds:
            state == CompositionState.from_dict(state.to_dict())
        """
        source_data = d["source"]
        return cls(
            source=SourceSpec.from_dict(source_data) if source_data is not None else None,
            nodes=tuple(NodeSpec.from_dict(n) for n in d["nodes"]),
            edges=tuple(EdgeSpec.from_dict(e) for e in d["edges"]),
            outputs=tuple(OutputSpec.from_dict(o) for o in d["outputs"]),
            metadata=PipelineMetadata.from_dict(d["metadata"]),
            version=d["version"],
        )

    # --- Validation ---

    def validate(self) -> ValidationSummary:
        """Run Stage 1 composition-time validation.

        Pure function of the current state — no catalog or engine consultation.
        Returns ValidationSummary with is_valid and human-readable errors.
        """
        errors: list[str] = []

        # 1. Source exists
        if self.source is None:
            errors.append("No source configured.")

        # 2. At least one output
        if not self.outputs:
            errors.append("No sinks configured.")

        # 3. Edge references valid
        node_ids = {n.id for n in self.nodes}
        output_names = {o.name for o in self.outputs}
        valid_from = node_ids | {"source"}
        valid_to = node_ids | output_names
        for edge in self.edges:
            if edge.from_node not in valid_from:
                errors.append(f"Edge '{edge.id}' references unknown node '{edge.from_node}' as from_node.")
            if edge.to_node not in valid_to:
                errors.append(f"Edge '{edge.id}' references unknown node '{edge.to_node}' as to_node.")

        # 4. Node IDs unique
        seen_node_ids: set[str] = set()
        for node in self.nodes:
            if node.id in seen_node_ids:
                errors.append(f"Duplicate node ID: '{node.id}'.")
            seen_node_ids.add(node.id)

        # 5. Output names unique
        seen_output_names: set[str] = set()
        for output in self.outputs:
            if output.name in seen_output_names:
                errors.append(f"Duplicate output name: '{output.name}'.")
            seen_output_names.add(output.name)

        # 6. Edge IDs unique
        seen_edge_ids: set[str] = set()
        for edge in self.edges:
            if edge.id in seen_edge_ids:
                errors.append(f"Duplicate edge ID: '{edge.id}'.")
            seen_edge_ids.add(edge.id)

        # 7. Node type field consistency
        for node in self.nodes:
            if node.node_type == "gate":
                if node.condition is None:
                    errors.append(f"Gate '{node.id}' is missing required field 'condition'.")
                if node.routes is None:
                    errors.append(f"Gate '{node.id}' is missing required field 'routes'.")
            elif node.node_type == "transform":
                if node.condition is not None:
                    errors.append(f"Transform '{node.id}' must not have 'condition' field.")
                if node.routes is not None:
                    errors.append(f"Transform '{node.id}' must not have 'routes' field.")
            elif node.node_type == "coalesce":
                if node.branches is None:
                    errors.append(f"Coalesce '{node.id}' is missing required field 'branches'.")
                if node.policy is None:
                    errors.append(f"Coalesce '{node.id}' is missing required field 'policy'.")
            elif node.node_type == "aggregation":
                if node.plugin is None:
                    errors.append(f"Aggregation '{node.id}' is missing required field 'plugin'.")

        # 8. Connection completeness
        edge_destinations = {e.to_node for e in self.edges}
        source_on_success = self.source.on_success if self.source else None
        for node in self.nodes:
            reachable = node.id in edge_destinations or node.input == source_on_success
            if not reachable:
                errors.append(f"Node '{node.id}' input '{node.input}' is not reachable from any edge or the source on_success.")

        return ValidationSummary(
            is_valid=len(errors) == 0,
            errors=tuple(errors),
        )
