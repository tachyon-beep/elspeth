# SQLite Read-Only Epoch Fix Plan

**Goal:** Preserve schema validation for existing SQLite audit databases while ensuring `create_tables=False` opens never mutate the database or fail solely because epoch stamping attempts a write.

**Why this is needed:** `LandscapeDB.from_url(..., create_tables=False)` currently validates the schema and then unconditionally calls `_sync_sqlite_schema_epoch()`. For compatible pre-epoch databases, that turns a nominally read-only inspection open into a write via `PRAGMA user_version = ...`, which conflicts with the documented forensic/read-only contract.

## Scope

- Modify [src/elspeth/core/landscape/database.py](/home/john/elspeth/src/elspeth/core/landscape/database.py) so schema-epoch stamping only runs on paths that are already allowed to create or upgrade schema state.
- Extend [tests/unit/core/landscape/test_database_compatibility_guards.py](/home/john/elspeth/tests/unit/core/landscape/test_database_compatibility_guards.py) with a regression test for `create_tables=False`.
- Re-run the compatibility guard tests to confirm we still stamp new databases and still reject incompatible epochs.

## Plan

### 1. Add the regression test first

**File:** [tests/unit/core/landscape/test_database_compatibility_guards.py](/home/john/elspeth/tests/unit/core/landscape/test_database_compatibility_guards.py)

Add a test next to the existing epoch-stamping coverage that:

- Creates a real SQLite audit DB with `metadata.create_all(engine)`.
- Leaves `PRAGMA user_version` at `0` to simulate a compatible pre-epoch database.
- Opens it via `LandscapeDB.from_url(..., create_tables=False)`.
- Verifies the open succeeds.
- Verifies `PRAGMA user_version` is still `0` afterward.

This keeps the regression check deterministic without relying on OS-specific file permission behavior.

Suggested command:

```bash
uv run pytest tests/unit/core/landscape/test_database_compatibility_guards.py -q
```

### 2. Narrow the write path in `from_url`

**File:** [src/elspeth/core/landscape/database.py](/home/john/elspeth/src/elspeth/core/landscape/database.py#L457)

Change the `from_url` flow so `_sync_sqlite_schema_epoch()` only runs when `create_tables=True`.

Recommended shape:

```python
if create_tables:
    metadata.create_all(engine)
    instance._sync_sqlite_schema_epoch()
```

That keeps the current behavior for:

- new databases created through the normal writable path
- existing writable databases opened in schema-managing mode

And it avoids mutation for:

- CLI inspection paths using `create_tables=False`
- MCP analyzer opens using `create_tables=False`

Leave `_validate_schema()` unchanged so we still:

- reject non-Landscape databases early
- reject incompatible future epochs
- accept epoch `0` as compatible for legacy read-only inspection

### 3. Clarify intent in comments/docstrings

**File:** [src/elspeth/core/landscape/database.py](/home/john/elspeth/src/elspeth/core/landscape/database.py#L281)

Update the nearby comment or `_sync_sqlite_schema_epoch()` docstring to make the contract explicit:

- schema stamping is part of schema creation/upgrade flow
- read-only/inspection opens must not stamp or otherwise mutate evidence

This reduces the chance of reintroducing the regression later.

### 4. Verify the full behavior envelope

Run:

```bash
uv run pytest tests/unit/core/landscape/test_database_compatibility_guards.py -q
```

Expected checks:

- new DBs opened with default `create_tables=True` still get `SQLITE_SCHEMA_EPOCH`
- existing compatible DBs opened with `create_tables=False` keep epoch `0`
- incompatible future epochs still raise `SchemaCompatibilityError`

Optional follow-up if we want extra CLI confidence:

```bash
uv run pytest tests/unit/cli/test_cli.py -q
```

## Risks to watch

- Do not move or weaken `_validate_schema()`. The regression is about write timing, not validation policy.
- Do not change the default constructor or `in_memory()` behavior unless tests show a broader issue; the reported bug is specific to `from_url(..., create_tables=False)`.
- If a read-only URI test is added later, watch for unrelated SQLite PRAGMA behavior from `_configure_sqlite()`. That would be a separate concern from the epoch-stamping regression.
