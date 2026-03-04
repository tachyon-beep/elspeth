"""Typed checkpoint state for pending coalesce joins.

Persists in-memory coalesce barriers so graceful shutdown and crash recovery
can resume waiting joins without replaying upstream source rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class CoalesceTokenCheckpoint:
    """Checkpoint state for one arrived branch token."""

    token_id: str
    row_id: str
    branch_name: str
    fork_group_id: str | None
    join_group_id: str | None
    expand_group_id: str | None
    row_data: dict[str, Any]
    contract: dict[str, Any]
    state_id: str
    arrival_offset_seconds: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "token_id": self.token_id,
            "row_id": self.row_id,
            "branch_name": self.branch_name,
            "fork_group_id": self.fork_group_id,
            "join_group_id": self.join_group_id,
            "expand_group_id": self.expand_group_id,
            "row_data": self.row_data,
            "contract": self.contract,
            "state_id": self.state_id,
            "arrival_offset_seconds": self.arrival_offset_seconds,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CoalesceTokenCheckpoint:
        required_fields = {
            "token_id",
            "row_id",
            "branch_name",
            "fork_group_id",
            "join_group_id",
            "expand_group_id",
            "row_data",
            "contract",
            "state_id",
            "arrival_offset_seconds",
        }
        missing = required_fields - set(data.keys())
        if missing:
            raise ValueError(f"Coalesce checkpoint token missing required fields: {missing}. Found: {set(data.keys())}")
        return cls(
            token_id=data["token_id"],
            row_id=data["row_id"],
            branch_name=data["branch_name"],
            fork_group_id=data["fork_group_id"],
            join_group_id=data["join_group_id"],
            expand_group_id=data["expand_group_id"],
            row_data=data["row_data"],
            contract=data["contract"],
            state_id=data["state_id"],
            arrival_offset_seconds=data["arrival_offset_seconds"],
        )


@dataclass(frozen=True, slots=True)
class CoalescePendingCheckpoint:
    """Checkpoint state for one pending coalesce key."""

    coalesce_name: str
    row_id: str
    elapsed_age_seconds: float
    branches: dict[str, CoalesceTokenCheckpoint]
    lost_branches: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "coalesce_name": self.coalesce_name,
            "row_id": self.row_id,
            "elapsed_age_seconds": self.elapsed_age_seconds,
            "branches": {branch: token.to_dict() for branch, token in self.branches.items()},
            "lost_branches": dict(self.lost_branches),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CoalescePendingCheckpoint:
        required_fields = {
            "coalesce_name",
            "row_id",
            "elapsed_age_seconds",
            "branches",
            "lost_branches",
        }
        missing = required_fields - set(data.keys())
        if missing:
            raise ValueError(f"Coalesce checkpoint pending entry missing required fields: {missing}. Found: {set(data.keys())}")

        branches = data["branches"]
        if not isinstance(branches, dict):
            raise ValueError(
                f"Coalesce checkpoint pending entry 'branches' must be a dict, got {type(branches).__name__}: {branches!r}"
            )

        lost_branches = data["lost_branches"]
        if not isinstance(lost_branches, dict):
            raise ValueError(
                "Coalesce checkpoint pending entry 'lost_branches' must be a dict, "
                f"got {type(lost_branches).__name__}: {lost_branches!r}"
            )

        return cls(
            coalesce_name=data["coalesce_name"],
            row_id=data["row_id"],
            elapsed_age_seconds=data["elapsed_age_seconds"],
            branches={branch: CoalesceTokenCheckpoint.from_dict(token) for branch, token in branches.items()},
            lost_branches={branch: reason for branch, reason in lost_branches.items()},
        )


@dataclass(frozen=True, slots=True)
class CoalesceCheckpointState:
    """Full pending coalesce checkpoint state."""

    version: str
    pending: tuple[CoalescePendingCheckpoint, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "_version": self.version,
            "pending": [entry.to_dict() for entry in self.pending],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CoalesceCheckpointState:
        if "_version" not in data:
            raise ValueError(f"Corrupted coalesce checkpoint: missing '_version'. Found keys: {sorted(data.keys())}.")
        if "pending" not in data:
            raise ValueError(f"Corrupted coalesce checkpoint: missing 'pending'. Found keys: {sorted(data.keys())}.")

        pending = data["pending"]
        if not isinstance(pending, list):
            raise ValueError(f"Corrupted coalesce checkpoint: 'pending' must be a list, got {type(pending).__name__}.")

        return cls(
            version=data["_version"],
            pending=tuple(CoalescePendingCheckpoint.from_dict(entry) for entry in pending),
        )
