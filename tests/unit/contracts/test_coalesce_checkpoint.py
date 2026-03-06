# tests/unit/contracts/test_coalesce_checkpoint.py
"""Unit tests for CoalesceTokenCheckpoint and CoalescePendingCheckpoint validation.

Covers __post_init__ invariant enforcement and from_dict error paths.
"""

from __future__ import annotations

import pytest

from elspeth.contracts.coalesce_checkpoint import (
    CoalescePendingCheckpoint,
    CoalesceTokenCheckpoint,
)
from elspeth.contracts.errors import AuditIntegrityError


def _valid_token_kwargs() -> dict:
    """Minimal valid kwargs for CoalesceTokenCheckpoint."""
    return {
        "token_id": "tok-1",
        "row_id": "row-1",
        "branch_name": "path_a",
        "fork_group_id": None,
        "join_group_id": None,
        "expand_group_id": None,
        "row_data": {"field": "value"},
        "contract": {"schema_version": "1"},
        "state_id": "state-1",
        "arrival_offset_seconds": 0.5,
    }


def _valid_token() -> CoalesceTokenCheckpoint:
    return CoalesceTokenCheckpoint(**_valid_token_kwargs())


class TestCoalesceTokenCheckpointPostInit:
    """__post_init__ validation for CoalesceTokenCheckpoint."""

    def test_valid_construction(self) -> None:
        """Valid kwargs produce a valid object."""
        token = _valid_token()
        assert token.token_id == "tok-1"

    @pytest.mark.parametrize("field", ["token_id", "row_id", "branch_name", "state_id"])
    def test_rejects_empty_string(self, field: str) -> None:
        """Required string fields must be non-empty."""
        kwargs = _valid_token_kwargs()
        kwargs[field] = ""
        with pytest.raises(ValueError, match=field):
            CoalesceTokenCheckpoint(**kwargs)

    @pytest.mark.parametrize("field", ["token_id", "row_id", "branch_name", "state_id"])
    def test_rejects_non_string(self, field: str) -> None:
        """Required string fields reject non-string types (e.g. corrupted JSON with int)."""
        kwargs = _valid_token_kwargs()
        kwargs[field] = 42
        with pytest.raises(ValueError, match=field):
            CoalesceTokenCheckpoint(**kwargs)

    def test_rejects_negative_arrival_offset(self) -> None:
        """arrival_offset_seconds must be non-negative."""
        kwargs = _valid_token_kwargs()
        kwargs["arrival_offset_seconds"] = -1.0
        with pytest.raises(ValueError, match="arrival_offset_seconds"):
            CoalesceTokenCheckpoint(**kwargs)

    def test_rejects_nan_arrival_offset(self) -> None:
        """NaN must not bypass the non-negative check."""
        kwargs = _valid_token_kwargs()
        kwargs["arrival_offset_seconds"] = float("nan")
        with pytest.raises(ValueError, match="arrival_offset_seconds"):
            CoalesceTokenCheckpoint(**kwargs)

    def test_rejects_inf_arrival_offset(self) -> None:
        """Infinity must not bypass the non-negative check."""
        kwargs = _valid_token_kwargs()
        kwargs["arrival_offset_seconds"] = float("inf")
        with pytest.raises(ValueError, match="arrival_offset_seconds"):
            CoalesceTokenCheckpoint(**kwargs)

    def test_rejects_non_dict_row_data(self) -> None:
        """row_data must be a dict."""
        kwargs = _valid_token_kwargs()
        kwargs["row_data"] = "not a dict"
        with pytest.raises(ValueError, match="row_data"):
            CoalesceTokenCheckpoint(**kwargs)

    def test_rejects_non_dict_contract(self) -> None:
        """contract must be a dict."""
        kwargs = _valid_token_kwargs()
        kwargs["contract"] = ["not", "a", "dict"]
        with pytest.raises(ValueError, match="contract"):
            CoalesceTokenCheckpoint(**kwargs)


class TestCoalescePendingCheckpointPostInit:
    """__post_init__ validation for CoalescePendingCheckpoint."""

    def test_valid_construction(self) -> None:
        """Valid kwargs produce a valid object."""
        pending = CoalescePendingCheckpoint(
            coalesce_name="merge_1",
            row_id="row-1",
            elapsed_age_seconds=1.5,
            branches={"path_a": _valid_token()},
            lost_branches={},
        )
        assert pending.coalesce_name == "merge_1"

    @pytest.mark.parametrize("field", ["coalesce_name", "row_id"])
    def test_rejects_empty_string(self, field: str) -> None:
        """Required string fields must be non-empty."""
        kwargs = {
            "coalesce_name": "merge_1",
            "row_id": "row-1",
            "elapsed_age_seconds": 1.5,
            "branches": {"path_a": _valid_token()},
            "lost_branches": {},
        }
        kwargs[field] = ""
        with pytest.raises(ValueError, match=field):
            CoalescePendingCheckpoint(**kwargs)

    def test_rejects_negative_elapsed_age(self) -> None:
        """elapsed_age_seconds must be non-negative."""
        with pytest.raises(ValueError, match="elapsed_age_seconds"):
            CoalescePendingCheckpoint(
                coalesce_name="merge_1",
                row_id="row-1",
                elapsed_age_seconds=-0.1,
                branches={},
                lost_branches={},
            )

    def test_rejects_nan_elapsed_age(self) -> None:
        """NaN must not bypass the non-negative check."""
        with pytest.raises(ValueError, match="elapsed_age_seconds"):
            CoalescePendingCheckpoint(
                coalesce_name="merge_1",
                row_id="row-1",
                elapsed_age_seconds=float("nan"),
                branches={},
                lost_branches={},
            )

    def test_rejects_inf_elapsed_age(self) -> None:
        """Infinity must not bypass the non-negative check."""
        with pytest.raises(ValueError, match="elapsed_age_seconds"):
            CoalescePendingCheckpoint(
                coalesce_name="merge_1",
                row_id="row-1",
                elapsed_age_seconds=float("inf"),
                branches={},
                lost_branches={},
            )

    def test_rejects_overlapping_branches_and_lost_branches(self) -> None:
        """branches and lost_branches must be disjoint."""
        token = _valid_token()
        with pytest.raises(ValueError, match="overlap"):
            CoalescePendingCheckpoint(
                coalesce_name="merge_1",
                row_id="row-1",
                elapsed_age_seconds=1.0,
                branches={"path_a": token},
                lost_branches={"path_a": "timed_out"},
            )


class TestCoalesceTokenCheckpointFromDict:
    """from_dict validation for CoalesceTokenCheckpoint."""

    def test_rejects_missing_fields(self) -> None:
        """from_dict raises AuditIntegrityError on missing required fields."""
        with pytest.raises(AuditIntegrityError, match="missing required fields"):
            CoalesceTokenCheckpoint.from_dict({"token_id": "tok-1"})

    def test_roundtrip(self) -> None:
        """to_dict → from_dict roundtrip preserves data."""
        original = _valid_token()
        restored = CoalesceTokenCheckpoint.from_dict(original.to_dict())
        assert restored == original


class TestCoalescePendingCheckpointFromDict:
    """from_dict validation for CoalescePendingCheckpoint."""

    def test_rejects_missing_fields(self) -> None:
        """from_dict raises AuditIntegrityError on missing required fields."""
        with pytest.raises(AuditIntegrityError, match="missing required fields"):
            CoalescePendingCheckpoint.from_dict({"coalesce_name": "merge_1"})

    def test_roundtrip(self) -> None:
        """to_dict → from_dict roundtrip preserves data."""
        token = _valid_token()
        original = CoalescePendingCheckpoint(
            coalesce_name="merge_1",
            row_id="row-1",
            elapsed_age_seconds=1.5,
            branches={"path_a": token},
            lost_branches={"path_b": "timed_out"},
        )
        restored = CoalescePendingCheckpoint.from_dict(original.to_dict())
        assert restored == original
