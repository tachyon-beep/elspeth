# Bug Report: Schema validation accepts non-composite FK to nodes for error tables

## Summary

- SQLite schema validation treats any FK on `node_id` as valid, so an outdated DB with `validation_errors.node_id → nodes.node_id` (missing `run_id`) passes validation even though the current schema requires a composite FK `(node_id, run_id)`.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-01-30
- Related run/issue ID: N/A

## Environment

- Commit/branch: de0ca01d55d988eca8b20f7aec17af733f8ad8b5 (branch fix/P2-aggregation-metadata-hardcoded)
- OS: Unknown
- Python version: Unknown
- Config profile / env vars: N/A
- Data set or fixture: SQLite audit DB created with legacy error-table FK on `node_id` only (no `run_id` in FK)

## Agent Context (if relevant)

- Goal or task prompt: Static analysis bug audit of `src/elspeth/core/landscape/database.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Create a SQLite DB where `nodes` has `(node_id, run_id)` columns but `validation_errors` (and/or `transform_errors`) has a FK constraint only on `node_id` referencing `nodes(node_id)` (legacy single-column FK).
2. Instantiate `LandscapeDB` against this DB.
3. Observe that `_validate_schema()` does not raise `SchemaCompatibilityError`.

## Expected Behavior

- `_validate_schema()` should reject legacy single-column FKs and require the composite FK `(node_id, run_id)` for error tables that reference `nodes`.

## Actual Behavior

- `_validate_schema()` considers any FK involving `node_id` pointing at `nodes` sufficient, so legacy single-column FKs pass validation.

## Evidence

- `_REQUIRED_FOREIGN_KEYS` only specifies a single column, and validation checks only that the column appears in a FK to `nodes`. `src/elspeth/core/landscape/database.py:36` and `src/elspeth/core/landscape/database.py:132`.
- The schema requires composite FKs for `validation_errors` and `transform_errors`. `src/elspeth/core/landscape/schema.py:329` and `src/elspeth/core/landscape/schema.py:354`.

## Impact

- User-facing impact: Developers can unknowingly run against outdated SQLite audit DBs that violate current schema constraints, leading to confusing cross-run behavior or later integrity errors.
- Data integrity / security impact: Audit integrity is weakened because rows can reference `nodes` without the required `run_id` scoping, contradicting the composite-key invariant.
- Performance or cost impact: Potentially extra debugging time; no direct performance cost.

## Root Cause Hypothesis

- `_validate_schema()` validates foreign keys by column name only and does not verify required composite FK column sets, allowing legacy single-column FKs to be treated as valid.

## Proposed Fix

- Code changes (modules/files):
  - Update `_REQUIRED_FOREIGN_KEYS` to include required constrained column sets (e.g., `("validation_errors", ("node_id", "run_id"), "nodes", ("node_id", "run_id"))`) and enforce exact match in `_validate_schema()`. `src/elspeth/core/landscape/database.py`.
- Config or schema changes: None.
- Tests to add/update:
  - Add a test that creates a DB with `validation_errors` (or `transform_errors`) FK on `node_id` only while `run_id` exists, and assert `SchemaCompatibilityError`. `tests/core/landscape/test_database.py`.
- Risks or migration steps:
  - Old SQLite audit DBs with legacy FKs will now fail fast on open (intended), requiring deletion or migration.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:389`
- Observed divergence: Validation does not enforce the composite key requirement implied by the nodes table composite PK and composite FKs in the schema.
- Reason (if known): FK validation only checks for a matching referenced table with a single constrained column.
- Alignment plan or decision needed: Enforce composite FK validation for all tables referencing `nodes` where `run_id` is part of the schema contract.

## Acceptance Criteria

- `_validate_schema()` raises `SchemaCompatibilityError` when `validation_errors` or `transform_errors` has a single-column FK on `node_id` without `run_id`.
- New/updated tests cover the composite FK requirement and pass on current schema.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/core/landscape/test_database.py -k foreign_key`
- New tests required: yes, add a test for missing composite FK columns.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md`
