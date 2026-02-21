## Summary

`AggregationExecutor.execute_flush()` can leave batches and node states non-terminal when post-transform audit/hash steps fail, violating audit trail completeness and leaving stale buffered state.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `src/elspeth/engine/executors/aggregation.py`
- Line(s): 315-327, 424-442, 461-514
- Function/Method: `AggregationExecutor.execute_flush`

## Evidence

`execute_flush()` only wraps `transform.process(...)` in `try/except` (`aggregation.py:360-423`).
Failures after that block are not covered:

- Batch is moved to `EXECUTING` before hash/state finalization (`aggregation.py:315-319`).
- Output hash canonicalization can raise `PluginContractViolation` (`aggregation.py:429-441`).
- Terminal recording/reset (`complete_node_state`, `complete_batch`, buffer reset) happens later (`aggregation.py:461-514`) and is skipped if an exception is raised at 429-441.

I verified this with a runtime probe using a batch transform returning `NaN` output (non-canonical). Observed output:

- exception: `PluginContractViolation`
- `complete_node_state_calls = 0`
- `complete_batch_calls = 0`
- `batch_id_after = b1`
- `buffer_count_after = 1`

So the batch remains in-progress in executor state and no terminal node/batch state is recorded for that flush attempt.

Related test coverage currently checks `transform.process` exception path (`tests/unit/engine/test_executors.py:1255-1273`) but not post-process hash/finalization failures.

## Root Cause Hypothesis

Error-handling scope is too narrow: only transform execution is guarded.
Any exception in later audit-finalization steps (input/output canonical hash, output serialization, or node completion) bypasses failure transition logic, even though batch status was already advanced to `EXECUTING`.

## Suggested Fix

Make flush finalization exception-safe for all non-pending failures after entering flush:

1. Extend guarded region to include:
- input/output hash computation
- result-to-output_data conversion
- `complete_node_state(...)`
- `complete_batch(...)`

2. On any non-`BatchPendingError` exception after flush starts:
- record `NodeStateStatus.FAILED` if state exists and is still open
- mark batch `BatchStatus.FAILED`
- clear/reset executor in-memory batch state (`_batch_ids`, `_member_counts`, `_buffers`, `_buffer_tokens`, trigger evaluator)
- clear `ctx.batch_token_ids`
- re-raise

3. Add regression tests for:
- non-canonical output in aggregation success path
- exception during post-process finalization still produces terminal batch/node states

## Impact

- Audit trail invariant break: flush attempts can leave no terminal `node_states`/`batches` transition.
- Recovery ambiguity: batch may remain effectively "in progress" in memory/state after failure.
- Potential downstream inconsistency in resume/debug flows because buffered rows remain with no clean failed terminalization for that flush operation.
