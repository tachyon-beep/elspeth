## Summary

`accumulate_row_outcomes()` silently ignores unrecognized `result.outcome` values instead of crashing, which can drop rows from sink routing/counters without any explicit failure.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `src/elspeth/engine/orchestrator/outcomes.py`
- Line(s): `72-120`
- Function/Method: `accumulate_row_outcomes`

## Evidence

`accumulate_row_outcomes()` handles known `RowOutcome` values with an `if/elif` chain, but has no final `else`:

```python
for result in results:
    if result.outcome == RowOutcome.COMPLETED:
        ...
    elif result.outcome == RowOutcome.ROUTED:
        ...
    ...
    elif result.outcome == RowOutcome.BUFFERED:
        counters.rows_buffered += 1
```

No fallback branch means any unexpected value (for example, a regression returning a non-enum value or a newly-added enum not wired here) is silently dropped: no counter update, no pending sink write, no invariant error.

This conflicts with repository invariants in `CLAUDE.md` ("plugin/system bugs should crash, not be hidden" and "I don't know what happened is never acceptable").

## Root Cause Hypothesis

During extraction/refactor, the handler was written for current known outcomes only, but without an exhaustiveness guard for invalid/future states.

## Suggested Fix

Add a terminal `else` that raises `OrchestrationInvariantError` with token/outcome context.

Example:

```python
else:
    raise OrchestrationInvariantError(
        f"Unhandled RowOutcome {result.outcome!r} for token {result.token.token_id}"
    )
```

Also tighten typing from `Iterable[Any]` to `Iterable[RowResult]` to reduce accidental misuse.

## Impact

A row can disappear from orchestrator accounting and sink dispatch without a terminal signal in this layer, creating audit/operational inconsistencies and making failures harder to trace.

## Triage

- Status: closed (false positive)
- Reason: `RowOutcome` is a Python `StrEnum` which prevents construction of non-member values. All 9 enum members (COMPLETED, ROUTED, FORKED, FAILED, QUARANTINED, CONSUMED_IN_BATCH, COALESCED, EXPANDED, BUFFERED) are handled in the if/elif chain. An `else` clause would be dead code.
- Source report: `docs/bugs/generated/engine/orchestrator/outcomes.py.md`
