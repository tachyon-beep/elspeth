# Analysis: src/elspeth/engine/orchestrator/aggregation.py

**Lines:** 433
**Role:** Aggregation orchestration -- manages the lifecycle of aggregation nodes including timeout checking, end-of-source buffer flushing, incomplete batch recovery, and routing of flushed tokens through the remainder of the pipeline.
**Key dependencies:** Imports from `contracts` (PendingOutcome, RowOutcome, TokenInfo, TriggerType, NodeID), `orchestrator.types` (AggregationFlushResult, PipelineConfig). Called by `orchestrator.core` (Orchestrator). Delegates to `RowProcessor` public facade methods (check_aggregation_timeout, get_aggregation_buffer_count, handle_timeout_flush, process_token).
**Analysis depth:** FULL

## Summary

This module is structurally sound and follows the project's conventions well. The two main functions (`check_aggregation_timeouts` and `flush_remaining_aggregation_buffers`) are near-identical in their downstream result handling, which is a significant duplication concern. There is one genuine data integrity risk around sink routing for `ROUTED` outcomes in the `completed_results` path (lines 193-202), and a subtle inconsistency between the two main functions regarding checkpoint callbacks. No critical security or concurrency issues.

## Warnings

### [193-202] completed_results path does not handle ROUTED or QUARANTINED outcomes

**What:** When `handle_timeout_flush` returns `completed_results`, the code handles only `FAILED` and "everything else." The "everything else" branch counts all non-FAILED results as `rows_succeeded` and routes them to the default sink. However, a completed result could theoretically have a `ROUTED` outcome (if the aggregation transform itself routes), which would be misclassified as `rows_succeeded` and routed to the wrong sink.

**Why it matters:** If a batch-aware transform returns a result that the processor classifies as `ROUTED` at the `completed_results` level, it would be counted as `rows_succeeded` (incorrect counter) and appended to `pending_tokens` under an inappropriate sink name (data routed to wrong destination). The same function's `work_items` path at lines 222-257 correctly distinguishes all outcome types, meaning the `completed_results` path is inconsistently handled.

**Evidence:**
```python
# Lines 193-202 (check_aggregation_timeouts, completed_results loop)
for result in completed_results:
    if result.outcome == RowOutcome.FAILED:
        rows_failed += 1
    else:
        # Route to appropriate sink based on branch_name if set
        sink_name = result.token.branch_name or default_sink_name
        if sink_name not in pending_tokens:
            sink_name = default_sink_name
        pending_tokens[sink_name].append((result.token, PendingOutcome(result.outcome)))
        rows_succeeded += 1
```
Compare to the `work_items` path at lines 222-257, which properly handles COMPLETED, ROUTED, QUARANTINED, COALESCED, FORKED, EXPANDED, and BUFFERED outcomes separately. The same discrepancy exists in `flush_remaining_aggregation_buffers` at lines 341-354.

Whether `completed_results` can actually contain ROUTED outcomes depends on the `handle_timeout_flush` contract in `processor.py`. If `completed_results` is strictly limited to COMPLETED and FAILED outcomes by construction, this is merely a latent risk. But the code's assumption is implicit and undocumented.

### [193-202, 341-354] PendingOutcome wraps raw result.outcome for completed_results, but QUARANTINED needs error_hash

**What:** In the `completed_results` path, `PendingOutcome(result.outcome)` is constructed without an `error_hash`. If a completed result has a QUARANTINED outcome, the downstream `SinkExecutor.write()` expects `PendingOutcome` to carry an `error_hash` for proper audit recording (per P1-2026-01-31 fix referenced in core.py line 949). The `completed_results` catch-all would produce a `PendingOutcome` with `error_hash=None` for quarantined tokens.

**Why it matters:** Loss of error_hash for quarantined tokens means the audit trail would lack the correlation between the quarantine record and the sink write, undermining traceability. This is a latent bug if `completed_results` can ever contain QUARANTINED outcomes.

**Evidence:** The `work_items` path at line 239 correctly handles QUARANTINED by just incrementing `rows_quarantined` without appending to `pending_tokens`. But the `completed_results` path would silently treat QUARANTINED as a success and route to sink.

### [103-269, 272-433] Near-complete duplication between check_aggregation_timeouts and flush_remaining_aggregation_buffers

**What:** The downstream result handling logic (lines 222-257 in `check_aggregation_timeouts` and lines 374-421 in `flush_remaining_aggregation_buffers`) is virtually identical -- the same if/elif chain covering all RowOutcome variants. The only differences are: (1) `flush_remaining_aggregation_buffers` calls `checkpoint_callback` at certain points, and (2) `flush_remaining_aggregation_buffers` does not accept an `agg_transform_lookup` parameter.

**Why it matters:** Any fix to outcome handling in one function must be replicated in the other, and history shows this is error-prone. If a new RowOutcome is added, both functions must be updated identically. The lack of `agg_transform_lookup` in `flush_remaining_aggregation_buffers` means end-of-source flushes pay an O(n) transform lookup cost per aggregation node, unlike the O(1) pre-computed lookup in `check_aggregation_timeouts`.

**Evidence:** Comparing lines 222-257 with lines 374-421 shows identical structure with the only additions being `checkpoint_callback` invocations.

### [198-201, 227-230, 346-349, 379-382] Fallback to default_sink_name when branch_name not in pending_tokens

**What:** The pattern `if sink_name not in pending_tokens: sink_name = default_sink_name` silently redirects tokens to the default sink when a branch-named sink is not in the `pending_tokens` dict. This can happen if the branch_name refers to a sink that was not pre-populated in `pending_tokens` (which is initialized from `config.sinks`).

**Why it matters:** If a branch_name refers to a non-existent sink due to a graph construction bug, the token is silently rerouted to the default sink instead of crashing. Per CLAUDE.md principles, this is a system bug being hidden by silent fallback. The validation module validates gate routes but may not cover all branch_name assignments from fork operations.

**Evidence:**
```python
sink_name = result.token.branch_name or default_sink_name
if sink_name not in pending_tokens:
    sink_name = default_sink_name  # Silent redirect
```

## Observations

### [74-100] handle_incomplete_batches recovery logic is clear and correct

The three-way handling of EXECUTING (crash recovery), FAILED (retry), and DRAFT (continue) batches is well-structured and follows documented recovery semantics. The function correctly delegates to the recorder for state transitions.

### [155-156] NodeID construction from string

`NodeID(agg_node_id_str)` assumes the string is a valid NodeID. Since `aggregation_settings` keys come from pipeline configuration (our data), this is correct per the trust model.

### [209-219] Coalesce step calculation logic

The `continuation_start` calculation correctly handles both the coalesce-at-step case and the normal "next step" case. The `+1` on `work_item.start_step` is necessary because `start_step` refers to the current aggregation step, and processing should resume from the next step.

### [0] No exception handling in the module

Neither `check_aggregation_timeouts` nor `flush_remaining_aggregation_buffers` wraps any calls in try/except. This is correct per CLAUDE.md -- these functions call system-owned code (processor facade methods), and failures should crash rather than be silently handled. However, it means a failure in one aggregation node's flush will prevent processing of subsequent aggregation nodes in the same loop iteration.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** (1) Extract the duplicated outcome-handling logic into a shared helper function to ensure consistent behavior and reduce maintenance risk. (2) Review whether `completed_results` can contain outcomes other than COMPLETED and FAILED, and either add explicit handling or document the invariant. (3) Consider whether the silent fallback to `default_sink_name` should be replaced with a crash for branch_name mismatches.
**Confidence:** HIGH -- The module is well-structured and the concerns are clearly identifiable from the code. The primary risk is the duplication leading to divergent behavior over time.
