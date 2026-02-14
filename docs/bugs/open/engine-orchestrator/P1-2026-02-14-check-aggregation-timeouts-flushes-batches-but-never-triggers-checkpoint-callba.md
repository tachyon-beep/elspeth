## Summary

`check_aggregation_timeouts()` flushes batches but never triggers checkpoint callbacks, so aggregation-boundary checkpoints are skipped for timeout/condition flushes.

## Severity

- Severity: major
- Priority: P2 (downgraded from P1 — crash window is narrow; next processed row creates a checkpoint covering the flushed work; tokens are in pending_tokens not yet written to sinks; re-processing on recovery is acceptable)

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/engine/orchestrator/aggregation.py`
- Line(s): 144-150, 237-242, 257-285
- Function/Method: `check_aggregation_timeouts`

## Evidence

`flush_remaining_aggregation_buffers()` supports checkpoint callbacks and invokes them for sink-bound outcomes:

- `/home/john/elspeth-rapid/src/elspeth/engine/orchestrator/aggregation.py:311` (has `checkpoint_callback` param)
- `/home/john/elspeth-rapid/src/elspeth/engine/orchestrator/aggregation.py:376`
- `/home/john/elspeth-rapid/src/elspeth/engine/orchestrator/aggregation.py:396`
- `/home/john/elspeth-rapid/src/elspeth/engine/orchestrator/aggregation.py:408-409`
- `/home/john/elspeth-rapid/src/elspeth/engine/orchestrator/aggregation.py:422-423`

But `check_aggregation_timeouts()` has no callback parameter and never checkpoints when it routes flushed tokens:

```python
# aggregation.py
def check_aggregation_timeouts(...):
    ...
    for result in completed_results:
        if result.outcome == RowOutcome.FAILED:
            rows_failed += 1
        else:
            _route_aggregation_outcome(result, pending_tokens)  # no checkpoint callback
            rows_succeeded += 1
```

And downstream routed/coalesced branches also append to `pending_tokens` without checkpoint callback (`aggregation.py:263-285`).

This contradicts checkpoint intent:

- `/home/john/elspeth-rapid/src/elspeth/core/config.py:1079-1088` (`aggregation_only`, `aggregation_boundaries: bool = True`)
- `/home/john/elspeth-rapid/src/elspeth/contracts/config/protocols.py:160-162` ("checkpoint at aggregation flush boundaries")

Call sites confirm timeout path has no callback:

- `/home/john/elspeth-rapid/src/elspeth/engine/orchestrator/core.py:1560-1566`
- `/home/john/elspeth-rapid/src/elspeth/engine/orchestrator/core.py:2202-2208`

## Root Cause Hypothesis

During refactor/extraction, checkpoint callback support was added to end-of-source flushing (`flush_remaining_aggregation_buffers`) but not to pre-row timeout/condition flushing (`check_aggregation_timeouts`), creating asymmetric behavior for the same aggregation-flush boundary concept.

## Suggested Fix

Add optional `checkpoint_callback` support to `check_aggregation_timeouts()` and invoke it for successful sink-bound outcomes (COMPLETED/ROUTED/COALESCED), mirroring `flush_remaining_aggregation_buffers()` behavior. Update `core.py` call sites to pass the callback when checkpointing at aggregation boundaries is enabled.

## Impact

Checkpoint coverage is incomplete during active processing. Timeout/condition-based aggregation flushes are not checkpointed, so crash recovery can lose intended aggregation-boundary progress (or have no resumable checkpoint in long-running streams), violating configured checkpoint semantics.
