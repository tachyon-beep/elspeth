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
from elspeth.contracts.coalesce_checkpoint import (
    CoalesceCheckpointState,
    CoalescePendingCheckpoint,
    CoalesceTokenCheckpoint,
)
from elspeth.contracts.errors import AuditIntegrityError


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


def test_resume_point_accepts_typed_coalesce_state() -> None:
    coalesce_state = CoalesceCheckpointState(
        version="1.0",
        pending=(
            CoalescePendingCheckpoint(
                coalesce_name="merge_paths",
                row_id="row-001",
                elapsed_age_seconds=1.5,
                branches={
                    "branch_a": CoalesceTokenCheckpoint(
                        token_id="tok-branch-a",
                        row_id="row-001",
                        branch_name="branch_a",
                        fork_group_id="fork-1",
                        join_group_id=None,
                        expand_group_id=None,
                        row_data={"value": 1},
                        contract={"mode": "OBSERVED", "locked": True, "fields": []},
                        state_id="state-123",
                        arrival_offset_seconds=0.0,
                    )
                },
                lost_branches={},
            ),
        ),
        completed_keys=(),
    )

    resume_point = ResumePoint(
        checkpoint=_checkpoint(),
        token_id="tok-001",
        node_id="node-001",
        sequence_number=1,
        coalesce_state=coalesce_state,
    )
    assert resume_point.coalesce_state is coalesce_state


def test_resume_point_rejects_empty_token_id() -> None:
    with pytest.raises(ValueError, match="token_id must not be empty"):
        ResumePoint(
            checkpoint=_checkpoint(),
            token_id="",
            node_id="node-001",
            sequence_number=1,
        )


def test_resume_point_rejects_empty_node_id() -> None:
    with pytest.raises(ValueError, match="node_id must not be empty"):
        ResumePoint(
            checkpoint=_checkpoint(),
            token_id="tok-001",
            node_id="",
            sequence_number=1,
        )


def test_resume_point_rejects_negative_sequence_number() -> None:
    with pytest.raises(ValueError, match="sequence_number must be non-negative"):
        ResumePoint(
            checkpoint=_checkpoint(),
            token_id="tok-001",
            node_id="node-001",
            sequence_number=-1,
        )


def test_resume_point_accepts_zero_sequence_number() -> None:
    resume_point = ResumePoint(
        checkpoint=_checkpoint(),
        token_id="tok-001",
        node_id="node-001",
        sequence_number=0,
    )
    assert resume_point.sequence_number == 0


# === AggregationNodeCheckpoint.from_dict corruption tests ===


def _valid_node_dict() -> dict:
    """Complete valid node checkpoint dict for mutation in corruption tests."""
    return {
        "tokens": [
            {
                "token_id": "tok-001",
                "row_id": "row-001",
                "branch_name": None,
                "fork_group_id": None,
                "join_group_id": None,
                "expand_group_id": None,
                "row_data": {"x": 1},
                "contract_version": "abc123",
            }
        ],
        "batch_id": "batch-001",
        "elapsed_age_seconds": 0.0,
        "count_fire_offset": None,
        "condition_fire_offset": None,
        "contract": {"mode": "FLEXIBLE"},
    }


def test_node_from_dict_round_trip() -> None:
    """Valid dict round-trips through from_dict → to_dict."""
    data = _valid_node_dict()
    node = AggregationNodeCheckpoint.from_dict("node-001", data)
    assert node.batch_id == "batch-001"
    assert node.count_fire_offset is None
    assert node.condition_fire_offset is None
    rt = node.to_dict()
    assert rt["count_fire_offset"] is None
    assert rt["condition_fire_offset"] is None


def test_node_from_dict_missing_count_fire_offset_raises() -> None:
    """Missing count_fire_offset is corruption — must crash, not silently return None."""
    data = _valid_node_dict()
    del data["count_fire_offset"]

    with pytest.raises(AuditIntegrityError, match="count_fire_offset"):
        AggregationNodeCheckpoint.from_dict("node-001", data)


def test_node_from_dict_missing_condition_fire_offset_raises() -> None:
    """Missing condition_fire_offset is corruption — must crash, not silently return None."""
    data = _valid_node_dict()
    del data["condition_fire_offset"]

    with pytest.raises(AuditIntegrityError, match="condition_fire_offset"):
        AggregationNodeCheckpoint.from_dict("node-001", data)


def test_node_from_dict_missing_elapsed_age_raises_with_context() -> None:
    """Missing elapsed_age_seconds should raise AuditIntegrityError with node_id context."""
    data = _valid_node_dict()
    del data["elapsed_age_seconds"]

    with pytest.raises(AuditIntegrityError, match="node-001"):
        AggregationNodeCheckpoint.from_dict("node-001", data)


def test_node_from_dict_multiple_missing_fields_reports_all() -> None:
    """All missing fields reported in one error, not just the first one found."""
    data = _valid_node_dict()
    del data["elapsed_age_seconds"]
    del data["count_fire_offset"]
    del data["condition_fire_offset"]

    with pytest.raises(AuditIntegrityError, match="missing required fields") as exc_info:
        AggregationNodeCheckpoint.from_dict("node-001", data)

    msg = str(exc_info.value)
    assert "elapsed_age_seconds" in msg
    assert "count_fire_offset" in msg
    assert "condition_fire_offset" in msg


# === Aggregation checkpoint type guard tests ===


def test_aggregation_token_rejects_non_dict_row_data() -> None:
    """row_data type guard rejects non-dict values with clear error."""
    with pytest.raises(ValueError, match="row_data must be a dict"):
        AggregationTokenCheckpoint(
            token_id="tok-001",
            row_id="row-001",
            branch_name=None,
            fork_group_id=None,
            join_group_id=None,
            expand_group_id=None,
            row_data="not a dict",  # type: ignore[arg-type]
            contract_version="abc123",
        )


def test_aggregation_node_rejects_non_dict_contract() -> None:
    """contract type guard rejects non-dict values with clear error."""
    with pytest.raises(ValueError, match="contract must be a dict"):
        AggregationNodeCheckpoint(
            tokens=(),
            batch_id="batch-001",
            elapsed_age_seconds=0.0,
            count_fire_offset=None,
            condition_fire_offset=None,
            contract=["not", "a", "dict"],  # type: ignore[arg-type]
        )
