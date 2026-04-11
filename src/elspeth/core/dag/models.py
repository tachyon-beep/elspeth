"""Types, constants, and exceptions for DAG operations.

Leaf module — no intra-package imports (prevents import cycles).
Matches the orchestrator/types.py pattern.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from elspeth.contracts.enums import NodeType
from elspeth.contracts.freeze import freeze_fields
from elspeth.contracts.schema import SchemaConfig
from elspeth.contracts.types import CoalesceName, NodeID
from elspeth.core.landscape.schema import NODE_ID_COLUMN_LENGTH

if TYPE_CHECKING:
    from elspeth.contracts import PluginSchema, TransformProtocol
    from elspeth.core.config import TransformSettings


class GraphValidationError(ValueError):
    """Raised when graph validation fails."""


@dataclass(frozen=True, slots=True)
class GraphValidationWarning:
    """Non-fatal warning emitted during graph construction.

    Unlike GraphValidationError, warnings don't prevent graph construction.
    They alert the operator to configurations that are technically valid but
    likely to cause runtime surprises (e.g., rows silently lost).
    """

    code: str
    message: str
    node_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.code:
            raise ValueError("GraphValidationWarning.code must not be empty")
        if not self.message:
            raise ValueError("GraphValidationWarning.message must not be empty")


@dataclass(frozen=True, slots=True)
class BranchInfo:
    """Properties of a fork branch that routes to a coalesce node.

    Consolidates two parallel dicts that were both keyed by BranchName:
    - branch_to_coalesce (BranchName -> CoalesceName)
    - branch_gate_map (BranchName -> NodeID)
    """

    coalesce_name: CoalesceName
    gate_node_id: NodeID

    def __post_init__(self) -> None:
        if not self.coalesce_name:
            raise ValueError("BranchInfo.coalesce_name must not be empty")
        if not self.gate_node_id:
            raise ValueError("BranchInfo.gate_node_id must not be empty")


_NODE_ID_MAX_LENGTH = NODE_ID_COLUMN_LENGTH


# Config stored on graph nodes varies by node type:
# - Source/Transform/Sink: raw plugin config dict (arbitrary keys per plugin)
# - Gate: {routes, condition, fork_to?}
# - Aggregation: {schema, trigger, output_mode, options}
# - Coalesce: {branches, policy, merge, timeout_seconds?, quorum_count?, select_branch?}
# Schema data is accessed via output_schema_config on NodeInfo, not config["schema"].
# config["schema"] exists on source/transform/sink/aggregation nodes for node ID
# hashing but is not read at runtime for schema semantics.
# dict[str, Any] is intentional: plugin configs are validated by each plugin's
# Pydantic model, not by the graph. The graph only hashes them for node IDs.
type NodeConfig = dict[str, Any]


@dataclass(frozen=True, slots=True)
class NodeInfo:
    """Information about a node in the execution graph.

    Frozen after construction — attribute reassignment is prevented to
    guarantee audit trail consistency. Schemas are locked at launch and
    never change during the run.

    Schema Contracts:
        input_schema_config and output_schema_config store the original
        SchemaConfig from plugin configuration. These contain contract
        declarations (guaranteed_fields, required_fields) used for DAG
        validation. The input_schema and output_schema are the generated
        Pydantic model types used for runtime validation.
    """

    node_id: NodeID
    node_type: NodeType
    plugin_name: str
    config: NodeConfig = field(default_factory=dict)
    input_schema: type[PluginSchema] | None = None
    output_schema: type[PluginSchema] | None = None
    input_schema_config: SchemaConfig | None = None
    output_schema_config: SchemaConfig | None = None
    # Populated only for SINK nodes by the builder from SinkProtocol.declared_required_fields.
    # Used for build-time validation that upstream coalesce output guarantees the
    # fields a sink requires. Empty frozenset for all non-sink nodes.
    declared_required_fields: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if len(self.node_id) > _NODE_ID_MAX_LENGTH:
            msg = f"node_id exceeds {_NODE_ID_MAX_LENGTH} characters: '{self.node_id}' (length={len(self.node_id)})"
            raise GraphValidationError(msg)
        # Offensive programming: declared_required_fields is sink-specific.
        # Catch the misuse at construction time rather than letting stray
        # data sit on a non-sink node until a future validator widens its
        # scope and produces mysterious errors.
        if self.declared_required_fields and self.node_type != NodeType.SINK:
            raise GraphValidationError(
                f"NodeInfo.declared_required_fields is only meaningful for SINK nodes; "
                f"node {self.node_id!r} has type {self.node_type.name} "
                f"with declared_required_fields={sorted(self.declared_required_fields)!r}."
            )
        # NOTE: config is NOT frozen here because the builder mutates
        # output_schema_config on pass-through nodes (gates, coalesce) via
        # object.__setattr__ during schema propagation. Deep freeze is
        # applied by build_execution_graph() after all mutations are complete.


@dataclass(frozen=True, slots=True)
class _GateEntry:
    """Internal gate metadata for coalesce and routing wiring."""

    node_id: NodeID
    name: str
    fork_to: tuple[str, ...] | None
    routes: Mapping[str, str]

    def __post_init__(self) -> None:
        if not self.node_id:
            raise ValueError("_GateEntry.node_id must not be empty")
        if not self.name:
            raise ValueError("_GateEntry.name must not be empty")
        if self.fork_to is not None and len(self.fork_to) == 0:
            raise ValueError("_GateEntry.fork_to must not be empty tuple (use None for no fork)")
        if len(self.routes) == 0:
            raise ValueError("_GateEntry.routes must have at least one entry")
        freeze_fields(self, "routes")


@dataclass(frozen=True, slots=True)
class WiredTransform:
    """Pair a transform plugin instance with its wiring settings."""

    plugin: TransformProtocol
    settings: TransformSettings

    def __post_init__(self) -> None:
        """Ensure wiring metadata matches the instantiated plugin."""
        if self.plugin.name != self.settings.plugin:
            raise GraphValidationError(
                f"WiredTransform mismatch: settings.plugin='{self.settings.plugin}' but plugin instance name='{self.plugin.name}'."
            )


def _suggest_similar(name: str, candidates: list[str]) -> list[str]:
    """Suggest similar names for wiring validation errors."""
    import difflib

    return difflib.get_close_matches(name, candidates, n=3, cutoff=0.6)
