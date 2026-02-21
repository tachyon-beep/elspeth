## Summary

`get_failure_context()` applies `LIMIT` to validation errors without `ORDER BY`, producing nondeterministic samples and potentially hiding the most recent failures.

## Severity

- Severity: minor
- Priority: P2

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/mcp/analyzers/diagnostics.py`
- Line(s): 283-296
- Function/Method: `get_failure_context`

## Evidence

Validation errors query:

```python
validation_errors = conn.execute(
    select(...)
    .outerjoin(...)
    .where(validation_errors_table.c.run_id == run_id)
    .limit(limit)
).fetchall()
```

No ordering is defined before `limit(limit)`.
In the same function, transform errors are explicitly ordered by recency:

- `diagnostics.py:277-279` (`order_by(transform_errors_table.c.created_at.desc()).limit(limit)`)

Validation errors table has timestamp field available for deterministic ordering:

- `src/elspeth/core/landscape/schema.py:413` (`created_at`)

## Root Cause Hypothesis

The query was implemented with `limit` but omitted a recency/stability ordering clause.

## Suggested Fix

Add explicit ordering before `limit`, e.g. newest first:

```python
.order_by(validation_errors_table.c.created_at.desc())
.limit(limit)
```

## Impact

Failure-context output can vary between calls and miss the latest validation issues, reducing diagnostic reliability during incident triage.

## Triage

- Status: open
- Source report: `docs/bugs/generated/mcp/analyzers/diagnostics.py.md`
- Finding index in source report: 2
- Beads: pending
