## Summary

`retry_batch()` is non-idempotent and can create multiple retry batches with the same `attempt` for one failed batch, causing ambiguous retry lineage.

## Severity

- Severity: major
- Priority: P2 (downgraded from P1 — narrow crash-during-recovery window, creates duplicate draft batches not silent corruption)

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/core/landscape/_batch_recording.py`
- Line(s): 310, 317, 324, 255
- Function/Method: `retry_batch`

## Evidence

`retry_batch()` always creates `attempt = original.attempt + 1` with no existence check:

- `/home/john/elspeth-rapid/src/elspeth/core/landscape/_batch_recording.py:317`
- `/home/john/elspeth-rapid/src/elspeth/core/landscape/_batch_recording.py:320`

It also leaves the original failed batch in place, and `get_incomplete_batches()` keeps returning `FAILED`:

- `/home/john/elspeth-rapid/src/elspeth/core/landscape/_batch_recording.py:255`
- `/home/john/elspeth-rapid/src/elspeth/core/landscape/_batch_recording.py:313`

Recovery calls retry for each failed batch:

- `/home/john/elspeth-rapid/src/elspeth/engine/orchestrator/aggregation.py:138`
- `/home/john/elspeth-rapid/src/elspeth/engine/orchestrator/aggregation.py:140`

Concrete reproduction (in-memory run) produced two draft batches both with `attempt == 1` from the same original failed batch.

## Root Cause Hypothesis

`retry_batch()` assumes one-time invocation per failed batch and does not enforce idempotency or uniqueness of `(run_id, aggregation_node_id, attempt)` at method level.

## Suggested Fix

In `retry_batch()`:

1. Before creating a new batch, query for an existing batch with:
   - same `run_id`
   - same `aggregation_node_id`
   - `attempt == original.attempt + 1`
2. If found, return it (idempotent) or raise a clear integrity error.
3. Copy-members operation should be wrapped in one transaction to avoid partially copied retry batches on mid-loop failure.

## Impact

- Multiple drafts can represent the same retry attempt.
- Retry lineage becomes ambiguous in audit records.
- Recovery can repeatedly fan out duplicate retry work for the same failed batch.

## Triage

Triage: Downgraded P1→P2. Requires crash specifically during recovery. Impact is redundant work (duplicate draft batches), not silent data corruption.
