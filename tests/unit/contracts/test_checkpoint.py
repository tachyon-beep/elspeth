"""Unit tests for checkpoint/recovery domain contracts."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from elspeth.contracts import Checkpoint, ResumeCheck, ResumePoint
from elspeth.contracts.aggregation_checkpoint import (
    AggregationCheckpointState,
    AggregationNodeCheckpoint,
    AggregationTokenCheckpoint,
)


def _checkpoint() -> Checkpoint:
    return Checkpoint(
        checkpoint_id="cp-001",
        run_id="run-001",
        token_id="tok-001",
        node_id="node-001",
        sequence_number=1,
        created_at=datetime.now(UTC),
        upstream_topology_hash="a" * 64,
        checkpoint_node_config_hash="b" * 64,
        format_version=Checkpoint.CURRENT_FORMAT_VERSION,
    )


def _make_agg_state() -> AggregationCheckpointState:
    """Create a minimal typed aggregation checkpoint state for testing."""
    return AggregationCheckpointState(
        version="3.0",
        nodes={
            "node-001": AggregationNodeCheckpoint(
                tokens=(
                    AggregationTokenCheckpoint(
                        token_id="tok-buf-001",
                        row_id="row-buf-001",
                        branch_name=None,
                        fork_group_id=None,
                        join_group_id=None,
                        expand_group_id=None,
                        row_data={"buffered_rows": 2},
                        contract_version="abc123",
                    ),
                ),
                batch_id="batch-001",
                elapsed_age_seconds=0.0,
                count_fire_offset=None,
                condition_fire_offset=None,
                contract={"mode": "FLEXIBLE", "locked": False, "version_hash": "abc123", "fields": []},
            ),
        },
    )


def test_resume_check_accepts_true_without_reason() -> None:
    check = ResumeCheck(can_resume=True)
    assert check.can_resume is True
    assert check.reason is None


def test_resume_check_rejects_true_with_reason() -> None:
    with pytest.raises(ValueError, match="can_resume=True should not have a reason"):
        ResumeCheck(can_resume=True, reason="unexpected")


def test_resume_check_rejects_false_without_reason() -> None:
    with pytest.raises(ValueError, match="can_resume=False must have a reason"):
        ResumeCheck(can_resume=False)


def test_resume_point_accepts_typed_aggregation_state() -> None:
    agg_state = _make_agg_state()
    resume_point = ResumePoint(
        checkpoint=_checkpoint(),
        token_id="tok-001",
        node_id="node-001",
        sequence_number=1,
        aggregation_state=agg_state,
    )
    assert resume_point.aggregation_state is agg_state


def test_resume_point_accepts_none_aggregation_state() -> None:
    resume_point = ResumePoint(
        checkpoint=_checkpoint(),
        token_id="tok-001",
        node_id="node-001",
        sequence_number=1,
        aggregation_state=None,
    )
    assert resume_point.aggregation_state is None


def test_resume_point_rejects_non_dto_aggregation_state() -> None:
    with pytest.raises(ValueError, match="aggregation_state must be AggregationCheckpointState or None"):
        ResumePoint(
            checkpoint=_checkpoint(),
            token_id="tok-001",
            node_id="node-001",
            sequence_number=1,
            aggregation_state={"not": "a DTO"},  # type: ignore[arg-type]
        )
