## Summary

`compute_grade()` returns `FULL_REPRODUCIBLE` for a `run_id` that does not exist, producing a false reproducibility classification instead of failing.

## Severity

- Severity: major
- Priority: P2 (downgraded from P1 — no production caller passes nonexistent run_id)

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/core/landscape/reproducibility.py`
- Line(s): 62, 66, 90, 95
- Function/Method: `compute_grade`

## Evidence

`compute_grade()` only queries `nodes_table` and never verifies the run exists in `runs_table`:

```python
query_all = select(nodes_table.c.determinism).where(nodes_table.c.run_id == run_id).distinct()
...
determinism_values = [row[0] for row in result.fetchall()]
...
has_non_reproducible = any(det in non_reproducible for det in determinism_values)
if has_non_reproducible:
    return ReproducibilityGrade.REPLAY_REPRODUCIBLE
else:
    return ReproducibilityGrade.FULL_REPRODUCIBLE
```

For a missing run, `determinism_values` is empty, so it falls through to `FULL_REPRODUCIBLE`.

Runtime reproduction (in-memory DB, no runs inserted) confirms this behavior:
- `compute_grade missing-run: full_reproducible`

## Root Cause Hypothesis

The function equates "no nodes found" with "empty pipeline," but does not distinguish that from "run does not exist." This conflates two different states and hides invalid/missing run IDs.

## Suggested Fix

Add an explicit run-existence check before reading node determinism, and fail if absent.

Example approach:
1. Query `runs_table` for `run_id`.
2. If no row, raise `ValueError` (or `AuditIntegrityError`) with run ID context.
3. Keep existing "empty pipeline => FULL" logic only for existing runs with zero nodes.

## Impact

A nonexistent run can be reported as maximally reproducible, which is a false audit claim and can mask upstream run-lifecycle bugs or bad IDs in callers.

## Triage

Triage: Downgraded P1→P2. compute_grade() called by orchestrator at run completion with valid run_id. No public API path passes fabricated IDs. Fix is trivial (add run-existence check).
