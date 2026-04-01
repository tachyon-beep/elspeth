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
from elspeth.contracts.freeze import deep_thaw, freeze_fields


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
        for field_name, value in (
            ("token_id", self.token_id),
            ("row_id", self.row_id),
            ("branch_name", self.branch_name),
            ("state_id", self.state_id),
        ):
            if not isinstance(value, str) or not value:
                raise ValueError(f"{field_name} must be a non-empty string, got {type(value).__name__}: {value!r}")
        if not isinstance(self.row_data, (dict, MappingProxyType)):
            raise TypeError(f"CoalesceTokenCheckpoint.row_data must be dict or MappingProxyType, got {type(self.row_data).__name__}")
        if not isinstance(self.contract, (dict, MappingProxyType)):
            raise TypeError(f"CoalesceTokenCheckpoint.contract must be dict or MappingProxyType, got {type(self.contract).__name__}")
        freeze_fields(self, "row_data", "contract")
        if self.arrival_offset_seconds < 0 or not math.isfinite(self.arrival_offset_seconds):
            raise ValueError(f"arrival_offset_seconds must be non-negative and finite, got {self.arrival_offset_seconds!r}")

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
        for field_name, value in (
            ("coalesce_name", self.coalesce_name),
            ("row_id", self.row_id),
        ):
            if not isinstance(value, str) or not value:
                raise ValueError(f"{field_name} must be a non-empty string, got {type(value).__name__}: {value!r}")
        if self.elapsed_age_seconds < 0 or not math.isfinite(self.elapsed_age_seconds):
            raise ValueError(f"elapsed_age_seconds must be non-negative and finite, got {self.elapsed_age_seconds!r}")
        freeze_fields(self, "branches", "lost_branches")
        # Validate branch keys are non-empty strings
        for branch_key in self.branches:
            if not isinstance(branch_key, str) or not branch_key:
                raise ValueError(f"branches key must be a non-empty string, got {type(branch_key).__name__}: {branch_key!r}")
        # Validate branch key matches embedded token's branch_name (dual-encoding consistency)
        for branch_key, token_ckpt in self.branches.items():
            if token_ckpt.branch_name != branch_key:
                raise AuditIntegrityError(
                    f"Branch key '{branch_key}' does not match token's branch_name '{token_ckpt.branch_name}'. "
                    f"Dual-encoded branch identity must agree — corrupted checkpoint."
                )
        # Validate lost_branches keys and values are non-empty strings
        for lb_key, lb_val in self.lost_branches.items():
            if not isinstance(lb_key, str) or not lb_key:
                raise ValueError(f"lost_branches key must be a non-empty string, got {type(lb_key).__name__}: {lb_key!r}")
            if not isinstance(lb_val, str) or not lb_val:
                raise ValueError(f"lost_branches[{lb_key!r}] must be a non-empty string, got {type(lb_val).__name__}: {lb_val!r}")
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

    def __post_init__(self) -> None:
        """Validate Tier 1 invariants at construction time."""
        if not isinstance(self.version, str) or not self.version:
            raise ValueError(f"version must be a non-empty string, got {type(self.version).__name__}: {self.version!r}")
        object.__setattr__(self, "pending", tuple(self.pending))
        object.__setattr__(self, "completed_keys", tuple(self.completed_keys))
        for i, key in enumerate(self.completed_keys):
            if not isinstance(key, tuple) or len(key) != 2 or not all(isinstance(s, str) for s in key):
                raise ValueError(f"completed_keys[{i}] must be a 2-element (str, str) tuple, got {type(key).__name__}: {key!r}")

    @property
    def has_resumable_state(self) -> bool:
        """Whether this checkpoint contains state needed for correct resume.

        True when there are pending barriers OR completed keys that must
        survive a checkpoint round-trip to detect late arrivals.
        """
        return bool(self.pending) or bool(self.completed_keys)

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
        for i, k in enumerate(raw_keys):
            if not isinstance(k, (list, tuple)) or len(k) != 2 or not all(isinstance(s, str) for s in k):
                raise AuditIntegrityError(
                    f"Corrupted coalesce checkpoint: completed_keys[{i}] must be a 2-element [str, str], got {type(k).__name__}: {k!r}"
                )
        completed_keys = tuple(tuple(k) for k in raw_keys)

        return cls(
            version=data["_version"],
            pending=tuple(CoalescePendingCheckpoint.from_dict(entry) for entry in pending),
            completed_keys=completed_keys,
        )
