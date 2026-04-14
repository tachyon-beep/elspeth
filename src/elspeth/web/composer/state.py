"""CompositionState and supporting data models for pipeline composition.

All dataclasses are frozen with slots. Container fields (options, routes,
fork_to, branches) are deep-frozen via freeze_fields() in __post_init__.
Mutation methods return new instances — they never modify the original.

Layer: L3 (application).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import PurePosixPath
from typing import Any, Literal, Self, TypedDict

from elspeth.contracts.freeze import deep_thaw, freeze_fields
from elspeth.engine.orchestrator.validation import (
    _ALLOWED_FAILSINK_PLUGINS,
)

NodeType = Literal["transform", "gate", "aggregation", "coalesce"]
EdgeType = Literal["on_success", "on_error", "route_true", "route_false", "fork"]


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
            name=d["name"],
            description=d["description"],
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
    node_type: NodeType
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
    edge_type: EdgeType
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
        on_write_failure: How to handle write failures ("discard" or a sink name).
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


Severity = Literal["high", "medium", "low"]


@dataclass(frozen=True, slots=True)
class ValidationEntry:
    """Structured validation message with component attribution.

    All fields are scalars. frozen=True is sufficient.
    """

    component: str
    message: str
    severity: Severity

    def to_dict(self) -> dict[str, str]:
        """Serialize to a plain dict for JSON responses."""
        return {"component": self.component, "message": self.message, "severity": self.severity}


EdgeContractDict = TypedDict(
    "EdgeContractDict",
    {
        "from": str,
        "to": str,
        "producer_guarantees": list[str],
        "consumer_requires": list[str],
        "missing_fields": list[str],
        "satisfied": bool,
    },
)


@dataclass(frozen=True, slots=True)
class EdgeContract:
    """Schema contract check result for a single producer->consumer edge."""

    from_id: str
    to_id: str
    producer_guarantees: tuple[str, ...]
    consumer_requires: tuple[str, ...]
    missing_fields: tuple[str, ...]
    satisfied: bool

    def to_dict(self) -> EdgeContractDict:
        """Serialize to a plain dict for JSON responses."""
        return {
            "from": self.from_id,
            "to": self.to_id,
            "producer_guarantees": list(self.producer_guarantees),
            "consumer_requires": list(self.consumer_requires),
            "missing_fields": list(self.missing_fields),
            "satisfied": self.satisfied,
        }


@dataclass(frozen=True, slots=True)
class ValidationSummary:
    """Stage 1 validation result.

    errors block execution. warnings are advisory but actionable.
    suggestions are optional improvements. edge_contracts shows
    per-edge schema contract check results. All are tuples for
    structured component attribution.
    """

    is_valid: bool
    errors: tuple[ValidationEntry, ...]
    warnings: tuple[ValidationEntry, ...] = ()
    suggestions: tuple[ValidationEntry, ...] = ()
    edge_contracts: tuple[EdgeContract, ...] = ()


def _source_options_have_schema(options: Mapping[str, Any]) -> bool:
    """Return whether source options carry a schema under the current contract.

    Composer state can contain either the user-facing ``schema`` alias or the
    internal ``schema_config`` field name, because plugin config parsing allows
    population by either key. Read-only summaries and validation must use the
    same rule so they cannot drift.
    """
    return "schema" in options or "schema_config" in options


def _validate_gate_expression(condition: str) -> str | None:
    """Validate a gate condition expression at composition time.

    Returns an error message if the expression is syntactically invalid or
    contains forbidden constructs, or None if valid.

    Uses a deferred import to keep state.py's module-level imports minimal
    (only contracts.freeze). The import is L3→L1, which is layer-legal.
    """
    from elspeth.core.expression_parser import (
        ExpressionParser,
        ExpressionSecurityError,
        ExpressionSyntaxError,
    )

    try:
        ExpressionParser(condition)
    except ExpressionSyntaxError as e:
        return f"Invalid gate condition syntax: {e}"
    except ExpressionSecurityError as e:
        return f"Forbidden construct in gate condition: {e}"
    return None


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
        if self.version < 1:
            raise ValueError(f"CompositionState.version must be >= 1, got {self.version}")

    # --- Mutation methods ---

    def with_source(self, source: SourceSpec) -> CompositionState:
        """Return new state with the given source, version incremented."""
        return replace(self, source=source, version=self.version + 1)

    def without_source(self) -> CompositionState:
        """Return new state with the source removed, version incremented."""
        return replace(self, source=None, version=self.version + 1)

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
        existing_ids = [e.id for e in self.edges]
        if edge.id in existing_ids:
            idx = existing_ids.index(edge.id)
            edge_list = list(self.edges)
            edge_list[idx] = edge
            edges = tuple(edge_list)
        else:
            edges = (*self.edges, edge)
        return replace(self, edges=edges, version=self.version + 1)

    def without_edge(self, edge_id: str) -> CompositionState | None:
        """Remove edge by id. Returns None if edge not found."""
        if not any(e.id == edge_id for e in self.edges):
            return None
        edges = tuple(e for e in self.edges if e.id != edge_id)
        return replace(self, edges=edges, version=self.version + 1)

    def with_output(self, output: OutputSpec) -> CompositionState:
        """Add or replace an output (matched by name). Version incremented."""
        existing_names = [o.name for o in self.outputs]
        if output.name in existing_names:
            idx = existing_names.index(output.name)
            output_list = list(self.outputs)
            output_list[idx] = output
            outputs = tuple(output_list)
        else:
            outputs = (*self.outputs, output)
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
        name = patch["name"] if "name" in patch else current.name
        description = patch["description"] if "description" in patch else current.description
        new_meta = PipelineMetadata(
            name=name,
            description=description,
        )
        return replace(self, metadata=new_meta, version=self.version + 1)

    # --- Serialization ---

    def to_dict(self) -> dict[str, Any]:
        """Recursively unwrap frozen containers to plain Python types.

        Converts MappingProxyType -> dict, tuple -> list recursively.
        The result is suitable for yaml.dump() and JSON serialization.
        """

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
                "options": deep_thaw(self.source.options),
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
                "options": deep_thaw(node.options),
            }
            if node.condition is not None:
                node_dict["condition"] = node.condition
            if node.routes is not None:
                node_dict["routes"] = deep_thaw(node.routes)
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
                    "options": deep_thaw(output.options),
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
        errors: list[ValidationEntry] = []
        _err = ValidationEntry  # local alias for brevity

        # 1. Source exists
        if self.source is None:
            errors.append(_err("source", "No source configured.", "high"))

        # 2. At least one output
        if not self.outputs:
            errors.append(_err("pipeline", "No sinks configured.", "high"))

        # 3. Edge references valid
        node_ids = {n.id for n in self.nodes}
        output_names = {o.name for o in self.outputs}
        valid_from = node_ids | {"source"}
        valid_to = node_ids | output_names
        for edge in self.edges:
            if edge.from_node not in valid_from:
                errors.append(_err(f"edge:{edge.id}", f"Edge '{edge.id}' references unknown node '{edge.from_node}' as from_node.", "high"))
            if edge.to_node not in valid_to:
                errors.append(_err(f"edge:{edge.id}", f"Edge '{edge.id}' references unknown node '{edge.to_node}' as to_node.", "high"))

        # 4. Node IDs unique
        seen_node_ids: set[str] = set()
        for node in self.nodes:
            if node.id in seen_node_ids:
                errors.append(_err(f"node:{node.id}", f"Duplicate node ID: '{node.id}'.", "high"))
            seen_node_ids.add(node.id)

        # 5. Output names unique
        seen_output_names: set[str] = set()
        for output in self.outputs:
            if output.name in seen_output_names:
                errors.append(_err(f"output:{output.name}", f"Duplicate output name: '{output.name}'.", "high"))
            seen_output_names.add(output.name)

        # 6. Edge IDs unique
        seen_edge_ids: set[str] = set()
        for edge in self.edges:
            if edge.id in seen_edge_ids:
                errors.append(_err(f"edge:{edge.id}", f"Duplicate edge ID: '{edge.id}'.", "high"))
            seen_edge_ids.add(edge.id)

        # 7. Node type field consistency
        for node in self.nodes:
            if node.node_type == "gate":
                if node.condition is None:
                    errors.append(_err(f"node:{node.id}", f"Gate '{node.id}' is missing required field 'condition'.", "high"))
                else:
                    # Validate expression content — defense-in-depth catches
                    # malformed conditions from any entry path (including
                    # session deserialization).
                    expr_error = _validate_gate_expression(node.condition)
                    if expr_error is not None:
                        errors.append(_err(f"node:{node.id}", f"Gate '{node.id}': {expr_error}", "high"))
                if node.routes is None:
                    errors.append(_err(f"node:{node.id}", f"Gate '{node.id}' is missing required field 'routes'.", "high"))
            elif node.node_type == "transform":
                if node.condition is not None:
                    errors.append(_err(f"node:{node.id}", f"Transform '{node.id}' must not have 'condition' field.", "high"))
                if node.routes is not None:
                    errors.append(_err(f"node:{node.id}", f"Transform '{node.id}' must not have 'routes' field.", "high"))
            elif node.node_type == "coalesce":
                if node.branches is None:
                    errors.append(_err(f"node:{node.id}", f"Coalesce '{node.id}' is missing required field 'branches'.", "high"))
                if node.policy is None:
                    errors.append(_err(f"node:{node.id}", f"Coalesce '{node.id}' is missing required field 'policy'.", "high"))
            elif node.node_type == "aggregation":
                if node.plugin is None:
                    errors.append(_err(f"node:{node.id}", f"Aggregation '{node.id}' is missing required field 'plugin'.", "high"))

        # 8. Connection completeness
        edge_destinations = {e.to_node for e in self.edges}
        source_on_success = self.source.on_success if self.source else None
        for node in self.nodes:
            reachable = node.id in edge_destinations or node.input == source_on_success
            if not reachable:
                errors.append(
                    _err(
                        f"node:{node.id}",
                        f"Node '{node.id}' input '{node.input}' is not reachable from any edge or the source on_success.",
                        "high",
                    )
                )

        # --- Warnings (advisory, non-blocking) ---
        warnings: list[ValidationEntry] = []
        _warn = ValidationEntry

        # Build connection-field targets (wiring that doesn't require edges)
        connection_targets: set[str] = set()
        if source_on_success is not None:
            connection_targets.add(source_on_success)
        for node in self.nodes:
            if node.on_success is not None:
                connection_targets.add(node.on_success)
            if node.on_error is not None:
                connection_targets.add(node.on_error)
            if node.routes is not None:
                connection_targets.update(node.routes.values())

        # W1: Output has no runtime routing reference (on_success / on_error / routes)
        # Edges are UI-only — generate_yaml() uses only connection fields,
        # so an edge to a sink without a matching connection field is a
        # false positive for reachability.
        for output in self.outputs:
            if output.name not in connection_targets:
                warnings.append(
                    _warn(
                        f"output:{output.name}",
                        f"Output '{output.name}' is not referenced by any on_success, on_error, or route — it will never receive data.",
                        "medium",
                    )
                )

        # W2: Source on_success target doesn't match any node input or output name
        if source_on_success is not None:
            node_inputs = {n.input for n in self.nodes if n.input is not None}
            if source_on_success not in node_inputs and source_on_success not in output_names:
                warnings.append(
                    _warn(
                        "source",
                        f"Source on_success '{source_on_success}' does not match any node input or output — data may not flow.",
                        "medium",
                    )
                )

        # W3: Node has no outgoing edges and no connection-field targets
        edge_sources = {e.from_node for e in self.edges}
        for node in self.nodes:
            has_edge_out = node.id in edge_sources
            has_connection_out = (
                node.on_success is not None or node.on_error is not None or (node.routes is not None and len(node.routes) > 0)
            )
            if not has_edge_out and not has_connection_out:
                warnings.append(
                    _warn(
                        f"node:{node.id}",
                        f"Node '{node.id}' has no outgoing edges — its output is not connected to any downstream node or sink.",
                        "medium",
                    )
                )

        # W4: Sink plugin/filename extension mismatch
        _plugin_exts: dict[str, set[str]] = {
            "csv": {".csv"},
            "json": {".json", ".jsonl"},
            "jsonl": {".jsonl"},
        }
        for output in self.outputs:
            if "path" not in output.options:
                continue
            path_val = output.options["path"]
            if type(path_val) is not str:
                continue

            ext = PurePosixPath(path_val).suffix.lower()
            if output.plugin not in _plugin_exts:
                continue
            accepted = _plugin_exts[output.plugin]
            if ext and ext not in accepted:
                warnings.append(
                    _warn(
                        f"output:{output.name}",
                        f"Output '{output.name}' uses plugin '{output.plugin}' but filename extension suggests a different format.",
                        "low",
                    )
                )

        # W5: Transform/aggregation node has empty or incomplete options
        # These plugins require configuration to do anything useful.
        _plugins_requiring_config: dict[str, tuple[str, str]] = {
            "value_transform": ("operations", "no operations defined — nothing will be computed"),
            "type_coerce": ("conversions", "no conversions defined — no types will be changed"),
            "llm": ("template", "no template defined — nothing will be sent to the model"),
            "field_mapper": ("mapping", "no mapping defined — no fields will be renamed"),
            "truncate": ("fields", "no fields specified — nothing will be truncated"),
            "keyword_filter": ("keywords", "no keywords defined — all rows will pass through"),
            "web_scrape": ("url_field", "no url_field specified — cannot determine which field contains URLs"),
            "json_explode": ("field", "no field specified — cannot determine which field to explode"),
        }
        for node in self.nodes:
            if node.plugin in _plugins_requiring_config:
                required_key, reason = _plugins_requiring_config[node.plugin]
                if not node.options or required_key not in node.options:
                    warnings.append(
                        _warn(
                            f"node:{node.id}",
                            f"Transform '{node.id}' ({node.plugin}) appears incomplete: {reason}.",
                            "medium",
                        )
                    )
                # Also check for empty list/dict/tuple values (lists are frozen to tuples)
                elif node.options[required_key] in ([], (), {}, None, ""):
                    warnings.append(
                        _warn(
                            f"node:{node.id}",
                            f"Transform '{node.id}' ({node.plugin}) has empty '{required_key}': {reason}.",
                            "medium",
                        )
                    )

        # W6: File sink missing required path
        _file_sinks = {"csv", "json", "jsonl", "text", "parquet", "xml"}
        for output in self.outputs:
            if output.plugin in _file_sinks:
                if not output.options or "path" not in output.options:
                    warnings.append(
                        _warn(
                            f"output:{output.name}",
                            f"Output '{output.name}' ({output.plugin}) has no path configured — cannot write to file.",
                            "medium",
                        )
                    )
                elif not output.options["path"]:
                    warnings.append(
                        _warn(
                            f"output:{output.name}",
                            f"Output '{output.name}' ({output.plugin}) has empty path — cannot write to file.",
                            "medium",
                        )
                    )

        # W7: on_write_failure reference validation
        # Mirrors rules from engine/orchestrator/validation.py so LLMs get
        # early feedback instead of failing at pipeline build time.
        _failsink_eligible = _ALLOWED_FAILSINK_PLUGINS
        output_name_set = {o.name for o in self.outputs}
        output_by_name = {o.name: o for o in self.outputs}
        for output in self.outputs:
            dest = output.on_write_failure
            if dest == "discard":
                continue
            # Rule 2: must reference an existing output
            if dest not in output_name_set:
                warnings.append(
                    _warn(
                        f"output:{output.name}",
                        f"Output '{output.name}' on_write_failure references '{dest}' which is not a configured output.",
                        "high",
                    )
                )
                continue  # Skip dependent checks
            # Rule 3: no self-reference
            if dest == output.name:
                warnings.append(
                    _warn(
                        f"output:{output.name}",
                        f"Output '{output.name}' on_write_failure references itself — a sink cannot be its own failsink.",
                        "high",
                    )
                )
                continue
            # Rule 4: target must use an eligible file plugin
            target = output_by_name[dest]
            if target.plugin not in _failsink_eligible:
                warnings.append(
                    _warn(
                        f"output:{output.name}",
                        f"Output '{output.name}' on_write_failure references '{dest}' (plugin='{target.plugin}'), but failsinks must use csv, json, or xml.",
                        "medium",
                    )
                )
            # Rule 5: no chains — target must use 'discard'
            if target.on_write_failure != "discard":
                warnings.append(
                    _warn(
                        f"output:{output.name}",
                        f"Output '{output.name}' on_write_failure references '{dest}', but '{dest}' has on_write_failure='{target.on_write_failure}' — failsink targets must use 'discard' (no chains).",
                        "medium",
                    )
                )

        # --- Suggestions (optional improvements) ---
        suggestions: list[ValidationEntry] = []
        _sug = ValidationEntry

        # S1: No error routing
        has_gate = any(n.node_type == "gate" for n in self.nodes)
        has_error_routing = any(e.edge_type == "on_error" for e in self.edges) or any(n.on_error is not None for n in self.nodes)
        if not has_gate and not has_error_routing and self.nodes:
            suggestions.append(
                _sug("pipeline", "Consider adding error routing — rows that fail transforms currently have no explicit destination.", "low")
            )

        # S2: Single output to external sink — suggest a local fallback
        # Local file sinks (csv, json, text, parquet) don't benefit from a backup:
        # if the filesystem is failing, a second file will fail too.
        # External sinks (database, azure_blob, dataverse, http) benefit from a
        # local recovery file when the external system is unavailable.
        _local_file_sinks = {"csv", "json", "jsonl", "text", "parquet"}
        if len(self.outputs) == 1:
            output = self.outputs[0]
            if output.plugin not in _local_file_sinks:
                suggestions.append(
                    _sug(
                        "pipeline",
                        f"Single external output ('{output.plugin}'). Consider adding a local file output for recovery if the external system is unavailable.",
                        "low",
                    )
                )

        # S3: Source has no schema under the current composer/plugin config contract
        if self.source is not None:
            has_schema = _source_options_have_schema(self.source.options)
            if not has_schema:
                suggestions.append(
                    _sug("source", "Source has no explicit schema. Downstream field references depend on runtime column names.", "low")
                )

        return ValidationSummary(
            is_valid=len(errors) == 0,
            errors=tuple(errors),
            warnings=tuple(warnings),
            suggestions=tuple(suggestions),
        )
