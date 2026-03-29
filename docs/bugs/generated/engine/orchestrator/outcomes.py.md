## Summary

Coalesce timeout/end-of-source failures are recorded as `FAILED` token outcomes in the audit trail, but `outcomes.py` only increments `rows_coalesce_failed` and never increments `rows_failed`, so run statistics can underreport failed rows.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `/home/john/elspeth/src/elspeth/engine/orchestrator/outcomes.py`
- Line(s): 233-246, 276-295
- Function/Method: `handle_coalesce_timeouts`, `flush_coalesce_pending`

## Evidence

`outcomes.py` treats a failed coalesce event as a single counter increment:

```python
for outcome in timed_out:
    if _validate_coalesce_outcome(outcome):
        ...
    else:
        counters.rows_coalesce_failed += 1
```

and similarly in `flush_coalesce_pending()` at [outcomes.py](/home/john/elspeth/src/elspeth/engine/orchestrator/outcomes.py#L276).

But the coalesce executor records a `FAILED` terminal outcome for every affected token, not just “one coalesce failed”:

```python
for _branch_name, entry in pending.branches.items():
    self._recorder.complete_node_state(... status=NodeStateStatus.FAILED ...)
    self._recorder.record_token_outcome(
        run_id=self._run_id,
        token_id=entry.token.token_id,
        outcome=RowOutcome.FAILED,
        error_hash=error_hash,
    )
```

See [coalesce_executor.py](/home/john/elspeth/src/elspeth/engine/coalesce_executor.py#L530) and [coalesce_executor.py](/home/john/elspeth/src/elspeth/engine/coalesce_executor.py#L537). Late-arrival failures do the same at [coalesce_executor.py](/home/john/elspeth/src/elspeth/engine/coalesce_executor.py#L392).

The rest of the orchestrator reports `rows_failed` as the row-failure count in user-visible progress/run results, with no adjustment for coalesce failures:
- [core.py](/home/john/elspeth/src/elspeth/engine/orchestrator/core.py#L2013)
- [types.py](/home/john/elspeth/src/elspeth/engine/orchestrator/types.py#L211)
- [run_result.py](/home/john/elspeth/src/elspeth/contracts/run_result.py#L24)

There is also evidence of intended semantics elsewhere: when a coalesce fails because a branch is lost during normal processing, the processor explicitly converts each consumed token into a `RowResult(..., outcome=FAILED)` “for counter accounting” at [processor.py](/home/john/elspeth/src/elspeth/engine/processor.py#L1459). `outcomes.py`’s timeout/flush path skips that accounting.

The existing unit tests encode the buggy behavior by asserting only `rows_coalesce_failed`:
- [test_outcomes.py](/home/john/elspeth/tests/unit/engine/orchestrator/test_outcomes.py#L695)
- [test_outcomes.py](/home/john/elspeth/tests/unit/engine/orchestrator/test_outcomes.py#L811)

## Root Cause Hypothesis

The extraction into `outcomes.py` modeled coalesce timeout/flush failures as event-level accounting (“one coalesce failed”) instead of token-level accounting (“N tokens failed”). That diverged from both the audit trail, which records `FAILED` per token, and the branch-loss code path, which emits per-token `FAILED` `RowResult`s for the same purpose.

## Suggested Fix

When `_validate_coalesce_outcome(outcome)` returns `False`, increment both:
- `counters.rows_coalesce_failed` by 1
- `counters.rows_failed` by `len(outcome.consumed_tokens)`

That keeps `rows_coalesce_failed` as the coalesce-event counter while aligning `rows_failed` with the per-token `FAILED` outcomes already persisted by `CoalesceExecutor`.

Add tests covering timeout and flush failures with multiple `consumed_tokens`, asserting both counters.

## Impact

Run summaries, progress events, graceful-shutdown error stats, and any UI/API consumers of `RunResult.rows_failed` can say zero failed rows even when the audit trail contains failed tokens from coalesce timeout/flush paths. That creates a direct audit/statistics contradiction and can hide real row loss from operators.
