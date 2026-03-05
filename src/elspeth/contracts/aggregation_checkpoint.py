"""Typed checkpoint state for aggregation buffers.

Replaces ``dict[str, Any]`` with frozen dataclasses that encode the
three-level checkpoint structure at the type level:

  AggregationCheckpointState          (Level 1 — full state)
    └── AggregationNodeCheckpoint     (Level 2 — per-node)
         └── AggregationTokenCheckpoint (Level 3 — per-token)

Trust-tier notes
----------------
* ``to_dict()`` — serialization boundary for ``checkpoint_dumps()``.
  Preserves the existing wire format exactly (flat ``_version`` + node_id keys).
* ``from_dict()`` — Tier 1 reconstruction.  Checkpoints are our data (per
  CLAUDE.md Data Manifesto): crash on any structural corruption, no coercion.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class AggregationTokenCheckpoint:
    """Checkpoint state for a single buffered token (Level 3).

    Attributes:
        token_id: Unique token identity for lineage tracking.
        row_id: Source row identity.
        branch_name: Fork branch name, or ``None`` for linear paths.
        fork_group_id: Fork group identity, or ``None``.
        join_group_id: Join group identity, or ``None``.
        expand_group_id: Deaggregation expansion group, or ``None``.
        row_data: Row payload as plain dict (opaque — PipelineRow owns format).
        contract_version: Version hash of the SchemaContract at checkpoint time.
    """

    token_id: str
    row_id: str
    branch_name: str | None
    fork_group_id: str | None
    join_group_id: str | None
    expand_group_id: str | None
    row_data: dict[str, Any]
    contract_version: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize to checkpoint dict format."""
        return {
            "token_id": self.token_id,
            "row_id": self.row_id,
            "branch_name": self.branch_name,
            "fork_group_id": self.fork_group_id,
            "join_group_id": self.join_group_id,
            "expand_group_id": self.expand_group_id,
            "row_data": self.row_data,
            "contract_version": self.contract_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AggregationTokenCheckpoint:
        """Reconstruct from checkpoint dict (Tier 1 — crash on corruption).

        Args:
            data: Token dict from checkpoint.

        Raises:
            ValueError: If required keys are missing.
        """
        required_fields = {
            "token_id",
            "row_id",
            "row_data",
            "branch_name",
            "fork_group_id",
            "join_group_id",
            "expand_group_id",
            "contract_version",
        }
        missing = required_fields - set(data.keys())
        if missing:
            raise ValueError(f"Checkpoint token missing required fields: {missing}. Found: {set(data.keys())}")
        return cls(
            token_id=data["token_id"],
            row_id=data["row_id"],
            branch_name=data["branch_name"],
            fork_group_id=data["fork_group_id"],
            join_group_id=data["join_group_id"],
            expand_group_id=data["expand_group_id"],
            row_data=data["row_data"],
            contract_version=data["contract_version"],
        )


@dataclass(frozen=True, slots=True)
class AggregationNodeCheckpoint:
    """Checkpoint state for one aggregation node (Level 2).

    Attributes:
        tokens: Buffered tokens awaiting aggregation flush.
        batch_id: Active batch identity (non-optional — must exist if tokens buffered).
        elapsed_age_seconds: Seconds since first accept for timeout preservation.
        count_fire_offset: Trigger fire-time offset for count trigger, or ``None``.
        condition_fire_offset: Trigger fire-time offset for condition trigger, or ``None``.
        contract: SchemaContract checkpoint dict (opaque — SchemaContract owns format).
    """

    tokens: tuple[AggregationTokenCheckpoint, ...]
    batch_id: str
    elapsed_age_seconds: float
    count_fire_offset: float | None
    condition_fire_offset: float | None
    contract: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Serialize to checkpoint dict format."""
        return {
            "tokens": [t.to_dict() for t in self.tokens],
            "batch_id": self.batch_id,
            "elapsed_age_seconds": self.elapsed_age_seconds,
            "count_fire_offset": self.count_fire_offset,
            "condition_fire_offset": self.condition_fire_offset,
            "contract": self.contract,
        }

    @classmethod
    def from_dict(cls, node_id: str, data: dict[str, Any]) -> AggregationNodeCheckpoint:
        """Reconstruct from checkpoint dict (Tier 1 — crash on corruption).

        Args:
            node_id: Node ID for error messages (not stored on the dataclass).
            data: Node-level dict from checkpoint.

        Raises:
            ValueError: If required keys are missing or structure is invalid.
        """
        required_fields = {
            "tokens",
            "batch_id",
            "elapsed_age_seconds",
            "count_fire_offset",
            "condition_fire_offset",
            "contract",
        }
        missing = required_fields - set(data.keys())
        if missing:
            raise ValueError(f"Checkpoint node '{node_id}' missing required fields: {missing}. Found: {set(data.keys())}")

        tokens_data = data["tokens"]
        if not isinstance(tokens_data, list):
            raise ValueError(f"Invalid checkpoint format for node {node_id}: 'tokens' must be a list, got {type(tokens_data).__name__}")

        batch_id = data["batch_id"]
        if batch_id is None:
            raise ValueError(
                f"Invalid checkpoint format for node {node_id}: 'batch_id' is None. Checkpoint entries with tokens must include a batch_id."
            )

        tokens = tuple(AggregationTokenCheckpoint.from_dict(t) for t in tokens_data)

        return cls(
            tokens=tokens,
            batch_id=batch_id,
            elapsed_age_seconds=data["elapsed_age_seconds"],
            count_fire_offset=data["count_fire_offset"],
            condition_fire_offset=data["condition_fire_offset"],
            contract=data["contract"],
        )


@dataclass(frozen=True, slots=True)
class AggregationCheckpointState:
    """Full aggregation checkpoint state (Level 1).

    Wire format (preserved for ``checkpoint_dumps`` compatibility)::

        {
            "_version": "3.0",
            "node_id_1": { ... node checkpoint ... },
            "node_id_2": { ... node checkpoint ... },
        }

    Attributes:
        version: Checkpoint format version string.
        nodes: Map of node_id → per-node checkpoint.
    """

    version: str
    nodes: dict[str, AggregationNodeCheckpoint]

    def to_dict(self) -> dict[str, Any]:
        """Serialize to flat wire-format dict.

        Preserves the existing ``{"_version": ..., "node_id": {...}, ...}`` layout.
        """
        state: dict[str, Any] = {"_version": self.version}
        for node_id, node_ckpt in self.nodes.items():
            state[node_id] = node_ckpt.to_dict()
        return state

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AggregationCheckpointState:
        """Reconstruct from wire-format dict (Tier 1 — crash on corruption).

        Args:
            data: Flat checkpoint dict with ``_version`` key and node_id keys.

        Raises:
            ValueError: If ``_version`` is missing or structure is invalid.
        """
        if "_version" not in data:
            raise ValueError(f"Corrupted checkpoint: missing '_version' key. Found keys: {sorted(data.keys())}.")
        version = data["_version"]

        nodes: dict[str, AggregationNodeCheckpoint] = {}
        for key, value in data.items():
            if key.startswith("_"):
                continue
            nodes[key] = AggregationNodeCheckpoint.from_dict(key, value)

        return cls(version=version, nodes=nodes)
