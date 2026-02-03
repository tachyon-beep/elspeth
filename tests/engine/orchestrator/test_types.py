# tests/engine/orchestrator/test_types.py
"""Tests for AggregationFlushResult dataclass.

These tests verify field ordering and semantics after migrating from a 9-element
tuple to a named dataclass. Field ordering bugs would be SILENT - counts could
swap between rows_succeeded and rows_failed without obvious test failures.

The test values (1,2,3,4,5,6,7,8,9) are deliberately distinct to catch any
field ordering mistakes during construction or addition.
"""

from dataclasses import FrozenInstanceError

import pytest

from elspeth.engine.orchestrator.types import AggregationFlushResult


class TestAggregationFlushResult:
    """Tests for the AggregationFlushResult dataclass."""

    def test_all_fields_accessible_by_name(self) -> None:
        """Verify each field is accessible by name (catches field omission)."""
        result = AggregationFlushResult(
            rows_succeeded=1,
            rows_failed=2,
            rows_routed=3,
            rows_quarantined=4,
            rows_coalesced=5,
            rows_forked=6,
            rows_expanded=7,
            rows_buffered=8,
            routed_destinations={"sink_a": 9},
        )

        # Each field must be accessible and have the correct value
        assert result.rows_succeeded == 1
        assert result.rows_failed == 2
        assert result.rows_routed == 3
        assert result.rows_quarantined == 4
        assert result.rows_coalesced == 5
        assert result.rows_forked == 6
        assert result.rows_expanded == 7
        assert result.rows_buffered == 8
        assert result.routed_destinations == {"sink_a": 9}

    def test_frozen_dataclass_immutability(self) -> None:
        """Verify frozen=True prevents mutation."""
        result = AggregationFlushResult(rows_succeeded=1)

        with pytest.raises(FrozenInstanceError):
            result.rows_succeeded = 999  # type: ignore[misc]

    def test_default_values(self) -> None:
        """Verify defaults are 0 for counts and empty dict for destinations."""
        result = AggregationFlushResult()

        assert result.rows_succeeded == 0
        assert result.rows_failed == 0
        assert result.rows_routed == 0
        assert result.rows_quarantined == 0
        assert result.rows_coalesced == 0
        assert result.rows_forked == 0
        assert result.rows_expanded == 0
        assert result.rows_buffered == 0
        assert result.routed_destinations == {}

    def test_addition_operator_sums_all_fields(self) -> None:
        """Verify __add__ correctly sums all fields."""
        result_a = AggregationFlushResult(
            rows_succeeded=1,
            rows_failed=2,
            rows_routed=3,
            rows_quarantined=4,
            rows_coalesced=5,
            rows_forked=6,
            rows_expanded=7,
            rows_buffered=8,
            routed_destinations={"sink_a": 10, "sink_b": 20},
        )
        result_b = AggregationFlushResult(
            rows_succeeded=10,
            rows_failed=20,
            rows_routed=30,
            rows_quarantined=40,
            rows_coalesced=50,
            rows_forked=60,
            rows_expanded=70,
            rows_buffered=80,
            routed_destinations={"sink_b": 30, "sink_c": 40},
        )

        combined = result_a + result_b

        assert combined.rows_succeeded == 11
        assert combined.rows_failed == 22
        assert combined.rows_routed == 33
        assert combined.rows_quarantined == 44
        assert combined.rows_coalesced == 55
        assert combined.rows_forked == 66
        assert combined.rows_expanded == 77
        assert combined.rows_buffered == 88
        assert combined.routed_destinations == {"sink_a": 10, "sink_b": 50, "sink_c": 40}

    def test_addition_operator_commutative(self) -> None:
        """Verify a + b == b + a (commutativity)."""
        result_a = AggregationFlushResult(
            rows_succeeded=1,
            rows_failed=2,
            rows_routed=3,
            rows_quarantined=4,
            rows_coalesced=5,
            rows_forked=6,
            rows_expanded=7,
            rows_buffered=8,
            routed_destinations={"sink_a": 10},
        )
        result_b = AggregationFlushResult(
            rows_succeeded=10,
            rows_failed=20,
            rows_routed=30,
            rows_quarantined=40,
            rows_coalesced=50,
            rows_forked=60,
            rows_expanded=70,
            rows_buffered=80,
            routed_destinations={"sink_b": 20},
        )

        assert result_a + result_b == result_b + result_a

    def test_addition_with_zero_result(self) -> None:
        """Verify adding zero-result is identity operation."""
        result = AggregationFlushResult(
            rows_succeeded=1,
            rows_failed=2,
            rows_routed=3,
            rows_quarantined=4,
            rows_coalesced=5,
            rows_forked=6,
            rows_expanded=7,
            rows_buffered=8,
            routed_destinations={"sink_a": 9},
        )
        zero = AggregationFlushResult()

        # Adding zero should return equivalent result
        assert result + zero == result
        assert zero + result == result
