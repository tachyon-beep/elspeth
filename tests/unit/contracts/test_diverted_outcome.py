"""Test DIVERTED RowOutcome and RunResult.rows_diverted."""

from __future__ import annotations

import pytest

from elspeth.contracts.enums import RowOutcome, RunStatus
from elspeth.contracts.run_result import RunResult


class TestDivertedOutcome:
    def test_diverted_value(self) -> None:
        assert RowOutcome.DIVERTED == "diverted"
        assert RowOutcome.DIVERTED.value == "diverted"

    def test_diverted_is_terminal(self) -> None:
        assert RowOutcome.DIVERTED.is_terminal is True

    def test_diverted_in_terminal_set(self) -> None:
        """DIVERTED should be in the same category as QUARANTINED and ROUTED."""
        terminal_outcomes = [o for o in RowOutcome if o.is_terminal]
        assert RowOutcome.DIVERTED in terminal_outcomes


class TestRunResultDiverted:
    def test_rows_diverted_default_zero(self) -> None:
        result = RunResult(
            run_id="test-1",
            status=RunStatus.COMPLETED,
            rows_processed=10,
            rows_succeeded=8,
            rows_failed=2,
            rows_routed=0,
        )
        assert result.rows_diverted == 0

    def test_rows_diverted_explicit(self) -> None:
        result = RunResult(
            run_id="test-1",
            status=RunStatus.COMPLETED,
            rows_processed=10,
            rows_succeeded=7,
            rows_failed=0,
            rows_routed=0,
            rows_diverted=3,
        )
        assert result.rows_diverted == 3

    def test_rows_diverted_negative_rejected(self) -> None:
        with pytest.raises(ValueError, match="rows_diverted"):
            RunResult(
                run_id="test-1",
                status=RunStatus.COMPLETED,
                rows_processed=10,
                rows_succeeded=10,
                rows_failed=0,
                rows_routed=0,
                rows_diverted=-1,
            )
