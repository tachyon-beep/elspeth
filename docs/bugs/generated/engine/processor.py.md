## Summary

Count-triggered transform aggregations can quarantine multiple batch members in Landscape, but `processor.py` only returns a `RowResult` for the triggering token, so earlier quarantined batch members are omitted from orchestrator counters.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth/src/elspeth/engine/processor.py
- Line(s): 726-745, 791-800
- Function/Method: `_route_transform_results`

## Evidence

`processor.py` records terminal outcomes for every buffered token:

```python
for i, token in enumerate(fctx.buffered_tokens):
    if i in quarantined_index_set:
        self._recorder.record_token_outcome(... outcome=RowOutcome.QUARANTINED ...)
    else:
        self._recorder.record_token_outcome(... outcome=RowOutcome.CONSUMED_IN_BATCH ...)
```

Source: `/home/john/elspeth/src/elspeth/engine/processor.py:728-745`

But on count-triggered flush it only returns a `RowResult` for the triggering token:

```python
if fctx.triggering_token is not None:
    triggering_index = len(fctx.buffered_tokens) - 1
    triggering_outcome = ...
    results.append(RowResult(token=fctx.triggering_token, outcome=triggering_outcome))
```

Source: `/home/john/elspeth/src/elspeth/engine/processor.py:786-800`

The orchestrator updates `rows_quarantined` from returned `RowResult`s only, and explicitly treats `CONSUMED_IN_BATCH` as a no-op:

- `/home/john/elspeth/src/elspeth/engine/orchestrator/outcomes.py:108-123`

Batch transforms are expected to quarantine multiple indices in one flush, not just the trigger row:

- `/home/john/elspeth/tests/unit/plugins/transforms/test_batch_replicate_integration.py:223-258`

Inference from these files: if a count-triggered batch flush returns `quarantined_indices=[0, 2]`, token `2` is surfaced via `RowResult`, but token `0` is only recorded in Landscape and never reaches `accumulate_row_outcomes()`. The audit DB says two rows were quarantined; the run counters only count one.

## Root Cause Hypothesis

`_route_transform_results()` mixes two responsibilities: durable terminal recording for all buffered parents and in-memory control-flow reporting for the current `process_row()` call. It records all parent outcomes, but only materializes a `RowResult` for the triggering parent, assuming other parents do not matter to counters. That assumption is false for quarantined parents.

## Suggested Fix

Return `RowResult`s for every buffered parent whose terminal state affects counters, not just the triggering token. At minimum, emit `RowResult(..., outcome=RowOutcome.QUARANTINED)` for all quarantined indices in the batch. A cleaner fix is to build parent `RowResult`s for every buffered token after outcome determination, then let `accumulate_row_outcomes()` ignore the `CONSUMED_IN_BATCH` ones and count the quarantined ones.

## Impact

`RunResult.rows_quarantined` can under-report quarantined rows for transform-mode count-triggered aggregations. That creates a mismatch between the legal record in Landscape and the execution summary used by operators, dashboards, and tests.
---
## Summary

Transform-mode aggregation records parents as `CONSUMED_IN_BATCH` or `QUARANTINED` before validating output cardinality and before creating child tokens, so a later exception can leave the audit trail claiming the batch is terminal even though no output token exists; recovery then skips the row.

## Severity

- Severity: critical
- Priority: P0

## Location

- File: /home/john/elspeth/src/elspeth/engine/processor.py
- Line(s): 726-745, 762-784
- Function/Method: `_route_transform_results`

## Evidence

`_route_transform_results()` records parent terminal outcomes first:

```python
for i, token in enumerate(fctx.buffered_tokens):
    if i in quarantined_index_set:
        self._recorder.record_token_outcome(... outcome=RowOutcome.QUARANTINED ...)
    else:
        self._recorder.record_token_outcome(... outcome=RowOutcome.CONSUMED_IN_BATCH ...)
```

Source: `/home/john/elspeth/src/elspeth/engine/processor.py:728-745`

Only after those terminal writes does it run failure-prone postconditions:

```python
if actual_count != fctx.settings.expected_output_count:
    raise RuntimeError(...)

expanded_tokens, _expand_group_id = self._token_manager.expand_token(
    ...,
    record_parent_outcome=False,
)
```

Source: `/home/john/elspeth/src/elspeth/engine/processor.py:762-784`

`TokenManager.expand_token()` can still raise before any child-token side effects if the output contract is invalid:

- `/home/john/elspeth/src/elspeth/engine/tokens.py:358-365`

There is a test asserting this exact guard:

- `/home/john/elspeth/tests/unit/engine/test_tokens.py:918-939`

Recovery treats both `QUARANTINED` and `CONSUMED_IN_BATCH` as terminal outcomes and excludes such rows from reprocessing:

- `/home/john/elspeth/src/elspeth/core/checkpoint/recovery.py:332-374`
- `/home/john/elspeth/src/elspeth/core/checkpoint/recovery.py:419-423`

What the code does: mark parents terminal, then attempt child creation.
What it should do: validate output count and create children successfully first, then mark parents terminal.

## Root Cause Hypothesis

The function tries to preserve per-parent batch outcomes, but it commits those outcomes too early. The ordering is backwards for audit integrity: parent terminal states are persisted before all downstream invariants for the batch output have been proven.

## Suggested Fix

Move parent `record_token_outcome()` calls until after:

1. `expected_output_count` validation succeeds, and
2. `expand_token()` succeeds.

If parent and child side effects must stay tightly coupled, make them a single atomic operation in the recorder/token layer. On any post-flush invariant failure, the batch should crash without leaving parent tokens in a terminal state that implies successful batch consumption.

## Impact

This can create silent data loss after a crash or invariant failure. Landscape shows the input tokens as terminal (`CONSUMED_IN_BATCH`/`QUARANTINED`), but no expanded output token exists. Because recovery treats those inputs as complete, resume logic can skip the row entirely, breaking lineage and violating the “no silent drops” audit guarantee.
