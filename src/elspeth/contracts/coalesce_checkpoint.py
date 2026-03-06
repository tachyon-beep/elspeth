"""Typed checkpoint state for pending coalesce joins.

Persists in-memory coalesce barriers so graceful shutdown and crash recovery
can resume waiting joins without replaying upstream source rows.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from elspeth.contracts.errors import AuditIntegrityError
from elspeth.contracts.freeze import deep_freeze, deep_thaw


@dataclass(frozen=True, slots=True)
class CoalesceTokenCheckpoint:
    """Checkpoint state for one arrived branch token."""

    token_id: str
    row_id: str
    branch_name: str
    fork_group_id: str | None
    join_group_id: str | None
    expand_group_id: str | None
    row_data: Mapping[str, Any]
    contract: Mapping[str, Any]
    state_id: str
    arrival_offset_seconds: float

    def __post_init__(self) -> None:
        """Validate Tier 1 invariants at construction time."""
        for field_name in ("token_id", "row_id", "branch_name", "state_id"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{field_name} must be a non-empty string, got {type(value).__name__}: {value!r}")
        if not isinstance(self.row_data, (dict, MappingProxyType)):
            raise ValueError(f"row_data must be a dict, got {type(self.row_data).__name__}: {self.row_data!r}")
        if not isinstance(self.contract, (dict, MappingProxyType)):
            raise ValueError(f"contract must be a dict, got {type(self.contract).__name__}: {self.contract!r}")
        if not isinstance(self.row_data, MappingProxyType):
            object.__setattr__(self, "row_data", deep_freeze(self.row_data))
        if not isinstance(self.contract, MappingProxyType):
            object.__setattr__(self, "contract", deep_freeze(self.contract))
        if (
            not isinstance(self.arrival_offset_seconds, (int, float))
            or not math.isfinite(self.arrival_offset_seconds)
            or self.arrival_offset_seconds < 0
        ):
            raise ValueError(f"arrival_offset_seconds must be non-negative, got {self.arrival_offset_seconds!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "token_id": self.token_id,
            "row_id": self.row_id,
            "branch_name": self.branch_name,
            "fork_group_id": self.fork_group_id,
            "join_group_id": self.join_group_id,
            "expand_group_id": self.expand_group_id,
            "row_data": deep_thaw(self.row_data),
            "contract": deep_thaw(self.contract),
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
            raise AuditIntegrityError(f"Corrupted coalesce token checkpoint: missing required fields {missing}. Found: {set(data.keys())}")
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
    branches: Mapping[str, CoalesceTokenCheckpoint]
    lost_branches: Mapping[str, str]

    def __post_init__(self) -> None:
        """Validate Tier 1 invariants at construction time."""
        for field_name in ("coalesce_name", "row_id"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{field_name} must be a non-empty string, got {type(value).__name__}: {value!r}")
        if (
            not isinstance(self.elapsed_age_seconds, (int, float))
            or not math.isfinite(self.elapsed_age_seconds)
            or self.elapsed_age_seconds < 0
        ):
            raise ValueError(f"elapsed_age_seconds must be non-negative, got {self.elapsed_age_seconds!r}")
        if not isinstance(self.branches, MappingProxyType):
            object.__setattr__(self, "branches", MappingProxyType(self.branches))
        if not isinstance(self.lost_branches, MappingProxyType):
            object.__setattr__(self, "lost_branches", MappingProxyType(self.lost_branches))
        overlap = set(self.branches) & set(self.lost_branches)
        if overlap:
            raise ValueError(f"branches and lost_branches must not overlap, shared keys: {sorted(overlap)}")

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
            raise AuditIntegrityError(
                f"Corrupted coalesce pending checkpoint: missing required fields {missing}. Found: {set(data.keys())}"
            )

        branches = data["branches"]
        if not isinstance(branches, dict):
            raise AuditIntegrityError(
                f"Corrupted coalesce pending checkpoint: 'branches' must be a dict, got {type(branches).__name__}: {branches!r}"
            )

        lost_branches = data["lost_branches"]
        if not isinstance(lost_branches, dict):
            raise AuditIntegrityError(
                f"Corrupted coalesce pending checkpoint: 'lost_branches' must be a dict, got {type(lost_branches).__name__}: {lost_branches!r}"
            )

        return cls(
            coalesce_name=data["coalesce_name"],
            row_id=data["row_id"],
            elapsed_age_seconds=data["elapsed_age_seconds"],
            branches={branch: CoalesceTokenCheckpoint.from_dict(token) for branch, token in branches.items()},
            lost_branches=dict(lost_branches),
        )


@dataclass(frozen=True, slots=True)
class CoalesceCheckpointState:
    """Full pending coalesce checkpoint state.

    Attributes:
        version: Checkpoint format version string.
        pending: Pending coalesce entries awaiting branch completion.
        completed_keys: Coalesce keys that already merged/failed, for
            late-arrival detection after restore. Each entry is a
            ``(coalesce_name, row_id)`` tuple.
    """

    version: str
    pending: tuple[CoalescePendingCheckpoint, ...]
    completed_keys: tuple[tuple[str, str], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "_version": self.version,
            "pending": [entry.to_dict() for entry in self.pending],
            "completed_keys": [list(key) for key in self.completed_keys],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CoalesceCheckpointState:
        if "_version" not in data:
            raise AuditIntegrityError(f"Corrupted coalesce checkpoint: missing '_version'. Found keys: {sorted(data.keys())}.")
        if "pending" not in data:
            raise AuditIntegrityError(f"Corrupted coalesce checkpoint: missing 'pending'. Found keys: {sorted(data.keys())}.")

        pending = data["pending"]
        if not isinstance(pending, list):
            raise AuditIntegrityError(f"Corrupted coalesce checkpoint: 'pending' must be a list, got {type(pending).__name__}.")

        if "completed_keys" not in data:
            raise AuditIntegrityError(f"Corrupted coalesce checkpoint: missing 'completed_keys'. Found keys: {sorted(data.keys())}.")
        raw_keys = data["completed_keys"]
        if not isinstance(raw_keys, list):
            raise AuditIntegrityError(f"Corrupted coalesce checkpoint: 'completed_keys' must be a list, got {type(raw_keys).__name__}.")
        completed_keys = tuple(tuple(k) for k in raw_keys)

        return cls(
            version=data["_version"],
            pending=tuple(CoalescePendingCheckpoint.from_dict(entry) for entry in pending),
            completed_keys=completed_keys,
        )
