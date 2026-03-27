"""Tests for accumulate_row_outcomes DIVERTED invariant.

DIVERTED outcomes are counted in SinkExecutor (via _write_pending_to_sinks
return value), NOT in the processing loop. If a DIVERTED outcome appears
in processing results, that's an orchestration bug.
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from elspeth.contracts import RowOutcome, TokenInfo
from elspeth.contracts.errors import OrchestrationInvariantError
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


def _make_pending() -> dict[str, list]:
    return {"sink1": [], "sink2": []}


class TestAccumulateDiverted:
    def test_diverted_raises_invariant_error(self) -> None:
        """DIVERTED in processing results is an orchestration bug."""
        counters = ExecutionCounters()
        pending = _make_pending()
        results = [_make_result(RowOutcome.DIVERTED, sink_name="sink1")]
        with pytest.raises(OrchestrationInvariantError, match="DIVERTED outcome should not appear"):
            accumulate_row_outcomes(results, counters, {"sink1": Mock()}, pending)

    def test_diverted_after_completed_still_raises(self) -> None:
        """Even mixed with valid outcomes, DIVERTED crashes."""
        counters = ExecutionCounters()
        pending = _make_pending()
        results = [
            _make_result(RowOutcome.COMPLETED, sink_name="sink1"),
            _make_result(RowOutcome.DIVERTED, sink_name="sink1"),
        ]
        with pytest.raises(OrchestrationInvariantError, match="DIVERTED outcome should not appear"):
            accumulate_row_outcomes(results, counters, {"sink1": Mock(), "sink2": Mock()}, pending)
