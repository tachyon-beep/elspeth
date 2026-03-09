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
from typing import TYPE_CHECKING

from elspeth.contracts import PendingOutcome, RowOutcome
from elspeth.contracts.errors import OrchestrationInvariantError
from elspeth.contracts.types import CoalesceName, NodeID
from elspeth.engine.orchestrator.types import ExecutionCounters, PendingTokenMap

if TYPE_CHECKING:
    from elspeth.contracts.plugin_context import PluginContext
    from elspeth.contracts.results import RowResult
    from elspeth.engine.coalesce_executor import CoalesceExecutor, CoalesceOutcome
    from elspeth.engine.processor import RowProcessor


def _require_sink_name(result: RowResult) -> str:
    """Require sink_name for outcomes that must route to a sink.

    Replaces cast(str, result.sink_name) which is a no-op at runtime.
    If sink_name is None, this is a Tier 1 invariant violation (our data).
    """
    name: str | None = result.sink_name
    if name is None:
        raise OrchestrationInvariantError(f"Result with outcome {result.outcome} missing sink_name. Token: {result.token}")
    return name


def accumulate_row_outcomes(
    results: Iterable[RowResult],
    counters: ExecutionCounters,
    config_sinks: Mapping[str, object],
    pending_tokens: PendingTokenMap,
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
        else:
            raise OrchestrationInvariantError(f"Unhandled RowOutcome variant: {result.outcome!r}. Token: {result.token}")


def _validate_coalesce_outcome(outcome: CoalesceOutcome) -> bool:
    """Validate CoalesceOutcome invariant and return whether it has a merged token.

    Raises OrchestrationInvariantError if the outcome has both or neither of
    merged_token and failure_reason — exactly one must be set.

    Returns:
        True if outcome has a merged token, False if it has a failure.
    """
    has_merged = outcome.merged_token is not None
    has_failure = outcome.failure_reason is not None
    if has_merged == has_failure:
        raise OrchestrationInvariantError(
            f"Invalid CoalesceOutcome state: merged={has_merged}, "
            f"failure_reason={outcome.failure_reason!r}. "
            f"Outcome must have exactly one of merged_token or failure_reason."
        )
    return has_merged


def _process_merged_coalesce_outcome(
    outcome: CoalesceOutcome,
    coalesce_name: CoalesceName,
    coalesce_node_map: dict[CoalesceName, NodeID],
    processor: RowProcessor,
    config_sinks: Mapping[str, object],
    ctx: PluginContext,
    counters: ExecutionCounters,
    pending_tokens: PendingTokenMap,
) -> None:
    """Process a successfully merged CoalesceOutcome through the processor.

    Extracted from handle_coalesce_timeouts and flush_coalesce_pending which
    had identical merge routing logic.
    """
    counters.rows_coalesced += 1
    merged_token = outcome.merged_token
    if merged_token is None:
        raise OrchestrationInvariantError("CoalesceOutcome has_merged=True but merged_token is None")
    coalesce_node_id = coalesce_node_map[coalesce_name]
    continuation_results = processor.process_token(
        token=merged_token,
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


def handle_coalesce_timeouts(
    coalesce_executor: CoalesceExecutor,
    coalesce_node_map: dict[CoalesceName, NodeID],
    processor: RowProcessor,
    config_sinks: Mapping[str, object],
    ctx: PluginContext,
    counters: ExecutionCounters,
    pending_tokens: PendingTokenMap,
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
        timed_out = coalesce_executor.check_timeouts(
            coalesce_name=coalesce_name_str,
        )
        for outcome in timed_out:
            if _validate_coalesce_outcome(outcome):
                _process_merged_coalesce_outcome(
                    outcome,
                    coalesce_name,
                    coalesce_node_map,
                    processor,
                    config_sinks,
                    ctx,
                    counters,
                    pending_tokens,
                )
            else:
                counters.rows_coalesce_failed += 1


def flush_coalesce_pending(
    coalesce_executor: CoalesceExecutor,
    coalesce_node_map: dict[CoalesceName, NodeID],
    processor: RowProcessor,
    config_sinks: Mapping[str, object],
    ctx: PluginContext,
    counters: ExecutionCounters,
    pending_tokens: PendingTokenMap,
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

    for outcome in pending_outcomes:
        if _validate_coalesce_outcome(outcome):
            # flush_pending outcomes carry coalesce_name on the outcome itself
            if outcome.coalesce_name is None:
                raise OrchestrationInvariantError(
                    "CoalesceOutcome has merged_token but coalesce_name is None. This indicates a bug in CoalesceExecutor.flush_pending()."
                )
            coalesce_name = CoalesceName(outcome.coalesce_name)
            _process_merged_coalesce_outcome(
                outcome,
                coalesce_name,
                coalesce_node_map,
                processor,
                config_sinks,
                ctx,
                counters,
                pending_tokens,
            )
        else:
            counters.rows_coalesce_failed += 1
