"""Checkpoint and recovery domain contracts.

These types are used for checkpoint validation and resume operations.
They are NOT persisted to the audit trail (those are in audit.py).
"""

from __future__ import annotations

from dataclasses import dataclass

from elspeth.contracts.aggregation_checkpoint import AggregationCheckpointState
from elspeth.contracts.audit import Checkpoint
from elspeth.contracts.coalesce_checkpoint import CoalesceCheckpointState


@dataclass(frozen=True, slots=True)
class ResumeCheck:
    """Result of checking if a run can be resumed.

    Used by RecoveryManager and CheckpointCompatibilityValidator to
    communicate whether resume is possible and why/why not.
    """

    can_resume: bool
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.can_resume and self.reason is not None:
            raise ValueError("can_resume=True should not have a reason")
        if not self.can_resume and self.reason is None:
            raise ValueError("can_resume=False must have a reason explaining why")


@dataclass(frozen=True, slots=True)
class ResumePoint:
    """Information needed to resume a run.

    Contains all the data needed by Orchestrator.resume() to continue
    processing from where a failed run left off.
    """

    checkpoint: Checkpoint
    token_id: str
    node_id: str
    sequence_number: int
    aggregation_state: AggregationCheckpointState | None = None
    coalesce_state: CoalesceCheckpointState | None = None

    def __post_init__(self) -> None:
        """Validate resume point fields — Tier 1 crash on invalid data.

        Per CLAUDE.md Data Manifesto: Checkpoints are Tier 1 audit data.
        Empty token_id/node_id or negative sequence_number indicates
        corrupted checkpoint data — crash immediately.
        """
        if not self.token_id:
            raise ValueError("ResumePoint.token_id must not be empty")
        if not self.node_id:
            raise ValueError("ResumePoint.node_id must not be empty")
        if self.sequence_number < 0:
            raise ValueError(f"ResumePoint.sequence_number must be non-negative, got {self.sequence_number}")
