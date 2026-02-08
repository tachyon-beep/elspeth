# tests/unit/engine/orchestrator/test_outcomes.py
"""Tests for row outcome accumulation and coalesce handling functions.

outcomes.py was extracted from duplicated RowOutcome switch blocks in
_execute_run() and _process_resumed_rows(). These tests verify that:
1. Every RowOutcome variant is correctly accumulated
2. Coalesce timeouts trigger downstream processing
3. End-of-source coalesce flush handles all paths
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from elspeth.contracts import PendingOutcome, RowOutcome, TokenInfo
from elspeth.contracts.types import CoalesceName
from elspeth.engine.orchestrator.outcomes import (
    accumulate_row_outcomes,
    flush_coalesce_pending,
    handle_coalesce_timeouts,
)
from elspeth.engine.orchestrator.types import ExecutionCounters
from tests.fixtures.factories import make_row, make_token_info

# =============================================================================
# Helpers
# =============================================================================


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


def _make_counters() -> ExecutionCounters:
    return ExecutionCounters()


def _make_pending() -> dict[str, list[tuple[TokenInfo, PendingOutcome | None]]]:
    return {"output": [], "error_sink": []}


# =============================================================================
# accumulate_row_outcomes — Individual outcome types
# =============================================================================


class TestAccumulateRowOutcomesCompleted:
    """Tests for COMPLETED outcome handling."""

    def test_completed_increments_succeeded(self) -> None:
        counters = _make_counters()
        pending = _make_pending()
        results = [_make_result(RowOutcome.COMPLETED)]

        accumulate_row_outcomes(results, counters, {"output": Mock()}, "output", pending)

        assert counters.rows_succeeded == 1

    def test_completed_appends_to_default_sink(self) -> None:
        counters = _make_counters()
        pending = _make_pending()
        results = [_make_result(RowOutcome.COMPLETED)]

        accumulate_row_outcomes(results, counters, {"output": Mock()}, "output", pending)

        assert len(pending["output"]) == 1
        assert pending["output"][0][1].outcome == RowOutcome.COMPLETED

    def test_completed_routes_to_branch_sink_when_exists(self) -> None:
        """COMPLETED tokens with branch_name route to that sink if it exists."""
        counters = _make_counters()
        pending = {"output": [], "branch_a": []}
        token = TokenInfo(row_id="row-1", token_id="tok-1", row_data=make_row({}), branch_name="branch_a")
        results = [_make_result(RowOutcome.COMPLETED, token=token)]

        accumulate_row_outcomes(results, counters, {"output": Mock(), "branch_a": Mock()}, "output", pending)

        assert len(pending["branch_a"]) == 1
        assert len(pending["output"]) == 0

    def test_completed_falls_back_to_default_when_branch_not_in_sinks(self) -> None:
        """COMPLETED token with branch_name not in sinks falls back to default."""
        counters = _make_counters()
        pending = _make_pending()
        token = TokenInfo(row_id="row-1", token_id="tok-1", row_data=make_row({}), branch_name="nonexistent")
        results = [_make_result(RowOutcome.COMPLETED, token=token)]

        accumulate_row_outcomes(results, counters, {"output": Mock()}, "output", pending)

        assert len(pending["output"]) == 1


class TestAccumulateRowOutcomesRouted:
    """Tests for ROUTED outcome handling."""

    def test_routed_increments_counter(self) -> None:
        counters = _make_counters()
        pending = {"output": [], "risk_sink": []}
        results = [_make_result(RowOutcome.ROUTED, sink_name="risk_sink")]

        accumulate_row_outcomes(results, counters, {"output": Mock()}, "output", pending)

        assert counters.rows_routed == 1

    def test_routed_tracks_destination(self) -> None:
        counters = _make_counters()
        pending = {"output": [], "risk_sink": []}
        results = [_make_result(RowOutcome.ROUTED, sink_name="risk_sink")]

        accumulate_row_outcomes(results, counters, {"output": Mock()}, "output", pending)

        assert counters.routed_destinations["risk_sink"] == 1

    def test_routed_appends_to_named_sink(self) -> None:
        counters = _make_counters()
        pending = {"output": [], "risk_sink": []}
        results = [_make_result(RowOutcome.ROUTED, sink_name="risk_sink")]

        accumulate_row_outcomes(results, counters, {"output": Mock()}, "output", pending)

        assert len(pending["risk_sink"]) == 1
        assert pending["risk_sink"][0][1].outcome == RowOutcome.ROUTED

    def test_routed_without_sink_name_crashes(self) -> None:
        """ROUTED outcome without sink_name is a contract violation."""
        counters = _make_counters()
        pending = _make_pending()
        results = [_make_result(RowOutcome.ROUTED, sink_name=None)]

        with pytest.raises(RuntimeError, match="ROUTED outcome requires sink_name"):
            accumulate_row_outcomes(results, counters, {"output": Mock()}, "output", pending)


class TestAccumulateRowOutcomesTerminal:
    """Tests for terminal outcome types that only increment counters."""

    def test_failed_increments_counter(self) -> None:
        counters = _make_counters()
        pending = _make_pending()
        results = [_make_result(RowOutcome.FAILED)]

        accumulate_row_outcomes(results, counters, {"output": Mock()}, "output", pending)

        assert counters.rows_failed == 1
        assert len(pending["output"]) == 0

    def test_quarantined_increments_counter(self) -> None:
        counters = _make_counters()
        pending = _make_pending()
        results = [_make_result(RowOutcome.QUARANTINED)]

        accumulate_row_outcomes(results, counters, {"output": Mock()}, "output", pending)

        assert counters.rows_quarantined == 1

    def test_forked_increments_counter(self) -> None:
        counters = _make_counters()
        pending = _make_pending()
        results = [_make_result(RowOutcome.FORKED)]

        accumulate_row_outcomes(results, counters, {"output": Mock()}, "output", pending)

        assert counters.rows_forked == 1

    def test_expanded_increments_counter(self) -> None:
        counters = _make_counters()
        pending = _make_pending()
        results = [_make_result(RowOutcome.EXPANDED)]

        accumulate_row_outcomes(results, counters, {"output": Mock()}, "output", pending)

        assert counters.rows_expanded == 1

    def test_buffered_increments_counter(self) -> None:
        counters = _make_counters()
        pending = _make_pending()
        results = [_make_result(RowOutcome.BUFFERED)]

        accumulate_row_outcomes(results, counters, {"output": Mock()}, "output", pending)

        assert counters.rows_buffered == 1

    def test_consumed_in_batch_is_noop(self) -> None:
        """CONSUMED_IN_BATCH doesn't increment any counter (counted on batch flush)."""
        counters = _make_counters()
        pending = _make_pending()
        results = [_make_result(RowOutcome.CONSUMED_IN_BATCH)]

        accumulate_row_outcomes(results, counters, {"output": Mock()}, "output", pending)

        assert counters.rows_succeeded == 0
        assert counters.rows_failed == 0


class TestAccumulateRowOutcomesCoalesced:
    """Tests for COALESCED outcome handling."""

    def test_coalesced_increments_both_counters(self) -> None:
        """COALESCED increments both rows_coalesced AND rows_succeeded."""
        counters = _make_counters()
        pending = _make_pending()
        results = [_make_result(RowOutcome.COALESCED)]

        accumulate_row_outcomes(results, counters, {"output": Mock()}, "output", pending)

        assert counters.rows_coalesced == 1
        assert counters.rows_succeeded == 1

    def test_coalesced_routes_to_default_sink(self) -> None:
        counters = _make_counters()
        pending = _make_pending()
        results = [_make_result(RowOutcome.COALESCED)]

        accumulate_row_outcomes(results, counters, {"output": Mock()}, "output", pending)

        assert len(pending["output"]) == 1
        assert pending["output"][0][1].outcome == RowOutcome.COMPLETED


class TestAccumulateRowOutcomesMixed:
    """Tests for multiple results in a single call."""

    def test_multiple_results_accumulated(self) -> None:
        """All results in the iterable are processed."""
        counters = _make_counters()
        pending = _make_pending()
        results = [
            _make_result(RowOutcome.COMPLETED),
            _make_result(RowOutcome.COMPLETED),
            _make_result(RowOutcome.FAILED),
            _make_result(RowOutcome.QUARANTINED),
        ]

        accumulate_row_outcomes(results, counters, {"output": Mock()}, "output", pending)

        assert counters.rows_succeeded == 2
        assert counters.rows_failed == 1
        assert counters.rows_quarantined == 1
        assert len(pending["output"]) == 2

    def test_empty_results_is_noop(self) -> None:
        """Empty results list changes nothing."""
        counters = _make_counters()
        pending = _make_pending()

        accumulate_row_outcomes([], counters, {"output": Mock()}, "output", pending)

        assert counters.rows_succeeded == 0
        assert counters.rows_failed == 0


# =============================================================================
# handle_coalesce_timeouts
# =============================================================================


class TestHandleCoalesceTimeouts:
    """Tests for per-row coalesce timeout checks."""

    def _setup(
        self,
        *,
        timed_out_outcomes: list[Mock] | None = None,
        total_transforms: int = 2,
        coalesce_step: int = 1,
    ) -> tuple[Mock, Mock, ExecutionCounters, dict, dict]:
        coalesce_executor = Mock()
        coalesce_executor.get_registered_names.return_value = ["merge_1"]
        coalesce_executor.check_timeouts.return_value = timed_out_outcomes or []

        processor = Mock()
        processor.process_token.return_value = []

        counters = _make_counters()
        pending = _make_pending()
        coalesce_step_map = {CoalesceName("merge_1"): coalesce_step}

        return coalesce_executor, processor, counters, pending, coalesce_step_map

    def test_no_timeouts_is_noop(self) -> None:
        """No timed-out coalesces means nothing happens."""
        executor, processor, counters, pending, step_map = self._setup()

        handle_coalesce_timeouts(
            coalesce_executor=executor,
            coalesce_step_map=step_map,
            processor=processor,
            config_transforms=[Mock(), Mock()],
            config_gates=[],
            config_sinks={"output": Mock()},
            ctx=Mock(),
            counters=counters,
            pending_tokens=pending,
            default_sink_name="output",
        )

        assert counters.rows_coalesced == 0
        processor.process_token.assert_not_called()

    def test_merged_token_with_downstream_continues_processing(self) -> None:
        """Merged token continues through remaining transforms."""
        merged_token = make_token_info()
        outcome = Mock()
        outcome.merged_token = merged_token
        outcome.failure_reason = None

        executor, processor, counters, pending, step_map = self._setup(
            timed_out_outcomes=[outcome],
            total_transforms=3,
            coalesce_step=1,
        )
        # Simulate downstream producing a COMPLETED result
        processor.process_token.return_value = [
            _make_result(RowOutcome.COMPLETED, token=merged_token),
        ]

        handle_coalesce_timeouts(
            coalesce_executor=executor,
            coalesce_step_map=step_map,
            processor=processor,
            config_transforms=[Mock(), Mock(), Mock()],
            config_gates=[],
            config_sinks={"output": Mock()},
            ctx=Mock(),
            counters=counters,
            pending_tokens=pending,
            default_sink_name="output",
        )

        assert counters.rows_coalesced == 1
        assert counters.rows_succeeded == 1
        processor.process_token.assert_called_once()

    def test_merged_token_terminal_goes_to_sink_directly(self) -> None:
        """Merged token at last step goes directly to sink (no downstream)."""
        merged_token = make_token_info()
        outcome = Mock()
        outcome.merged_token = merged_token
        outcome.failure_reason = None

        executor, processor, counters, pending, step_map = self._setup(
            timed_out_outcomes=[outcome],
            total_transforms=1,
            coalesce_step=1,  # step == total_steps
        )

        handle_coalesce_timeouts(
            coalesce_executor=executor,
            coalesce_step_map=step_map,
            processor=processor,
            config_transforms=[Mock()],
            config_gates=[],
            config_sinks={"output": Mock()},
            ctx=Mock(),
            counters=counters,
            pending_tokens=pending,
            default_sink_name="output",
        )

        assert counters.rows_coalesced == 1
        assert counters.rows_succeeded == 1
        assert len(pending["output"]) == 1
        processor.process_token.assert_not_called()

    def test_failure_increments_coalesce_failed(self) -> None:
        """Failed coalesce (missing branches) increments coalesce_failed."""
        outcome = Mock()
        outcome.merged_token = None
        outcome.failure_reason = "quorum_not_met"

        executor, processor, counters, pending, step_map = self._setup(
            timed_out_outcomes=[outcome],
        )

        handle_coalesce_timeouts(
            coalesce_executor=executor,
            coalesce_step_map=step_map,
            processor=processor,
            config_transforms=[Mock(), Mock()],
            config_gates=[],
            config_sinks={"output": Mock()},
            ctx=Mock(),
            counters=counters,
            pending_tokens=pending,
            default_sink_name="output",
        )

        assert counters.rows_coalesce_failed == 1
        assert counters.rows_coalesced == 0


# =============================================================================
# flush_coalesce_pending
# =============================================================================


class TestFlushCoalescePending:
    """Tests for end-of-source coalesce flush."""

    def test_merged_token_with_downstream(self) -> None:
        """Merged tokens from flush continue through downstream transforms."""
        merged_token = make_token_info()
        outcome = Mock()
        outcome.merged_token = merged_token
        outcome.failure_reason = None
        outcome.coalesce_name = "merge_1"

        coalesce_executor = Mock()
        coalesce_executor.flush_pending.return_value = [outcome]

        processor = Mock()
        processor.process_token.return_value = [
            _make_result(RowOutcome.COMPLETED, token=merged_token),
        ]

        counters = _make_counters()
        pending = _make_pending()
        step_map = {CoalesceName("merge_1"): 0}

        flush_coalesce_pending(
            coalesce_executor=coalesce_executor,
            coalesce_step_map=step_map,
            processor=processor,
            config_transforms=[Mock(), Mock()],
            config_gates=[],
            config_sinks={"output": Mock()},
            ctx=Mock(),
            counters=counters,
            pending_tokens=pending,
            default_sink_name="output",
        )

        assert counters.rows_coalesced == 1
        assert counters.rows_succeeded == 1

    def test_merged_token_terminal(self) -> None:
        """Terminal merged token goes directly to sink."""
        merged_token = make_token_info()
        outcome = Mock()
        outcome.merged_token = merged_token
        outcome.failure_reason = None
        outcome.coalesce_name = "merge_1"

        coalesce_executor = Mock()
        coalesce_executor.flush_pending.return_value = [outcome]

        processor = Mock()
        counters = _make_counters()
        pending = _make_pending()
        step_map = {CoalesceName("merge_1"): 1}

        flush_coalesce_pending(
            coalesce_executor=coalesce_executor,
            coalesce_step_map=step_map,
            processor=processor,
            config_transforms=[Mock()],
            config_gates=[],
            config_sinks={"output": Mock()},
            ctx=Mock(),
            counters=counters,
            pending_tokens=pending,
            default_sink_name="output",
        )

        assert counters.rows_coalesced == 1
        assert counters.rows_succeeded == 1
        assert len(pending["output"]) == 1
        processor.process_token.assert_not_called()

    def test_failure_increments_coalesce_failed(self) -> None:
        """Failed flush outcomes increment coalesce_failed counter."""
        outcome = Mock()
        outcome.merged_token = None
        outcome.failure_reason = "incomplete_branches"
        outcome.coalesce_name = None

        coalesce_executor = Mock()
        coalesce_executor.flush_pending.return_value = [outcome]

        counters = _make_counters()
        pending = _make_pending()

        flush_coalesce_pending(
            coalesce_executor=coalesce_executor,
            coalesce_step_map={},
            processor=Mock(),
            config_transforms=[],
            config_gates=[],
            config_sinks={"output": Mock()},
            ctx=Mock(),
            counters=counters,
            pending_tokens=pending,
            default_sink_name="output",
        )

        assert counters.rows_coalesce_failed == 1

    def test_empty_flush_is_noop(self) -> None:
        """No pending coalesces means nothing happens."""
        coalesce_executor = Mock()
        coalesce_executor.flush_pending.return_value = []

        counters = _make_counters()
        pending = _make_pending()

        flush_coalesce_pending(
            coalesce_executor=coalesce_executor,
            coalesce_step_map={},
            processor=Mock(),
            config_transforms=[],
            config_gates=[],
            config_sinks={"output": Mock()},
            ctx=Mock(),
            counters=counters,
            pending_tokens=pending,
            default_sink_name="output",
        )

        assert counters.rows_coalesced == 0
        assert counters.rows_coalesce_failed == 0
