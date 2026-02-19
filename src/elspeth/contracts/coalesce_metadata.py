"""Typed coalesce metadata for the Landscape audit trail.

Replaces loose ``dict[str, Any]`` at 4 construction sites in
``coalesce_executor.py`` with a frozen dataclass that makes every
field visible to mypy and enforces immutability.

Trust-tier notes
----------------
* Factory classmethods — used by our code (Tier 1/2).
* ``to_dict()`` — serialization boundary for ``context_after_json``.
  Omits ``None`` fields so the JSON shape is identical to the
  pre-dataclass dict literals.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Any


@dataclass(frozen=True, slots=True)
class ArrivalOrderEntry:
    """One branch's arrival timing relative to first arrival."""

    branch: str
    arrival_offset_ms: float

    def to_dict(self) -> dict[str, Any]:
        return {"branch": self.branch, "arrival_offset_ms": self.arrival_offset_ms}


@dataclass(frozen=True, slots=True)
class CoalesceMetadata:
    """Typed metadata for coalesce merge/failure audit records.

    All 4 construction sites in ``coalesce_executor.py`` produce
    subsets of these fields.  ``to_dict()`` omits ``None`` values so
    the serialized output is identical to the pre-dataclass dicts.

    Attributes:
        policy: Coalesce policy (require_all, first, quorum, best_effort).
        reason: Human-readable reason for late arrival failure.
        merge_strategy: Merge strategy (union, nested, select).
        expected_branches: All configured branch names.
        branches_arrived: Branches that actually arrived before merge/failure.
        branches_lost: Mapping of branch name to loss reason.
        select_branch: Selected branch name (for select merge strategy).
        arrival_order: Chronological arrival entries.
        wait_duration_ms: Total wall-clock wait from first arrival to merge.
        quorum_required: Quorum threshold (for quorum policy failures).
        timeout_seconds: Configured timeout (for timeout-triggered failures).
        union_field_collisions: Field name to contributing branches (union merge).
    """

    policy: str

    # Failure context
    reason: str | None = None

    # Merge context
    merge_strategy: str | None = None
    expected_branches: tuple[str, ...] | None = None
    branches_arrived: tuple[str, ...] | None = None
    branches_lost: MappingProxyType[str, str] | None = None
    select_branch: str | None = None

    # Timing
    arrival_order: tuple[ArrivalOrderEntry, ...] | None = None
    wait_duration_ms: float | None = None

    # Failure policy fields
    quorum_required: int | None = None
    timeout_seconds: float | None = None

    # Union merge collision info
    union_field_collisions: MappingProxyType[str, tuple[str, ...]] | None = None

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialize to plain dict, omitting None fields.

        Produces output identical to the current dict literals
        in ``coalesce_executor.py``.
        """
        result: dict[str, Any] = {"policy": self.policy}
        if self.reason is not None:
            result["reason"] = self.reason
        if self.merge_strategy is not None:
            result["merge_strategy"] = self.merge_strategy
        if self.expected_branches is not None:
            result["expected_branches"] = list(self.expected_branches)
        if self.branches_arrived is not None:
            result["branches_arrived"] = list(self.branches_arrived)
        if self.branches_lost is not None:
            result["branches_lost"] = dict(self.branches_lost)
        if self.select_branch is not None:
            result["select_branch"] = self.select_branch
        if self.arrival_order is not None:
            result["arrival_order"] = [e.to_dict() for e in self.arrival_order]
        if self.wait_duration_ms is not None:
            result["wait_duration_ms"] = self.wait_duration_ms
        if self.quorum_required is not None:
            result["quorum_required"] = self.quorum_required
        if self.timeout_seconds is not None:
            result["timeout_seconds"] = self.timeout_seconds
        if self.union_field_collisions is not None:
            result["union_field_collisions"] = {k: list(v) for k, v in self.union_field_collisions.items()}
        return result

    # ------------------------------------------------------------------
    # Factories
    # ------------------------------------------------------------------

    @classmethod
    def for_late_arrival(cls, *, policy: str, reason: str) -> CoalesceMetadata:
        """Late arrival after merge/failure already completed."""
        return cls(policy=policy, reason=reason)

    @classmethod
    def for_failure(
        cls,
        *,
        policy: str,
        expected_branches: list[str],
        branches_arrived: list[str],
        branches_lost: dict[str, str] | None = None,
        quorum_required: int | None = None,
        timeout_seconds: float | None = None,
    ) -> CoalesceMetadata:
        """Merge failure (timeout, missing branches, quorum not met)."""
        return cls(
            policy=policy,
            expected_branches=tuple(expected_branches),
            branches_arrived=tuple(branches_arrived),
            branches_lost=MappingProxyType(branches_lost) if branches_lost else None,
            quorum_required=quorum_required,
            timeout_seconds=timeout_seconds,
        )

    @classmethod
    def for_select_not_arrived(
        cls,
        *,
        policy: str,
        merge_strategy: str,
        select_branch: str,
        branches_arrived: list[str],
    ) -> CoalesceMetadata:
        """Select branch not in arrived set at merge time."""
        return cls(
            policy=policy,
            merge_strategy=merge_strategy,
            select_branch=select_branch,
            branches_arrived=tuple(branches_arrived),
        )

    @classmethod
    def for_merge(
        cls,
        *,
        policy: str,
        merge_strategy: str,
        expected_branches: list[str],
        branches_arrived: list[str],
        branches_lost: dict[str, str],
        arrival_order: list[ArrivalOrderEntry],
        wait_duration_ms: float,
    ) -> CoalesceMetadata:
        """Successful merge with full audit context."""
        return cls(
            policy=policy,
            merge_strategy=merge_strategy,
            expected_branches=tuple(expected_branches),
            branches_arrived=tuple(branches_arrived),
            branches_lost=MappingProxyType(branches_lost) if branches_lost else MappingProxyType({}),
            arrival_order=tuple(arrival_order),
            wait_duration_ms=wait_duration_ms,
        )

    @classmethod
    def with_collisions(
        cls,
        base: CoalesceMetadata,
        collisions: dict[str, list[str]],
    ) -> CoalesceMetadata:
        """Add union field collision info to an existing metadata instance.

        Since CoalesceMetadata is frozen, this creates a new instance
        via ``dataclasses.replace()``.
        """
        frozen_collisions = MappingProxyType({k: tuple(v) for k, v in collisions.items()})
        return replace(base, union_field_collisions=frozen_collisions)
