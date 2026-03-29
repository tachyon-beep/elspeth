## Summary

No concrete bug found in /home/john/elspeth/src/elspeth/core/landscape/_database_ops.py

## Severity

- Severity: trivial
- Priority: P3

## Location

- File: /home/john/elspeth/src/elspeth/core/landscape/_database_ops.py
- Line(s): 27-71
- Function/Method: `execute_fetchone`, `execute_fetchall`, `execute_insert`, `execute_update`

## Evidence

`DatabaseOps` is a very small helper layer:

```python
def execute_insert(self, stmt: Executable, *, context: str = "") -> None:
    with self._db.connection() as conn:
        result = conn.execute(stmt)
        if result.rowcount == 0:
            raise AuditIntegrityError(...)
```

```python
def execute_update(self, stmt: Executable, *, context: str = "") -> None:
    with self._db.connection() as conn:
        result = conn.execute(stmt)
        if result.rowcount == 0:
            raise AuditIntegrityError(...)
```

Relevant checks:

- The transaction wrapper is the project-standard `LandscapeDB.connection()` context manager, which uses `engine.begin()` for commit/rollback semantics: [database.py](/home/john/elspeth/src/elspeth/core/landscape/database.py#L569).
- The helper’s Tier-1 zero-row guard is explicitly exercised in [test_database_ops.py](/home/john/elspeth/tests/unit/core/landscape/test_database_ops.py#L90), including:
  - duplicate `INSERT OR IGNORE` returning `rowcount=0`: [test_database_ops.py](/home/john/elspeth/tests/unit/core/landscape/test_database_ops.py#L100)
  - update against a nonexistent row returning `rowcount=0`: [test_database_ops.py](/home/john/elspeth/tests/unit/core/landscape/test_database_ops.py#L146)
- Callers that depend on this behavior are using it in the intended way for audit writes, for example:
  - run creation/completion: [run_lifecycle_repository.py](/home/john/elspeth/src/elspeth/core/landscape/run_lifecycle_repository.py#L109), [run_lifecycle_repository.py](/home/john/elspeth/src/elspeth/core/landscape/run_lifecycle_repository.py#L165)
  - row/token/outcome writes: [data_flow_repository.py](/home/john/elspeth/src/elspeth/core/landscape/data_flow_repository.py#L351), [data_flow_repository.py](/home/john/elspeth/src/elspeth/core/landscape/data_flow_repository.py#L409), [data_flow_repository.py](/home/john/elspeth/src/elspeth/core/landscape/data_flow_repository.py#L812)
  - node state / call / operation writes: [execution_repository.py](/home/john/elspeth/src/elspeth/core/landscape/execution_repository.py#L182), [execution_repository.py](/home/john/elspeth/src/elspeth/core/landscape/execution_repository.py#L622), [execution_repository.py](/home/john/elspeth/src/elspeth/core/landscape/execution_repository.py#L688), [execution_repository.py](/home/john/elspeth/src/elspeth/core/landscape/execution_repository.py#L840)

I also verified the SQLite behavior directly in a small SQLAlchemy repro: normal inserts and updates report `rowcount=1`, while duplicate `INSERT OR IGNORE` reports `rowcount=0`, matching the helper’s tests and intended enforcement.

## Root Cause Hypothesis

No bug identified.

## Suggested Fix

No fix recommended.

## Impact

No concrete breakage identified in this file. The helper appears consistent with the project’s Tier-1 audit-write policy and with its current callers and tests.
