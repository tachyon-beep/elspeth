# tests/unit/engine/orchestrator/test_outcomes.py
"""Tests for row outcome accumulation and coalesce handling functions.

outcomes.py was extracted from duplicated RowOutcome switch blocks in
_execute_run() and _process_resumed_rows(). These tests verify that:
1. Every RowOutcome variant is correctly accumulated
2. Coalesce timeouts trigger downstream processing
3. End-of-source coalesce flush handles all paths
"""

from __future__ import annotations

from typing import Any
from unittest.mock import Mock

import pytest

from elspeth.contracts import PendingOutcome, RowOutcome, TokenInfo
from elspeth.contracts.types import CoalesceName, NodeID
from elspeth.engine.orchestrator.outcomes import (
    accumulate_row_outcomes,
    flush_coalesce_pending,
    handle_coalesce_timeouts,
)
from elspeth.engine.orchestrator.types import ExecutionCounters
from elspeth.testing import make_row, make_token_info

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
        results = [_make_result(RowOutcome.COMPLETED, sink_name="output")]

        accumulate_row_outcomes(results, counters, {"output": Mock()}, pending)

        assert counters.rows_succeeded == 1

    def test_completed_appends_to_sink(self) -> None:
        counters = _make_counters()
        pending = _make_pending()
        results = [_make_result(RowOutcome.COMPLETED, sink_name="output")]

        accumulate_row_outcomes(results, counters, {"output": Mock()}, pending)

        assert len(pending["output"]) == 1
        pending_outcome = pending["output"][0][1]
        assert pending_outcome is not None
        assert pending_outcome.outcome == RowOutcome.COMPLETED

    def test_completed_ignores_branch_name_and_uses_result_sink(self) -> None:
        """COMPLETED routing uses result.sink_name, not token.branch_name."""
        counters = _make_counters()
        pending: dict[str, list[tuple[TokenInfo, PendingOutcome | None]]] = {"output": [], "branch_a": []}
        token = TokenInfo(row_id="row-1", token_id="tok-1", row_data=make_row({}), branch_name="branch_a")
        results = [_make_result(RowOutcome.COMPLETED, token=token, sink_name="output")]

        accumulate_row_outcomes(results, counters, {"output": Mock(), "branch_a": Mock()}, pending)

        assert len(pending["branch_a"]) == 0
        assert len(pending["output"]) == 1

    def test_completed_falls_back_to_sink_name_when_branch_not_in_sinks(self) -> None:
        """COMPLETED token with branch_name not in sinks uses result.sink_name."""
        counters = _make_counters()
        pending = _make_pending()
        token = TokenInfo(row_id="row-1", token_id="tok-1", row_data=make_row({}), branch_name="nonexistent")
        results = [_make_result(RowOutcome.COMPLETED, token=token, sink_name="output")]

        accumulate_row_outcomes(results, counters, {"output": Mock()}, pending)

        assert len(pending["output"]) == 1


class TestAccumulateRowOutcomesRouted:
    """Tests for ROUTED outcome handling."""

    def test_routed_increments_counter(self) -> None:
        counters = _make_counters()
        pending: dict[str, list[tuple[TokenInfo, PendingOutcome | None]]] = {"output": [], "risk_sink": []}
        results = [_make_result(RowOutcome.ROUTED, sink_name="risk_sink")]

        accumulate_row_outcomes(results, counters, {"output": Mock()}, pending)

        assert counters.rows_routed == 1

    def test_routed_tracks_destination(self) -> None:
        counters = _make_counters()
        pending: dict[str, list[tuple[TokenInfo, PendingOutcome | None]]] = {"output": [], "risk_sink": []}
        results = [_make_result(RowOutcome.ROUTED, sink_name="risk_sink")]

        accumulate_row_outcomes(results, counters, {"output": Mock()}, pending)

        assert counters.routed_destinations["risk_sink"] == 1

    def test_routed_appends_to_named_sink(self) -> None:
        counters = _make_counters()
        pending: dict[str, list[tuple[TokenInfo, PendingOutcome | None]]] = {"output": [], "risk_sink": []}
        results = [_make_result(RowOutcome.ROUTED, sink_name="risk_sink")]

        accumulate_row_outcomes(results, counters, {"output": Mock()}, pending)

        assert len(pending["risk_sink"]) == 1
        pending_outcome = pending["risk_sink"][0][1]
        assert pending_outcome is not None
        assert pending_outcome.outcome == RowOutcome.ROUTED

    def test_routed_without_sink_name_crashes(self) -> None:
        """ROUTED outcome without sink_name is a contract violation."""
        from elspeth.contracts.errors import OrchestrationInvariantError

        counters = _make_counters()
        pending = _make_pending()
        results = [_make_result(RowOutcome.ROUTED, sink_name=None)]

        with pytest.raises(OrchestrationInvariantError, match="not in configured sinks"):
            accumulate_row_outcomes(results, counters, {"output": Mock()}, pending)


class TestAccumulateRowOutcomesTerminal:
    """Tests for terminal outcome types that only increment counters."""

    def test_failed_increments_counter(self) -> None:
        counters = _make_counters()
        pending = _make_pending()
        results = [_make_result(RowOutcome.FAILED)]

        accumulate_row_outcomes(results, counters, {"output": Mock()}, pending)

        assert counters.rows_failed == 1
        assert len(pending["output"]) == 0

    def test_quarantined_increments_counter(self) -> None:
        counters = _make_counters()
        pending = _make_pending()
        results = [_make_result(RowOutcome.QUARANTINED)]

        accumulate_row_outcomes(results, counters, {"output": Mock()}, pending)

        assert counters.rows_quarantined == 1

    def test_forked_increments_counter(self) -> None:
        counters = _make_counters()
        pending = _make_pending()
        results = [_make_result(RowOutcome.FORKED)]

        accumulate_row_outcomes(results, counters, {"output": Mock()}, pending)

        assert counters.rows_forked == 1

    def test_expanded_increments_counter(self) -> None:
        counters = _make_counters()
        pending = _make_pending()
        results = [_make_result(RowOutcome.EXPANDED)]

        accumulate_row_outcomes(results, counters, {"output": Mock()}, pending)

        assert counters.rows_expanded == 1

    def test_buffered_increments_counter(self) -> None:
        counters = _make_counters()
        pending = _make_pending()
        results = [_make_result(RowOutcome.BUFFERED)]

        accumulate_row_outcomes(results, counters, {"output": Mock()}, pending)

        assert counters.rows_buffered == 1

    def test_consumed_in_batch_is_noop(self) -> None:
        """CONSUMED_IN_BATCH doesn't increment any counter (counted on batch flush)."""
        counters = _make_counters()
        pending = _make_pending()
        results = [_make_result(RowOutcome.CONSUMED_IN_BATCH)]

        accumulate_row_outcomes(results, counters, {"output": Mock()}, pending)

        assert counters.rows_succeeded == 0
        assert counters.rows_failed == 0


class TestAccumulateRowOutcomesCoalesced:
    """Tests for COALESCED outcome handling."""

    def test_coalesced_increments_both_counters(self) -> None:
        """COALESCED increments both rows_coalesced AND rows_succeeded."""
        counters = _make_counters()
        pending = _make_pending()
        results = [_make_result(RowOutcome.COALESCED, sink_name="output")]

        accumulate_row_outcomes(results, counters, {"output": Mock()}, pending)

        assert counters.rows_coalesced == 1
        assert counters.rows_succeeded == 1

    def test_coalesced_routes_to_sink(self) -> None:
        counters = _make_counters()
        pending = _make_pending()
        results = [_make_result(RowOutcome.COALESCED, sink_name="output")]

        accumulate_row_outcomes(results, counters, {"output": Mock()}, pending)

        assert len(pending["output"]) == 1
        pending_outcome = pending["output"][0][1]
        assert pending_outcome is not None
        assert pending_outcome.outcome == RowOutcome.COMPLETED


class TestAccumulateRowOutcomesMixed:
    """Tests for multiple results in a single call."""

    def test_multiple_results_accumulated(self) -> None:
        """All results in the iterable are processed."""
        counters = _make_counters()
        pending = _make_pending()
        results = [
            _make_result(RowOutcome.COMPLETED, sink_name="output"),
            _make_result(RowOutcome.COMPLETED, sink_name="output"),
            _make_result(RowOutcome.FAILED),
            _make_result(RowOutcome.QUARANTINED),
        ]

        accumulate_row_outcomes(results, counters, {"output": Mock()}, pending)

        assert counters.rows_succeeded == 2
        assert counters.rows_failed == 1
        assert counters.rows_quarantined == 1
        assert len(pending["output"]) == 2

    def test_empty_results_is_noop(self) -> None:
        """Empty results list changes nothing."""
        counters = _make_counters()
        pending = _make_pending()

        accumulate_row_outcomes([], counters, {"output": Mock()}, pending)

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
    ) -> tuple[Mock, Mock, ExecutionCounters, dict[str, list[tuple[TokenInfo, PendingOutcome | None]]], dict[CoalesceName, NodeID]]:
        coalesce_executor = Mock()
        coalesce_executor.get_registered_names.return_value = ["merge_1"]
        coalesce_executor.check_timeouts.return_value = timed_out_outcomes or []

        processor = Mock()
        processor.process_token.return_value = []
        processor.resolve_node_step.return_value = coalesce_step

        counters = _make_counters()
        pending = _make_pending()
        coalesce_node_map = {CoalesceName("merge_1"): NodeID("coalesce::merge_1")}

        return coalesce_executor, processor, counters, pending, coalesce_node_map

    def test_no_timeouts_is_noop(self) -> None:
        """No timed-out coalesces means nothing happens."""
        executor, processor, counters, pending, node_map = self._setup()

        handle_coalesce_timeouts(
            coalesce_executor=executor,
            coalesce_node_map=node_map,
            processor=processor,
            config_transforms=[Mock(), Mock()],
            config_sinks={"output": Mock()},
            ctx=Mock(),
            counters=counters,
            pending_tokens=pending,
        )

        assert counters.rows_coalesced == 0
        processor.process_token.assert_not_called()

    def test_merged_token_with_downstream_continues_processing(self) -> None:
        """Merged token continues through remaining transforms."""
        merged_token = make_token_info()
        outcome = Mock()
        outcome.merged_token = merged_token
        outcome.failure_reason = None

        executor, processor, counters, pending, node_map = self._setup(
            timed_out_outcomes=[outcome],
            total_transforms=3,
            coalesce_step=1,
        )
        # Simulate downstream producing a COMPLETED result
        processor.process_token.return_value = [
            _make_result(RowOutcome.COMPLETED, token=merged_token, sink_name="output"),
        ]

        ctx = Mock()
        transforms: list[Any] = [Mock(), Mock(), Mock()]
        handle_coalesce_timeouts(
            coalesce_executor=executor,
            coalesce_node_map=node_map,
            processor=processor,
            config_transforms=transforms,
            config_sinks={"output": Mock()},
            ctx=ctx,
            counters=counters,
            pending_tokens=pending,
        )

        assert counters.rows_coalesced == 1
        assert counters.rows_succeeded == 1
        processor.process_token.assert_called_once_with(
            token=merged_token,
            transforms=transforms,
            ctx=ctx,
            current_node_id=NodeID("coalesce::merge_1"),
            coalesce_node_id=NodeID("coalesce::merge_1"),
            coalesce_name=CoalesceName("merge_1"),
        )

    def test_merged_token_terminal_processed_for_explicit_sink_routing(self) -> None:
        """Terminal merged token is processed to resolve explicit on_success sink."""
        merged_token = make_token_info()
        outcome = Mock()
        outcome.merged_token = merged_token
        outcome.failure_reason = None

        executor, processor, counters, pending, node_map = self._setup(
            timed_out_outcomes=[outcome],
            total_transforms=1,
            coalesce_step=1,  # step == total_steps
        )
        processor.process_token.return_value = [_make_result(RowOutcome.COMPLETED, token=merged_token, sink_name="output")]

        ctx = Mock()
        transforms: list[Any] = [Mock()]
        handle_coalesce_timeouts(
            coalesce_executor=executor,
            coalesce_node_map=node_map,
            processor=processor,
            config_transforms=transforms,
            config_sinks={"output": Mock()},
            ctx=ctx,
            counters=counters,
            pending_tokens=pending,
        )

        assert counters.rows_coalesced == 1
        assert counters.rows_succeeded == 1
        assert len(pending["output"]) == 1
        processor.process_token.assert_called_once_with(
            token=merged_token,
            transforms=transforms,
            ctx=ctx,
            current_node_id=NodeID("coalesce::merge_1"),
            coalesce_node_id=NodeID("coalesce::merge_1"),
            coalesce_name=CoalesceName("merge_1"),
        )

    def test_failure_increments_coalesce_failed(self) -> None:
        """Failed coalesce (missing branches) increments coalesce_failed."""
        outcome = Mock()
        outcome.merged_token = None
        outcome.failure_reason = "quorum_not_met"

        executor, processor, counters, pending, node_map = self._setup(
            timed_out_outcomes=[outcome],
        )

        handle_coalesce_timeouts(
            coalesce_executor=executor,
            coalesce_node_map=node_map,
            processor=processor,
            config_transforms=[Mock(), Mock()],
            config_sinks={"output": Mock()},
            ctx=Mock(),
            counters=counters,
            pending_tokens=pending,
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
            _make_result(RowOutcome.COMPLETED, token=merged_token, sink_name="output"),
        ]
        processor.resolve_node_step.return_value = 0

        counters = _make_counters()
        pending = _make_pending()
        node_map = {CoalesceName("merge_1"): NodeID("coalesce::merge_1")}

        ctx = Mock()
        transforms: list[Any] = [Mock(), Mock()]
        flush_coalesce_pending(
            coalesce_executor=coalesce_executor,
            coalesce_node_map=node_map,
            processor=processor,
            config_transforms=transforms,
            config_sinks={"output": Mock()},
            ctx=ctx,
            counters=counters,
            pending_tokens=pending,
        )

        assert counters.rows_coalesced == 1
        assert counters.rows_succeeded == 1
        processor.process_token.assert_called_once_with(
            token=merged_token,
            transforms=transforms,
            ctx=ctx,
            current_node_id=NodeID("coalesce::merge_1"),
            coalesce_node_id=NodeID("coalesce::merge_1"),
            coalesce_name=CoalesceName("merge_1"),
        )

    def test_merged_token_terminal(self) -> None:
        """Terminal merged token is processed to resolve explicit on_success sink."""
        merged_token = make_token_info()
        outcome = Mock()
        outcome.merged_token = merged_token
        outcome.failure_reason = None
        outcome.coalesce_name = "merge_1"

        coalesce_executor = Mock()
        coalesce_executor.flush_pending.return_value = [outcome]

        processor = Mock()
        processor.resolve_node_step.return_value = 1
        processor.process_token.return_value = [_make_result(RowOutcome.COMPLETED, token=merged_token, sink_name="output")]
        counters = _make_counters()
        pending = _make_pending()
        node_map = {CoalesceName("merge_1"): NodeID("coalesce::merge_1")}

        ctx = Mock()
        transforms: list[Any] = [Mock()]
        flush_coalesce_pending(
            coalesce_executor=coalesce_executor,
            coalesce_node_map=node_map,
            processor=processor,
            config_transforms=transforms,
            config_sinks={"output": Mock()},
            ctx=ctx,
            counters=counters,
            pending_tokens=pending,
        )

        assert counters.rows_coalesced == 1
        assert counters.rows_succeeded == 1
        assert len(pending["output"]) == 1
        processor.process_token.assert_called_once_with(
            token=merged_token,
            transforms=transforms,
            ctx=ctx,
            current_node_id=NodeID("coalesce::merge_1"),
            coalesce_node_id=NodeID("coalesce::merge_1"),
            coalesce_name=CoalesceName("merge_1"),
        )

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
            coalesce_node_map={},
            processor=Mock(),
            config_transforms=[],
            config_sinks={"output": Mock()},
            ctx=Mock(),
            counters=counters,
            pending_tokens=pending,
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
            coalesce_node_map={},
            processor=Mock(),
            config_transforms=[],
            config_sinks={"output": Mock()},
            ctx=Mock(),
            counters=counters,
            pending_tokens=pending,
        )

        assert counters.rows_coalesced == 0
        assert counters.rows_coalesce_failed == 0
