# src/elspeth/engine/orchestrator/outcomes.py
"""Row outcome accumulation functions for the orchestrator.

This module contains functions for:
- Accumulating row processing outcomes into ExecutionCounters
- Handling coalesce timeout checks per-row
- Flushing pending coalesce operations at end-of-source

All functions operate on external state passed via parameters - they don't
maintain internal state. This follows the same pattern as aggregation.py:
pure delegation targets for the Orchestrator.

These functions were extracted from _execute_run() and _process_resumed_rows()
to eliminate ~400 lines of duplicated code. The extraction also fixed bugs
where the resume path was missing `rows_succeeded += 1` for coalesce
timeout continuations (lines 2124, 2139-2143 in the original).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, Any

from elspeth.contracts import PendingOutcome, RowOutcome, TokenInfo
from elspeth.contracts.errors import OrchestrationInvariantError
from elspeth.contracts.types import CoalesceName, NodeID
from elspeth.engine.orchestrator.types import ExecutionCounters

if TYPE_CHECKING:
    from elspeth.contracts.plugin_context import PluginContext
    from elspeth.engine.coalesce_executor import CoalesceExecutor
    from elspeth.engine.processor import RowProcessor


def _require_sink_name(result: Any) -> str:
    """Require sink_name for outcomes that must route to a sink.

    Replaces cast(str, result.sink_name) which is a no-op at runtime.
    If sink_name is None, this is a Tier 1 invariant violation (our data).
    """
    name: str | None = result.sink_name
    if name is None:
        raise OrchestrationInvariantError(f"Result with outcome {result.outcome} missing sink_name. Token: {result.token}")
    return name


def accumulate_row_outcomes(
    results: Iterable[Any],
    counters: ExecutionCounters,
    config_sinks: Mapping[str, object],
    pending_tokens: dict[str, list[tuple[TokenInfo, PendingOutcome | None]]],
) -> None:
    """Accumulate row processing outcomes into counters and pending_tokens.

    Replaces the RowOutcome switch block that was duplicated 4 times in
    _execute_run() and _process_resumed_rows() (main loop, coalesce timeout
    continuations, coalesce flush continuations).

    This single implementation ensures consistent counting across all paths.
    In particular, COALESCED outcomes always increment rows_succeeded (fixing
    the bug where the resume path omitted this).

    Routing is determined by result.sink_name (set by on_success routing in
    the processor) rather than a default_sink_name parameter.

    Args:
        results: Iterable of RowProcessingResult from processor.process_row/process_token
        counters: Mutable ExecutionCounters to update
        config_sinks: Dict of sink_name -> sink plugin (for sink validation)
        pending_tokens: Dict of sink_name -> list of (token, pending_outcome) pairs
    """
    for result in results:
        if result.outcome == RowOutcome.COMPLETED:
            counters.rows_succeeded += 1
            # RowResult.__post_init__ guarantees sink_name is set for COMPLETED
            sink_name = _require_sink_name(result)
            if sink_name not in pending_tokens:
                raise OrchestrationInvariantError(
                    f"Sink '{sink_name}' from result.sink_name not in configured sinks. "
                    f"Available: {sorted(pending_tokens.keys())}. Token: {result.token}"
                )
            pending_tokens[sink_name].append((result.token, PendingOutcome(RowOutcome.COMPLETED)))
        elif result.outcome == RowOutcome.ROUTED:
            counters.rows_routed += 1
            sink_name = _require_sink_name(result)
            counters.routed_destinations[sink_name] += 1
            if sink_name not in pending_tokens:
                raise OrchestrationInvariantError(
                    f"Routed sink '{sink_name}' not in configured sinks. Available: {sorted(pending_tokens.keys())}. Token: {result.token}"
                )
            pending_tokens[sink_name].append((result.token, PendingOutcome(RowOutcome.ROUTED)))
        elif result.outcome == RowOutcome.FAILED:
            counters.rows_failed += 1
        elif result.outcome == RowOutcome.QUARANTINED:
            counters.rows_quarantined += 1
        elif result.outcome == RowOutcome.FORKED:
            counters.rows_forked += 1
            # Children are counted separately when they reach terminal state
        elif result.outcome == RowOutcome.CONSUMED_IN_BATCH:
            # Aggregated - will be counted when batch flushes
            pass
        elif result.outcome == RowOutcome.COALESCED:
            # Merged token from coalesce - route to output sink
            # Use result.sink_name set by on_success routing
            sink_name = _require_sink_name(result)
            counters.rows_coalesced += 1
            counters.rows_succeeded += 1
            if sink_name not in pending_tokens:
                raise OrchestrationInvariantError(
                    f"Coalesced sink '{sink_name}' not in configured sinks. "
                    f"Available: {sorted(pending_tokens.keys())}. Token: {result.token}"
                )
            pending_tokens[sink_name].append((result.token, PendingOutcome(RowOutcome.COMPLETED)))
        elif result.outcome == RowOutcome.EXPANDED:
            # Deaggregation parent token - children counted separately
            counters.rows_expanded += 1
        elif result.outcome == RowOutcome.BUFFERED:
            # Passthrough mode buffered token
            counters.rows_buffered += 1


def handle_coalesce_timeouts(
    coalesce_executor: CoalesceExecutor,
    coalesce_node_map: dict[CoalesceName, NodeID],
    processor: RowProcessor,
    config_sinks: Mapping[str, object],
    ctx: PluginContext,
    counters: ExecutionCounters,
    pending_tokens: dict[str, list[tuple[TokenInfo, PendingOutcome | None]]],
) -> None:
    """Check and handle coalesce timeouts after processing each row.

    Extracted from the per-row coalesce timeout block that was duplicated in
    _execute_run() (lines 1286-1340) and _process_resumed_rows() (lines 2102-2145).

    Uses accumulate_row_outcomes() for downstream continuation handling, which
    fixes the bug where the resume path omitted `rows_succeeded += 1` for
    COMPLETED coalesce continuations.

    Args:
        coalesce_executor: CoalesceExecutor managing join barriers
        coalesce_node_map: Maps CoalesceName -> coalesce node ID in graph
        processor: RowProcessor for downstream processing
        config_sinks: Dict of sink_name -> sink plugin (for sink validation)
        ctx: Plugin context for transform execution
        counters: Mutable ExecutionCounters to update
        pending_tokens: Dict of sink_name -> tokens to append results to
    """
    for coalesce_name_str in coalesce_executor.get_registered_names():
        coalesce_name = CoalesceName(coalesce_name_str)
        coalesce_node_id = coalesce_node_map[coalesce_name]
        timed_out = coalesce_executor.check_timeouts(
            coalesce_name=coalesce_name_str,
        )
        for outcome in timed_out:
            if outcome.merged_token is not None:
                counters.rows_coalesced += 1
                # Route merged token through processor from the coalesce node.
                # Processor internals decide terminal vs non-terminal using DAG
                # continuation metadata and return COMPLETED with sink_name when terminal.
                continuation_results = processor.process_token(
                    token=outcome.merged_token,
                    ctx=ctx,
                    current_node_id=coalesce_node_id,
                    coalesce_node_id=coalesce_node_id,
                    coalesce_name=coalesce_name,
                )
                accumulate_row_outcomes(
                    continuation_results,
                    counters,
                    config_sinks,
                    pending_tokens,
                )
            elif outcome.failure_reason:
                counters.rows_coalesce_failed += 1


def flush_coalesce_pending(
    coalesce_executor: CoalesceExecutor,
    coalesce_node_map: dict[CoalesceName, NodeID],
    processor: RowProcessor,
    config_sinks: Mapping[str, object],
    ctx: PluginContext,
    counters: ExecutionCounters,
    pending_tokens: dict[str, list[tuple[TokenInfo, PendingOutcome | None]]],
) -> None:
    """Flush pending coalesce operations at end-of-source.

    Extracted from the end-of-source coalesce flush that was duplicated in
    _execute_run() (lines 1420-1476) and _process_resumed_rows() (lines 2172-2221).

    Uses accumulate_row_outcomes() for consistent downstream outcome handling.

    Args:
        coalesce_executor: CoalesceExecutor managing join barriers
        coalesce_node_map: Maps CoalesceName -> coalesce node ID in graph
        processor: RowProcessor for downstream processing
        config_sinks: Dict of sink_name -> sink plugin (for sink validation)
        ctx: Plugin context for transform execution
        counters: Mutable ExecutionCounters to update
        pending_tokens: Dict of sink_name -> tokens to append results to
    """
    pending_outcomes = coalesce_executor.flush_pending()

    # Handle any merged tokens from flush
    for outcome in pending_outcomes:
        if outcome.merged_token is not None:
            # Successful merge
            counters.rows_coalesced += 1
            # Business logic: coalesce_name is guaranteed non-None when merged_token is not None
            assert outcome.coalesce_name is not None, "Coalesce outcome must have coalesce_name when merged_token exists"
            coalesce_name = CoalesceName(outcome.coalesce_name)
            # Route merged token through processor from the coalesce node.
            # Processor internals decide terminal vs non-terminal using DAG
            # continuation metadata and return COMPLETED with sink_name when terminal.
            continuation_results = processor.process_token(
                token=outcome.merged_token,
                ctx=ctx,
                current_node_id=coalesce_node_map[coalesce_name],
                coalesce_node_id=coalesce_node_map[coalesce_name],
                coalesce_name=coalesce_name,
            )
            accumulate_row_outcomes(
                continuation_results,
                counters,
                config_sinks,
                pending_tokens,
            )
        elif outcome.failure_reason:
            # Coalesce failed (quorum_not_met, incomplete_branches)
            # Audit trail recorded by executor: each consumed token has
            # node_state with status="failed" and error_json explaining why.
            counters.rows_coalesce_failed += 1
