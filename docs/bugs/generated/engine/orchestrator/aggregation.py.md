## Summary

`handle_incomplete_batches()` creates retry batches during resume but discards the new `batch_id`, so restored aggregation state still points at the old failed batch and the next flush crashes on an illegal terminal-to-executing transition.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `/home/john/elspeth/src/elspeth/engine/orchestrator/aggregation.py`
- Line(s): 98-105
- Function/Method: `handle_incomplete_batches`

## Evidence

`handle_incomplete_batches()` retries incomplete batches, but it ignores the `Batch` object returned by `recorder.retry_batch()`:

```python
# src/elspeth/engine/orchestrator/aggregation.py:98-105
for batch in incomplete:
    if batch.status == BatchStatus.EXECUTING:
        recorder.update_batch_status(batch.batch_id, BatchStatus.FAILED)
        recorder.retry_batch(batch.batch_id)
    elif batch.status == BatchStatus.FAILED:
        recorder.retry_batch(batch.batch_id)
```

That matters because resume restores aggregation executor state from the checkpointed `batch_id`, not from the newly created retry batch:

```python
# src/elspeth/engine/orchestrator/core.py:2589-2599
handle_incomplete_batches(recorder, run_id)
...
if resume_point.aggregation_state is not None:
    restored_state[resume_point.node_id] = resume_point.aggregation_state
```

```python
# src/elspeth/engine/executors/aggregation.py:761-765
node.tokens = reconstructed_tokens
node.buffers = [t.row_data.to_dict() for t in reconstructed_tokens]
node.batch_id = node_checkpoint.batch_id
```

On the resumed flush, the executor tries to transition that stale batch back to `EXECUTING`:

```python
# src/elspeth/engine/executors/aggregation.py:321-326
self._recorder.update_batch_status(
    batch_id=batch_id,
    status=BatchStatus.EXECUTING,
    trigger_type=trigger_type,
)
```

But `handle_incomplete_batches()` has already marked the original batch `FAILED`, and `update_batch_status()` forbids moving terminal batches back to non-terminal states:

```python
# src/elspeth/core/landscape/execution_repository.py:1146-1160
.where(batches_table.c.status.notin_(terminal_values))
...
raise AuditIntegrityError(
    f"Cannot transition batch {batch_id} from terminal status {existing.status!r} "
    f"to {status.value!r}. Terminal batches are immutable."
)
```

So the recovery sequence is internally inconsistent:

1. `aggregation.py` creates retry batch attempt N+1.
2. Restored checkpoint still rebinds executor state to old batch attempt N.
3. First resumed flush touches attempt N again and crashes.

The existing tests for `handle_incomplete_batches()` only assert that `retry_batch()` was called, not that the returned retry `batch_id` is propagated into restored runtime state; see [`tests/unit/engine/orchestrator/test_aggregation.py`](/home/john/elspeth/tests/unit/engine/orchestrator/test_aggregation.py#L179).

## Root Cause Hypothesis

The recovery helper was written as a fire-and-forget side-effect function, but resume recovery actually needs the retry batch identity. By returning `None` and discarding `retry_batch()`’s result, `handle_incomplete_batches()` loses the only authoritative mapping from old batch attempt to new retry batch attempt.

## Suggested Fix

Make `handle_incomplete_batches()` return enough information for resume reconstruction to rebind checkpoint state to the new retry batch, for example a mapping of old `batch_id -> new_batch_id` or old aggregation node -> retried `Batch`.

Then apply that remap before `restore_from_checkpoint()` uses the checkpointed batch IDs.

Sketch:

```python
def handle_incomplete_batches(...) -> dict[str, str]:
    remapped: dict[str, str] = {}
    ...
    retried = recorder.retry_batch(batch.batch_id)
    remapped[batch.batch_id] = retried.batch_id
    return remapped
```

And during resume, rewrite checkpoint batch IDs with that mapping before restoring executor state.

## Impact

Resume after an aggregation crash can fail deterministically for `EXECUTING`/`FAILED` batches. That blocks recovery of buffered rows, leaves retry batches orphaned from runtime state, and breaks the intended audit story for batch attempts because the executor continues referencing the superseded batch instead of the retry attempt.
