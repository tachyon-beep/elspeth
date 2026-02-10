# src/elspeth/engine/orchestrator/aggregation.py
"""Aggregation handling functions for the orchestrator.

This module contains functions for:
- Finding aggregation transforms by node ID
- Handling incomplete batches during recovery
- Checking and flushing aggregation timeouts
- Flushing remaining aggregation buffers at end-of-source

All functions operate on external state passed via parameters - they don't
maintain internal state. This enables the Orchestrator to use them as
pure delegation targets.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from typing import TYPE_CHECKING, cast

from elspeth.contracts import PendingOutcome, RowOutcome, TokenInfo
from elspeth.contracts.enums import TriggerType
from elspeth.contracts.errors import OrchestrationInvariantError
from elspeth.contracts.types import NodeID
from elspeth.engine.orchestrator.types import AggregationFlushResult, PipelineConfig

if TYPE_CHECKING:
    from elspeth.contracts.plugin_context import PluginContext
    from elspeth.contracts.results import RowResult
    from elspeth.core.landscape import LandscapeRecorder
    from elspeth.engine.processor import RowProcessor
    from elspeth.plugins.protocols import TransformProtocol


def _route_aggregation_outcome(
    result: RowResult,
    pending_tokens: dict[str, list[tuple[TokenInfo, PendingOutcome | None]]],
    checkpoint_callback: Callable[[TokenInfo], None] | None = None,
) -> None:
    """Route a non-failed aggregation result to the appropriate sink.

    Consolidates the routing logic that was previously duplicated across 4 blocks
    in check_aggregation_timeouts() and flush_remaining_aggregation_buffers().

    Routing uses result.sink_name which is set by on_success routing in the
    processor. The sink_name is authoritative for COMPLETED results (guaranteed
    by RowResult.__post_init__).

    Args:
        result: A non-FAILED RowResult from aggregation processing
        pending_tokens: Dict of sink_name -> tokens to append results to
        checkpoint_callback: Optional callback after successful routing
    """
    sink_name = cast(str, result.sink_name)
    if sink_name not in pending_tokens:
        raise OrchestrationInvariantError(
            f"Aggregation result sink '{sink_name}' not in configured sinks. "
            f"Available: {sorted(pending_tokens.keys())}. Token: {result.token}"
        )
    pending_tokens[sink_name].append((result.token, PendingOutcome(result.outcome)))

    if checkpoint_callback is not None:
        checkpoint_callback(result.token)


def find_aggregation_transform(
    config: PipelineConfig,
    agg_node_id_str: str,
    agg_name: str,
) -> tuple[TransformProtocol, NodeID]:
    """Find the batch-aware transform for an aggregation node.

    Args:
        config: Pipeline configuration with transforms
        agg_node_id_str: The aggregation node ID as string
        agg_name: Human-readable aggregation name (for error messages)

    Returns:
        Tuple of (transform, aggregation_node_id)

    Raises:
        RuntimeError: If no batch-aware transform found for the aggregation
    """
    from elspeth.plugins.protocols import TransformProtocol

    agg_transform: TransformProtocol | None = None
    agg_node_id = NodeID(agg_node_id_str)

    for t in config.transforms:
        if isinstance(t, TransformProtocol) and t.node_id == agg_node_id_str and t.is_batch_aware:
            agg_transform = t
            break

    if agg_transform is None:
        raise RuntimeError(
            f"No batch-aware transform found for aggregation '{agg_name}' "
            f"(node_id={agg_node_id_str}). This indicates a bug in graph construction "
            f"or pipeline configuration. "
            f"Available transforms: {[t.node_id for t in config.transforms]}"
        )

    return agg_transform, agg_node_id


def handle_incomplete_batches(
    recorder: LandscapeRecorder,
    run_id: str,
) -> None:
    """Find and handle incomplete batches for recovery.

    - EXECUTING batches: Mark as failed (crash interrupted), then retry
    - FAILED batches: Retry with incremented attempt
    - DRAFT batches: Leave as-is (collection continues)

    Args:
        recorder: LandscapeRecorder for database operations
        run_id: Run being recovered
    """
    from elspeth.contracts.enums import BatchStatus

    incomplete = recorder.get_incomplete_batches(run_id)

    for batch in incomplete:
        if batch.status == BatchStatus.EXECUTING:
            # Crash interrupted mid-execution, mark failed then retry
            recorder.update_batch_status(batch.batch_id, BatchStatus.FAILED)
            recorder.retry_batch(batch.batch_id)
        elif batch.status == BatchStatus.FAILED:
            # Previous failure, retry
            recorder.retry_batch(batch.batch_id)
        # DRAFT batches continue normally (collection resumes)


def check_aggregation_timeouts(
    config: PipelineConfig,
    processor: RowProcessor,
    ctx: PluginContext,
    pending_tokens: dict[str, list[tuple[TokenInfo, PendingOutcome | None]]],
    agg_transform_lookup: dict[str, tuple[TransformProtocol, NodeID]] | None = None,
) -> AggregationFlushResult:
    """Check and flush any aggregations whose timeout has expired.

    Called BEFORE processing each row to ensure timeouts fire during active
    processing, not just at end-of-source. Checking BEFORE buffering ensures
    timed-out batches don't include the newly arriving row.

    Bug fix: P1-2026-01-22-aggregation-timeout-idle-never-fires
    Before this fix, should_flush() was only called from buffer_row(),
    meaning timeouts never fired during idle periods between rows.

    KNOWN LIMITATION (True Idle):
    Timeouts fire when the next row arrives, not during "true idle" periods.
    If no rows arrive, buffered data will not flush until either:
    1. A new row arrives (triggering this timeout check), or
    2. The source completes (triggering flush_remaining_aggregation_buffers)

    Example: If timeout_seconds=5 and rows stop arriving at T=10, the batch
    won't flush until either a new row arrives or the source ends. For
    streaming sources that may never end, consider using count triggers or
    implementing periodic polling at the source level.

    Routing uses result.sink_name (set by on_success in the processor) rather
    than a default_sink_name parameter.

    Args:
        config: Pipeline configuration with aggregation_settings
        processor: RowProcessor with public aggregation timeout API
        ctx: Plugin context for transform execution
        pending_tokens: Dict of sink_name -> tokens to append results to
        agg_transform_lookup: Pre-computed dict mapping node_id_str ->
            (transform, aggregation_node_id).
            If None, lookup is computed on each call (less efficient).

    Returns:
        AggregationFlushResult with counts for succeeded, failed, routed,
        quarantined, coalesced, forked, expanded, buffered rows and routed_destinations
    """
    rows_succeeded = 0
    rows_failed = 0
    rows_routed = 0
    rows_quarantined = 0
    rows_coalesced = 0
    rows_forked = 0
    rows_expanded = 0
    rows_buffered = 0
    routed_destinations: Counter[str] = Counter()

    for agg_node_id_str, agg_settings in config.aggregation_settings.items():
        agg_node_id = NodeID(agg_node_id_str)

        # Use public facade method to check timeout (no private member access)
        should_flush, trigger_type = processor.check_aggregation_timeout(agg_node_id)

        if not should_flush:
            continue

        # Skip if not a timeout trigger - count triggers are handled in buffer_row
        if trigger_type != TriggerType.TIMEOUT:
            continue

        # Check if there are buffered rows
        buffered_count = processor.get_aggregation_buffer_count(agg_node_id)
        if buffered_count == 0:
            continue

        # Get transform and aggregation node from pre-computed lookup (O(1)) or compute (O(n))
        if agg_transform_lookup and agg_node_id_str in agg_transform_lookup:
            agg_transform, _agg_node_id = agg_transform_lookup[agg_node_id_str]
        else:
            # Fallback: use helper method if lookup not provided
            agg_transform, _agg_node_id = find_aggregation_transform(config, agg_node_id_str, agg_settings.name)

        # Use handle_timeout_flush for proper output_mode handling.
        # Continuation is node-based inside the processor.
        completed_results, work_items = processor.handle_timeout_flush(
            node_id=agg_node_id,
            transform=agg_transform,
            ctx=ctx,
            trigger_type=TriggerType.TIMEOUT,
        )

        # Handle completed results (no more transforms - go to sink)
        for result in completed_results:
            if result.outcome == RowOutcome.FAILED:
                rows_failed += 1
            else:
                _route_aggregation_outcome(result, pending_tokens)
                rows_succeeded += 1

        # Process work items through remaining transforms
        # These tokens need to continue through the pipeline
        for work_item in work_items:
            if work_item.current_node_id is None:
                raise RuntimeError("Aggregation continuation work item missing current_node_id")
            downstream_results = processor.process_token(
                token=work_item.token,
                transforms=config.transforms,
                ctx=ctx,
                current_node_id=work_item.current_node_id,
                coalesce_node_id=work_item.coalesce_node_id,
                coalesce_name=work_item.coalesce_name,
            )

            for result in downstream_results:
                if result.outcome == RowOutcome.FAILED:
                    rows_failed += 1
                elif result.outcome == RowOutcome.COMPLETED:
                    _route_aggregation_outcome(result, pending_tokens)
                    rows_succeeded += 1
                elif result.outcome == RowOutcome.ROUTED:
                    rows_routed += 1
                    routed_sink = cast(str, result.sink_name)
                    routed_destinations[routed_sink] += 1
                    pending_tokens[routed_sink].append((result.token, PendingOutcome(RowOutcome.ROUTED)))
                elif result.outcome == RowOutcome.QUARANTINED:
                    rows_quarantined += 1
                elif result.outcome == RowOutcome.COALESCED:
                    sink_name = cast(str, result.sink_name)
                    rows_coalesced += 1
                    rows_succeeded += 1
                    pending_tokens[sink_name].append((result.token, PendingOutcome(RowOutcome.COMPLETED)))
                elif result.outcome == RowOutcome.FORKED:
                    rows_forked += 1
                elif result.outcome == RowOutcome.EXPANDED:
                    rows_expanded += 1
                elif result.outcome == RowOutcome.BUFFERED:
                    rows_buffered += 1
                # CONSUMED_IN_BATCH is handled within process_token

    return AggregationFlushResult(
        rows_succeeded=rows_succeeded,
        rows_failed=rows_failed,
        rows_routed=rows_routed,
        rows_quarantined=rows_quarantined,
        rows_coalesced=rows_coalesced,
        rows_forked=rows_forked,
        rows_expanded=rows_expanded,
        rows_buffered=rows_buffered,
        routed_destinations=dict(routed_destinations),
    )


def flush_remaining_aggregation_buffers(
    config: PipelineConfig,
    processor: RowProcessor,
    ctx: PluginContext,
    pending_tokens: dict[str, list[tuple[TokenInfo, PendingOutcome | None]]],
    checkpoint_callback: Callable[[TokenInfo], None] | None = None,
) -> AggregationFlushResult:
    """Flush remaining aggregation buffers at end-of-source.

    Without this, rows buffered but not yet flushed (e.g., 50 rows
    when trigger is count=100) would be silently lost.

    Uses handle_timeout_flush with END_OF_SOURCE trigger to properly handle
    all output_mode semantics (single, passthrough, transform) and route
    tokens through remaining transforms if any exist after the aggregation.

    Routing uses result.sink_name (set by on_success in the processor) rather
    than a default_sink_name parameter.

    Args:
        config: Pipeline configuration with aggregation_settings
        processor: RowProcessor with public aggregation facades
        ctx: Plugin context for transform execution
        pending_tokens: Dict of sink_name -> tokens to append results to
        checkpoint_callback: Optional callback to create checkpoint after successful
            token processing. Called with the token that was processed. The callback
            should capture run_id, node_id, and processor for getting aggregation state.

    Returns:
        AggregationFlushResult with counts for succeeded, failed, routed,
        quarantined, coalesced, forked, expanded, buffered rows and routed_destinations

    Raises:
        RuntimeError: If no batch-aware transform found for an aggregation
                     (indicates bug in graph construction or pipeline config)
    """
    rows_succeeded = 0
    rows_failed = 0
    rows_routed = 0
    rows_quarantined = 0
    rows_coalesced = 0
    rows_forked = 0
    rows_expanded = 0
    rows_buffered = 0
    routed_destinations: Counter[str] = Counter()
    for agg_node_id_str, agg_settings in config.aggregation_settings.items():
        agg_node_id = NodeID(agg_node_id_str)

        # Use public facade (not private member)
        buffered_count = processor.get_aggregation_buffer_count(agg_node_id)
        if buffered_count == 0:
            continue

        # Use helper method for transform lookup
        agg_transform, _agg_node_id = find_aggregation_transform(config, agg_node_id_str, agg_settings.name)

        # Use handle_timeout_flush with END_OF_SOURCE trigger
        # This properly handles output_mode and routes through remaining transforms
        completed_results, work_items = processor.handle_timeout_flush(
            node_id=agg_node_id,
            transform=agg_transform,
            ctx=ctx,
            trigger_type=TriggerType.END_OF_SOURCE,
        )

        # Handle completed results (terminal tokens - go to sink)
        for result in completed_results:
            if result.outcome == RowOutcome.FAILED:
                rows_failed += 1
            else:
                _route_aggregation_outcome(result, pending_tokens, checkpoint_callback)
                rows_succeeded += 1

        # Process work items through remaining transforms
        # These tokens need to continue through the pipeline
        for work_item in work_items:
            if work_item.current_node_id is None:
                raise RuntimeError("Aggregation continuation work item missing current_node_id")
            downstream_results = processor.process_token(
                token=work_item.token,
                transforms=config.transforms,
                ctx=ctx,
                current_node_id=work_item.current_node_id,
                coalesce_node_id=work_item.coalesce_node_id,
                coalesce_name=work_item.coalesce_name,
            )

            for result in downstream_results:
                if result.outcome == RowOutcome.FAILED:
                    rows_failed += 1
                elif result.outcome == RowOutcome.COMPLETED:
                    _route_aggregation_outcome(result, pending_tokens, checkpoint_callback)
                    rows_succeeded += 1
                elif result.outcome == RowOutcome.ROUTED:
                    rows_routed += 1
                    routed_sink = cast(str, result.sink_name)
                    routed_destinations[routed_sink] += 1
                    pending_tokens[routed_sink].append((result.token, PendingOutcome(RowOutcome.ROUTED)))
                    if checkpoint_callback is not None:
                        checkpoint_callback(result.token)
                elif result.outcome == RowOutcome.QUARANTINED:
                    rows_quarantined += 1
                elif result.outcome == RowOutcome.COALESCED:
                    sink_name = cast(str, result.sink_name)
                    rows_coalesced += 1
                    rows_succeeded += 1
                    pending_tokens[sink_name].append((result.token, PendingOutcome(RowOutcome.COMPLETED)))
                    if checkpoint_callback is not None:
                        checkpoint_callback(result.token)
                elif result.outcome == RowOutcome.FORKED:
                    rows_forked += 1
                elif result.outcome == RowOutcome.EXPANDED:
                    rows_expanded += 1
                elif result.outcome == RowOutcome.BUFFERED:
                    rows_buffered += 1
                # CONSUMED_IN_BATCH is handled within process_token

    return AggregationFlushResult(
        rows_succeeded=rows_succeeded,
        rows_failed=rows_failed,
        rows_routed=rows_routed,
        rows_quarantined=rows_quarantined,
        rows_coalesced=rows_coalesced,
        rows_forked=rows_forked,
        rows_expanded=rows_expanded,
        rows_buffered=rows_buffered,
        routed_destinations=dict(routed_destinations),
    )
