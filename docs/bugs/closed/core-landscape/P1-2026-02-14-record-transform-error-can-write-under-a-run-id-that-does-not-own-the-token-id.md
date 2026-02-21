## Summary

`record_transform_error()` can write a transform error under a `run_id` that does not own the `token_id`, causing silent cross-run audit contamination.

## Severity

- Severity: major
- Priority: P3 (downgraded from P1 — theoretical; no production caller passes mismatched IDs; merge with schema-hardening item)

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/core/landscape/_error_recording.py`
- Line(s): `160-166`, `211-223`
- Function/Method: `record_transform_error`, `get_transform_errors_for_token`

## Evidence

`record_transform_error()` inserts `run_id` and `token_id` without verifying they belong together:

```python
# _error_recording.py:160-166
transform_errors_table.insert().values(
    run_id=run_id,
    token_id=token_id,
    transform_id=transform_id,
    ...
)
```

Schema allows this mismatch because `transform_errors` has separate FKs to `runs` and `tokens`, but no FK enforcing token->run consistency (`schema.py:438-450`), and `tokens` has no `run_id` column (`schema.py:131-142`).

`lineage.explain()` later fetches transform errors by token only (`lineage.py:195`), so a mismatched row is surfaced as if valid lineage for that token.

I verified this behavior in-memory: inserting `run_id='runB'` with `token_id='tokA'` (created in `runA`) succeeds, and `get_transform_errors_for_token('tokA')` returns the `runB` error.

## Root Cause Hypothesis

The method assumes caller invariants guarantee `run_id`/`token_id` consistency, but database constraints do not enforce that invariant, and this file does not validate it before insert.

## Suggested Fix

In `record_transform_error()`, validate token ownership before insert:

- Load token via `get_token(token_id)`, then row via `get_row(token.row_id)`.
- Crash fast if token missing, row missing, or `row.run_id != run_id`.
- Optionally harden `get_transform_errors_for_token()` to accept `run_id` (or internally verify consistency) to prevent leaked corrupted rows.

## Impact

Audit trail integrity is violated: transform errors can be attached to the wrong run, producing incorrect lineage/explain output and misleading incident analysis.

## Triage

Triage: Downgraded P1→P3. Same root cause as schema-cross-run-contamination and token-lifecycle bugs. All production callers maintain ID consistency through orchestrator processing context. Track as single schema-hardening item.
