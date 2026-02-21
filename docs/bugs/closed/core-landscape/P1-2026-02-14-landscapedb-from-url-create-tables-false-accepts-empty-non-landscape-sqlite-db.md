## Summary

`LandscapeDB.from_url(..., create_tables=False)` accepts an empty/non-Landscape SQLite database and only fails later on first query, instead of failing fast during schema validation.

## Severity

- Severity: major
- Priority: P2 (downgraded from P1 — only affects read-only analysis paths; worse error messages, not data corruption)

## Location

- File: `src/elspeth/core/landscape/database.py`
- Line(s): 294-295, 300-316, 447-453
- Function/Method: `_validate_schema`, `from_url`

## Evidence

`_validate_schema()` only reports missing tables if **some** Landscape tables already exist:

```python
# src/elspeth/core/landscape/database.py:294-295
missing_tables = sorted(expected_tables - existing_tables) if present_landscape_tables else []
```

When `existing_tables` has no Landscape tables (empty DB / wrong DB), `missing_tables` becomes `[]`.
Then required-column/FK checks also skip because tables are absent:

```python
# src/elspeth/core/landscape/database.py:300-316
if table_name not in existing_tables:
    continue
```

`from_url()` always calls `_validate_schema()`, then returns directly when `create_tables=False`:

```python
# src/elspeth/core/landscape/database.py:449-453
instance._validate_schema()
if create_tables:
    metadata.create_all(engine)
return instance
```

So `create_tables=False` allows a non-Landscape DB through validation.

Integration evidence:
- `src/elspeth/mcp/analyzer.py:63` uses `create_tables=False`
- `src/elspeth/cli.py:682` uses `create_tables=False`

Repro (executed locally):
- `LandscapeDB.from_url("sqlite:///:memory:", create_tables=False)` succeeds
- First read (`LandscapeRecorder.list_runs()`) fails with `OperationalError: no such table: runs`

## Root Cause Hypothesis

Schema validation is designed to distinguish "brand-new DB to initialize" from "existing partial Landscape DB," but it does not account for callers explicitly requesting **no table creation** (`create_tables=False`). That path should enforce "existing Landscape schema required," but current logic treats empty/non-Landscape DBs as acceptable.

## Suggested Fix

In `database.py`, make schema validation mode-aware for `create_tables=False`:

- Add a strict flag to `_validate_schema` (for example, `require_existing_landscape: bool = False`).
- In `from_url`, call `_validate_schema(require_existing_landscape=not create_tables)`.
- In strict mode, if no expected Landscape tables are present, raise `SchemaCompatibilityError` immediately with actionable guidance.
- Keep current permissive behavior only when `create_tables=True`.

## Impact

- MCP/CLI analysis paths (`create_tables=False`) can connect to wrong/empty DBs and fail later with raw SQL errors.
- Error context is delayed and less actionable (`no such table`) instead of an immediate schema compatibility failure.
- On writable systems, typoed SQLite paths may produce empty DB files and mislead operators before failure.

## Triage

Triage: Downgraded P1→P2. Only callers with create_tables=False are MCP analyzer and CLI (read-only). User gets error either way — just a less actionable one. Not a data integrity issue.
