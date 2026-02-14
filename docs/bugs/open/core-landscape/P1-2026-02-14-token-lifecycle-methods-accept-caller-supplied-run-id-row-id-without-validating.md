## Summary

Token lifecycle methods accept caller-supplied `run_id`/`row_id` without validating token ownership, allowing cross-run and cross-row lineage corruption.

## Severity

- Severity: major
- Priority: P3 (downgraded from P1 — theoretical; orchestrator guarantees ID consistency)

## Location

- File: /home/john/elspeth-rapid/src/elspeth/core/landscape/_token_recording.py
- Line(s): 184-273, 275-327, 329-429, 506-579
- Function/Method: `fork_token`, `coalesce_tokens`, `expand_token`, `record_token_outcome`

## Evidence

`record_token_outcome()` inserts `run_id` and `token_id` directly with no ownership check:

```python
# _token_recording.py
token_outcomes_table.insert().values(
    run_id=run_id,
    token_id=token_id,
    ...
)
```

`fork_token()`/`expand_token()` also trust caller-supplied `run_id` and `row_id` while linking to `parent_token_id`, with no check that they belong together:

```python
# _token_recording.py
tokens_table.insert().values(row_id=row_id, ...)
token_parents_table.insert().values(token_id=child_id, parent_token_id=parent_token_id, ...)
token_outcomes_table.insert().values(run_id=run_id, token_id=parent_token_id, ...)
```

`coalesce_tokens()` links arbitrary parent tokens to a merged token row without validating parent rows:

```python
# _token_recording.py
for parent_id in parent_token_ids:
    token_parents_table.insert().values(token_id=token_id, parent_token_id=parent_id, ...)
```

Schema does not enforce `token_outcomes.run_id == token.row.run_id` (separate FKs only): `/home/john/elspeth-rapid/src/elspeth/core/landscape/schema.py:151-153`.

I verified behavior by executing against `LandscapeDB.in_memory()`:
- A token created in `run-A` can be recorded as terminal in `run-B`; querying outcomes for its row returns empty for `run-A` and populated for `run-B`.
- `fork_token(parent from row1, row_id=row2, ...)` succeeds and creates child-parent lineage across different rows.

This contaminates run-scoped logic that depends on `token_outcomes.run_id`, e.g. recovery in `/home/john/elspeth-rapid/src/elspeth/core/checkpoint/recovery.py:342-370`.

## Root Cause Hypothesis

The methods rely on caller correctness and FK existence, but current FK structure cannot enforce cross-table invariants (token↔row↔run consistency). Required integrity checks are missing at write time in this file.

## Suggested Fix

Add explicit invariant checks in this file before inserts:
- Resolve `token_id -> row_id -> run_id` via `tokens` join `rows`.
- In `record_token_outcome`: require token's row run to match `run_id`.
- In `fork_token`/`expand_token`: require parent token row == `row_id` and parent row run == `run_id`.
- In `coalesce_tokens`: require non-empty parents and all parent tokens share `row_id` equal to provided `row_id`.
- Raise `ValueError` on mismatch before any writes.

## Impact

Audit trail can attribute outcomes to the wrong run and create cross-row lineage edges. This breaks run isolation, can mislead explain/recovery, and violates audit traceability guarantees.

## Triage

Triage: Downgraded P1→P3. Same root cause as schema-cross-run-contamination and record-transform-error-wrong-run bugs. All callers derive IDs from same processing context. Track as single schema-hardening item.
