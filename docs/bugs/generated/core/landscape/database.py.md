## Summary

`LandscapeDB.from_url(..., create_tables=False)` silently skips the "must already be a Landscape database" guard for non-SQLite backends, so MCP/CLI inspection against a wrong PostgreSQL database succeeds at connect time and only blows up later with raw table-not-found errors.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth/src/elspeth/core/landscape/database.py
- Line(s): 313-325, 352-361, 491-556
- Function/Method: `_validate_schema`, `from_url`

## Evidence

`from_url()` sets `require_existing_schema=not create_tables` specifically for inspection/read-only callers:

```python
# src/elspeth/core/landscape/database.py:541-547
instance = cls._from_parts(
    url,
    engine,
    passphrase=passphrase,
    journal=journal,
    require_existing_schema=not create_tables,
)
```

The validation logic even documents the intended fail-fast behavior for `create_tables=False` callers:

```python
# src/elspeth/core/landscape/database.py:352-355
# If _require_existing_schema is set (create_tables=False callers like MCP/CLI),
# we require at least some Landscape tables to be present. An empty/non-Landscape
# DB with create_tables=False would fail later with raw SQL errors — fail fast instead.
```

But `_validate_schema()` returns immediately for every non-SQLite URL:

```python
# src/elspeth/core/landscape/database.py:324-325
if not self.connection_string.startswith("sqlite"):
    return
```

So the fail-fast guard at lines 355-361 is unreachable for PostgreSQL.

That matters because the analyzer opens databases in this exact mode:

```python
# src/elspeth/mcp/analyzer.py:62
self._db = LandscapeDB.from_url(database_url, passphrase=passphrase, create_tables=False)
```

and then immediately issues direct `runs` queries:

```python
# src/elspeth/mcp/analyzers/queries.py:51-63
with db.connection() as conn:
    query = select(runs_table)...
    rows = conn.execute(query).fetchall()
```

For a non-Landscape PostgreSQL database, initialization succeeds even though the schema is wrong, and the first query later fails with a raw backend error instead of the intended `SchemaCompatibilityError`.

## Root Cause Hypothesis

Schema validation was implemented as "SQLite-only" to catch stale local audit DBs, but `from_url(create_tables=False)` later added a broader contract: inspection callers should fail fast if the target is not an ELSPETH audit database. The early non-SQLite return was never updated to enforce that contract for PostgreSQL.

## Suggested Fix

Keep the SQLite-specific epoch/column compatibility checks, but add a backend-agnostic existence check when `_require_existing_schema` is true.

For example:
- inspect all backends for table names
- if `create_tables=False` and none of `metadata.tables.keys()` exist, raise `SchemaCompatibilityError`
- keep the detailed SQLite-only column/FK/epoch checks behind the SQLite branch

## Impact

Read-only tools against PostgreSQL can connect to the wrong database and fail later with opaque SQL errors instead of a clear compatibility error. That weakens operator diagnostics and violates the file’s own fail-fast contract for audit-database inspection.
---
## Summary

SQLite schema compatibility checks ignore required check constraints and unique indexes, so an outdated audit DB can pass validation even when critical `calls` integrity constraints are missing.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth/src/elspeth/core/landscape/database.py
- Line(s): 374-426
- Function/Method: `_validate_schema`

## Evidence

The validator only checks:
- missing tables
- `_REQUIRED_COLUMNS`
- `_REQUIRED_FOREIGN_KEYS`

```python
# src/elspeth/core/landscape/database.py:374-402
missing_columns: list[tuple[str, str]] = []
...
missing_fks: list[tuple[str, str, str]] = []
...
```

There is no validation for required check constraints or indexes.

But the schema defines audit-critical invariants on `calls` entirely via a check constraint and partial unique indexes:

```python
# src/elspeth/core/landscape/schema.py:278-306
CheckConstraint(
    "(state_id IS NOT NULL AND operation_id IS NULL) OR (state_id IS NULL AND operation_id IS NOT NULL)",
    name="calls_has_parent",
)

Index(
    "ix_calls_state_call_index_unique",
    calls_table.c.state_id,
    calls_table.c.call_index,
    unique=True,
    sqlite_where=(calls_table.c.state_id.isnot(None)),
)

Index(
    "ix_calls_operation_call_index_unique",
    calls_table.c.operation_id,
    calls_table.c.call_index,
    unique=True,
    sqlite_where=(calls_table.c.operation_id.isnot(None)),
)
```

Those constraints are not optional defense-in-depth. The tests describe them as required for audit integrity:

```python
# tests/integration/audit/test_recorder_calls.py:230-235
The schema has a partial unique index: UNIQUE(state_id, call_index) WHERE state_id IS NOT NULL.
This enforces call ordering uniqueness for audit integrity - call_index must be
unambiguous for replay/verification.
```

Because `_validate_schema()` does not inspect indexes or check constraints, a stale SQLite DB missing these invariants still passes startup validation as long as the columns/FKs exist.

## Root Cause Hypothesis

The compatibility guard was built incrementally around additive columns and a few foreign keys, but it never expanded to cover newer integrity rules expressed as indexes/check constraints. That leaves the validator blind to some of the most important schema-level audit guarantees.

## Suggested Fix

Extend `_validate_schema()` with required-index and required-check-constraint validation, at least for SQLite. In particular, verify:
- `calls_has_parent`
- `ix_calls_state_call_index_unique`
- `ix_calls_operation_call_index_unique`

A small `_REQUIRED_INDEXES` / `_REQUIRED_CHECK_CONSTRAINTS` manifest alongside `_REQUIRED_COLUMNS` would fit the existing pattern.

## Impact

An outdated SQLite audit DB can admit malformed or ambiguous `calls` rows:
- both `state_id` and `operation_id` set, or neither set
- duplicate `call_index` values under the same parent

That breaks call lineage and replayability in the audit trail while the database still appears "compatible" at startup.
