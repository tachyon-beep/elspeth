## Summary

`_find_affected_run_ids()` can fail with SQLite "too many SQL variables" on large purges, after payloads have already been deleted.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth-rapid/src/elspeth/core/retention/purge.py
- Line(s): 352-403
- Function/Method: `_find_affected_run_ids`

## Evidence

`_find_affected_run_ids()` builds 8 separate `IN (...)` predicates using the full `refs_set`:

```python
refs_set = set(refs)
...
.where(rows_table.c.source_data_ref.in_(refs_set))
...
.where(operations_table.c.input_data_ref.in_(refs_set))
...
.where(calls_table.c.request_ref.in_(refs_set))
...
```

Source: `/home/john/elspeth-rapid/src/elspeth/core/retention/purge.py:352-403`.

There is no chunking or temp-table strategy. I validated this path locally with a large list and got:
`OperationalError: (sqlite3.OperationalError) too many SQL variables`.

The codebase already documents this SQLite bind-limit risk elsewhere and chunks accordingly:
`/home/john/elspeth-rapid/src/elspeth/core/checkpoint/recovery.py:32-34`.

Coverage gap: retention property tests only generate up to 10 rows/refs:
`/home/john/elspeth-rapid/tests/property/core/test_retention_monotonicity.py:54`.

## Root Cause Hypothesis

The function assumes reference lists stay small and uses direct `IN` expansion across multiple queries, which does not scale to large purge batches on SQLite variable limits.

## Suggested Fix

Chunk `refs_set` inside `_find_affected_run_ids()` (for example 500-per-chunk, matching recovery patterns), execute per-chunk queries, and union run IDs in Python.
Alternative: write refs to a temp table and join against it.

## Impact

Large purge runs can crash during grade-update discovery after blob deletions already happened. This leaves partially applied purge side effects and stale `reproducibility_grade` values for affected runs.
