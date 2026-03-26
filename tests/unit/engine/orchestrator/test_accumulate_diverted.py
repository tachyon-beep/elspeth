"""Tests for accumulate_row_outcomes DIVERTED branch."""

from __future__ import annotations

from unittest.mock import Mock

from elspeth.contracts import PendingOutcome, RowOutcome, TokenInfo
from elspeth.engine.orchestrator.outcomes import accumulate_row_outcomes
from elspeth.engine.orchestrator.types import ExecutionCounters
from elspeth.testing import make_token_info


def _make_result(
    outcome: RowOutcome,
    *,
    token: TokenInfo | None = None,
    sink_name: str | None = None,
) -> Mock:
    """Create a mock RowResult with the given outcome."""
    result = Mock()
    result.outcome = outcome
    result.token = token or make_token_info()
    result.sink_name = sink_name
    return result


def _make_pending() -> dict[str, list[tuple[TokenInfo, PendingOutcome | None]]]:
    return {"sink1": [], "sink2": []}


class TestAccumulateDiverted:
    def test_diverted_increments_rows_diverted(self) -> None:
        counters = ExecutionCounters()
        pending = _make_pending()
        results = [
            _make_result(RowOutcome.COMPLETED, sink_name="sink1"),
            _make_result(RowOutcome.DIVERTED, sink_name="sink1"),
            _make_result(RowOutcome.DIVERTED, sink_name="sink1"),
        ]
        accumulate_row_outcomes(results, counters, {"sink1": Mock(), "sink2": Mock()}, pending)
        assert counters.rows_diverted == 2

    def test_diverted_does_not_increment_rows_succeeded(self) -> None:
        """DIVERTED rows failed their primary sink write -- they are not 'succeeded'."""
        counters = ExecutionCounters()
        pending = _make_pending()
        results = [_make_result(RowOutcome.DIVERTED, sink_name="sink1")]
        accumulate_row_outcomes(results, counters, {"sink1": Mock(), "sink2": Mock()}, pending)
        assert counters.rows_diverted == 1
        assert counters.rows_succeeded == 0

    def test_diverted_mixed_with_other_outcomes(self) -> None:
        counters = ExecutionCounters()
        pending = _make_pending()
        results = [
            _make_result(RowOutcome.COMPLETED, sink_name="sink1"),
            _make_result(RowOutcome.DIVERTED, sink_name="sink1"),
            _make_result(RowOutcome.QUARANTINED),
            _make_result(RowOutcome.DIVERTED, sink_name="sink2"),
        ]
        accumulate_row_outcomes(results, counters, {"sink1": Mock(), "sink2": Mock()}, pending)
        assert counters.rows_succeeded == 1
        assert counters.rows_diverted == 2
        assert counters.rows_quarantined == 1
