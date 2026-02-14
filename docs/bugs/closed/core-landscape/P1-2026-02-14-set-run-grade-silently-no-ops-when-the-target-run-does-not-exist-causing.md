## Summary

`set_run_grade()` silently no-ops when the target run does not exist, causing undetected grade write loss.

**CLOSED -- Dead code.** set_run_grade() is exported but never called from production code. Production uses finalize_run() -> complete_run() which correctly validates with execute_update().

## Severity

- Severity: major
- Priority: CLOSED (dead code — function never called from production)

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/core/landscape/reproducibility.py`
- Line(s): 106, 107
- Function/Method: `set_run_grade`

## Evidence

`set_run_grade()` executes an `UPDATE` but does not validate affected row count:

```python
with db.connection() as conn:
    conn.execute(
        runs_table.update()
        .where(runs_table.c.run_id == run_id)
        .values(reproducibility_grade=grade.value)
    )
```

Runtime reproduction confirms silent success on missing row:
- `set_run_grade missing-run: completed without exception`

Integration inconsistency: the project's standard DB helper treats zero-row updates as integrity failures (`src/elspeth/core/landscape/_database_ops.py:48`, `src/elspeth/core/landscape/_database_ops.py:56`), but this function bypasses that enforcement.

## Root Cause Hypothesis

This function uses raw `conn.execute()` without rowcount validation, unlike the rest of recorder update paths that enforce Tier-1 integrity on missing targets.

## Suggested Fix

After `conn.execute(...)`, check `result.rowcount` and raise if it is `0`, or route through `DatabaseOps.execute_update(...)` semantics so missing runs cannot be silently ignored.

## Impact

Grade updates can be silently dropped, leaving runs with stale/NULL reproducibility grades and weakening audit reliability (no explicit failure signal for lost write).
