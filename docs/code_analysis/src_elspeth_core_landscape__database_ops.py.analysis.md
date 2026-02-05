# Analysis: src/elspeth/core/landscape/_database_ops.py

**Lines:** 57
**Role:** Low-level database operation helpers that reduce boilerplate in the `LandscapeRecorder`. Provides four methods: `execute_fetchone`, `execute_fetchall`, `execute_insert`, and `execute_update`. Each wraps a `connection()` context manager call and adds Tier 1 audit integrity checks for write operations (zero-row detection).
**Key dependencies:** Imports `LandscapeDB` (TYPE_CHECKING only), `sqlalchemy.Executable`, `sqlalchemy.engine.Row`. Used exclusively by `LandscapeRecorder` (27 insert/update call sites, ~42 fetch call sites).
**Analysis depth:** FULL

## Summary

This is a small, focused utility class that correctly implements the Tier 1 trust model (crash on any anomaly for audit data writes). The code is clean and the zero-rowcount checks on insert/update are a valuable safety net. The primary concern is that each method opens and commits its own transaction, which means multi-statement operations in the recorder are not atomic. This is a design trade-off rather than a bug, but it has implications for audit trail consistency during crash scenarios.

## Warnings

### [25-57] Each operation runs in its own transaction -- no multi-statement atomicity

**What:** Every method (`execute_fetchone`, `execute_fetchall`, `execute_insert`, `execute_update`) opens its own connection via `self._db.connection()`, which calls `engine.begin()`. This means each call is a separate transaction that auto-commits on exit.

**Why it matters:** In the recorder, many logical operations involve multiple database writes. For example, `begin_run()` calls `execute_insert` (one transaction), then `register_node` calls `execute_insert` again (separate transaction), then `register_edge` (another transaction). If the process crashes between transactions, the audit trail will have a partially-recorded run -- a run row with no nodes, or nodes with no edges.

For the current single-process, single-threaded execution model, this is unlikely to cause problems because each transaction is small and commits quickly. However, for a Tier 1 audit system that demands "if it's not recorded, it didn't happen," partial writes can create confusing states during crash recovery.

The alternative would be passing a connection through the call chain for multi-statement atomicity. However, this would be a significant API change and the current design is pragmatic for RC-2.

**Evidence:**
```python
def execute_insert(self, stmt: Executable) -> None:
    with self._db.connection() as conn:  # Opens new transaction
        result = conn.execute(stmt)
        # Transaction commits on exit
```

The recorder's `begin_run` method:
```python
self._ops.execute_insert(
    runs_table.insert().values(...)  # Transaction 1: commits
)
# If crash here, run exists but has no nodes
```

### [44-46] `rowcount` check may not be reliable for all statement types

**What:** `execute_insert` checks `result.rowcount == 0` after executing the insert. SQLAlchemy's `CursorResult.rowcount` is documented as returning the number of rows matched/affected for UPDATE/DELETE and INSERT statements.

**Why it matters:** For standard INSERT statements against SQLite and PostgreSQL, `rowcount` is reliable and will be 1 for single-row inserts. However:
- For `INSERT ... ON CONFLICT DO NOTHING` (upsert patterns), `rowcount` would be 0 if the row already existed, which would incorrectly trigger the `ValueError`.
- For `INSERT ... SELECT` statements, `rowcount` reflects the number of rows inserted from the SELECT.

Currently, the recorder only uses plain `INSERT` statements (no upserts, no INSERT-SELECT), so this is not an active bug. But if anyone adds an upsert pattern through this helper, they will get a false positive error.

**Evidence:**
```python
if result.rowcount == 0:
    raise ValueError("execute_insert: zero rows affected - audit write failed")
```

### [48-57] `execute_update` zero-row check is correct but error message could be misleading

**What:** `execute_update` raises `ValueError` with message "target row does not exist (audit data corruption)" when `rowcount == 0`.

**Why it matters:** A zero-rowcount update could also happen if the WHERE clause is correct but the SET values are identical to the existing values. In some database configurations (particularly PostgreSQL with `UPDATE ... SET col = same_value`), `rowcount` may still report 1 (rows matched), so this is not an issue in practice. For SQLite, `rowcount` reports rows changed, but SQLAlchemy normalizes this. The bigger point is: zero-row updates are not always "corruption" -- they could be race conditions where another process already updated the row. The error message's certainty about "corruption" could mislead investigators.

## Observations

### [15-23] Clean single-responsibility design

The class has a single constructor parameter (`db: LandscapeDB`) and provides four methods that map directly to the four database operation patterns. This is a good example of the Helper pattern -- it reduces boilerplate without adding abstraction layers.

### [6-12] TYPE_CHECKING guard for LandscapeDB import

The `LandscapeDB` import is behind `TYPE_CHECKING` to avoid circular imports (`database.py` -> `schema.py` <- `recorder.py` -> `_database_ops.py` -> `database.py`). This is correctly done.

### [37-46] Tier 1 crash-on-anomaly for inserts is well-aligned with Data Manifesto

The `execute_insert` zero-row check directly implements the Data Manifesto's Tier 1 rule: "Bad data in the audit trail = crash immediately." If an insert fails to affect any rows (e.g., constraint violation that was silently eaten by the driver), the system raises rather than continuing with a missing audit record. This is good.

### No retry logic

The helpers do not implement any retry logic for transient database errors (e.g., `SQLITE_BUSY`, connection timeouts). This is consistent with the Tier 1 approach (crash on anomaly), but see the `database.py` analysis regarding the missing `busy_timeout` PRAGMA -- without it, `SQLITE_BUSY` errors become more likely and would propagate as unhandled exceptions here.

## Verdict

**Status:** SOUND
**Recommended action:** No immediate changes required. The per-operation transaction granularity is a known design trade-off that is acceptable for RC-2. Consider documenting the non-atomicity in a comment so future developers understand that multi-step recorder operations are not transactional. If upsert patterns are ever added, the `execute_insert` rowcount check will need to be conditional.
**Confidence:** HIGH -- The file is only 57 lines and every code path is straightforward. The transaction granularity concern is a design observation, not a bug.
