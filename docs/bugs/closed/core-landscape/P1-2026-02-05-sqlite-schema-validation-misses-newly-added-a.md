# Bug Report: SQLite schema validation misses newly added audit columns in `runs`/`nodes`

## Summary

- `_validate_schema()` only checks `_REQUIRED_COLUMNS`, which omits several columns that are now written by `LandscapeRecorder` (`runs.source_schema_json`, `runs.schema_contract_json`, `runs.schema_contract_hash`, `nodes.schema_mode`, `nodes.schema_fields_json`, `nodes.input_contract_json`, `nodes.output_contract_json`). Stale SQLite databases therefore pass validation and fail later with `OperationalError` when inserts target missing columns.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: RC2.3-pipeline-row @ 1c70074ef3b71e4fe85d4f926e52afeca50197ab
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Legacy SQLite `audit.db` created before schema contract fields (Phase 5/WP-11.99) and source schema fields were added

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `/home/john/elspeth-rapid/src/elspeth/core/landscape/database.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Use a pre-refactor SQLite `audit.db` that lacks the newer `runs` and `nodes` columns listed below.
2. Initialize `LandscapeDB` with that file and start a run (e.g., `LandscapeRecorder.begin_run()` / `register_node()`).

## Expected Behavior

- `LandscapeDB._validate_schema()` should raise `SchemaCompatibilityError` at startup indicating missing columns.

## Actual Behavior

- Initialization succeeds because `_REQUIRED_COLUMNS` does not include the new columns, and the first insert into `runs` or `nodes` fails at runtime with `sqlite3.OperationalError: table ... has no column ...`.

## Evidence

- `_REQUIRED_COLUMNS` omits the new `runs`/`nodes` audit columns and is the sole gate for SQLite validation: `src/elspeth/core/landscape/database.py:27-41`.
- `runs` table defines `source_schema_json`, `schema_contract_json`, and `schema_contract_hash`, which are newer audit fields: `src/elspeth/core/landscape/schema.py:40-58`.
- `nodes` table defines `schema_mode`, `schema_fields_json`, `input_contract_json`, and `output_contract_json` (WP-11.99 / Phase 5 audit columns): `src/elspeth/core/landscape/schema.py:77-84`.
- `LandscapeRecorder.begin_run()` always inserts `source_schema_json`, `schema_contract_json`, and `schema_contract_hash`: `src/elspeth/core/landscape/recorder.py:224-236`.
- `LandscapeRecorder.register_node()` always inserts `schema_mode`, `schema_fields_json`, `input_contract_json`, `output_contract_json`: `src/elspeth/core/landscape/recorder.py:756-773`.

## Impact

- User-facing impact: Pipelines crash mid-start on stale SQLite databases instead of failing fast with a clear compatibility error.
- Data integrity / security impact: Partial audit trail state can be written (e.g., run row created but nodes not recorded), violating the “all-or-nothing” audit traceability intent.
- Performance or cost impact: None, but causes repeated failed runs and manual cleanup for developers.

## Root Cause Hypothesis

- `_REQUIRED_COLUMNS` in `database.py` has not been updated to include newer audit fields added to `runs` and `nodes`, so `_validate_schema()` cannot detect outdated SQLite schemas before inserts execute.

## Proposed Fix

- Code changes (modules/files): Update `_REQUIRED_COLUMNS` in `src/elspeth/core/landscape/database.py` to include `runs.source_schema_json`, `runs.schema_contract_json`, `runs.schema_contract_hash`, `nodes.schema_mode`, `nodes.schema_fields_json`, `nodes.input_contract_json`, and `nodes.output_contract_json`.
- Config or schema changes: None.
- Tests to add/update: Add a SQLite schema-compat test that creates a minimal pre-change `audit.db` (missing these columns) and asserts `LandscapeDB(...)._validate_schema()` raises `SchemaCompatibilityError`.
- Risks or migration steps: None beyond existing guidance to delete/recreate stale SQLite databases.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): Unknown.
- Observed divergence: Schema compatibility checks do not cover newer audit columns, allowing incompatible DBs to proceed.
- Reason (if known): Likely `_REQUIRED_COLUMNS` list not maintained after Phase 5/WP-11.99 changes.
- Alignment plan or decision needed: Extend `_REQUIRED_COLUMNS` to reflect current audit schema.

## Acceptance Criteria

- Stale SQLite databases missing any of the listed `runs`/`nodes` audit columns fail fast with `SchemaCompatibilityError` before any inserts are attempted.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/ -k "schema_compat"`
- New tests required: yes, add a compatibility test for missing `runs`/`nodes` audit columns

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md` (Auditability Standard, Phase 5 audit schema references)
