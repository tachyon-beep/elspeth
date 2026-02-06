# Bug Report: DatabaseOps write helpers ignore affected row count, allowing silent audit-table no-ops

## Summary

- `execute_update` (and `execute_insert`) do not verify affected row count, so Tier‑1 audit updates can silently no-op and mask incorrect IDs or missing rows.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: 1c70074ef3b71e4fe85d4f926e52afeca50197ab (branch RC2.3-pipeline-row)
- OS: Unknown
- Python version: Unknown
- Config profile / env vars: N/A
- Data set or fixture: In-memory LandscapeDB

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `/home/john/elspeth-rapid/src/elspeth/core/landscape/_database_ops.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Create a `LandscapeDB.in_memory()` and `LandscapeRecorder`.
2. Call `update_run_status()` with a non-existent `run_id`.
3. Observe that no exception is raised and no row is updated.

## Expected Behavior

- Tier‑1 audit writes should fail loudly when no rows are affected (e.g., raise `AuditIntegrityError`) to prevent silent audit corruption.

## Actual Behavior

- The update returns without error even when zero rows are affected, leaving the audit trail in a stale or inconsistent state.

## Evidence

- `src/elspeth/core/landscape/_database_ops.py:37` and `src/elspeth/core/landscape/_database_ops.py:42` show `execute_insert`/`execute_update` executing statements without checking `result.rowcount`.
- `src/elspeth/core/landscape/recorder.py:440` shows `update_run_status()` relying on `execute_update()` with no follow-up verification, so a missing run silently no-ops.

## Impact

- User-facing impact: Runs can appear stuck or incorrectly reported (e.g., status never transitions) without any error surfaced.
- Data integrity / security impact: Audit trail can silently miss required state transitions, violating Tier‑1 integrity guarantees.
- Performance or cost impact: Minimal direct impact; potential operational cost from undetected audit inconsistencies.

## Root Cause Hypothesis

- `DatabaseOps.execute_update()` (and `execute_insert()`) do not validate affected row counts, so missing or mismatched identifiers produce silent no-ops instead of crashing as required for Tier‑1 data.

## Proposed Fix

- Code changes (modules/files): Add rowcount validation in `src/elspeth/core/landscape/_database_ops.py` for `execute_update` and `execute_insert` (e.g., raise `AuditIntegrityError` on `rowcount == 0` and optionally assert `rowcount == 1` for single-row writes).
- Config or schema changes: None.
- Tests to add/update: Add unit tests ensuring `update_run_status()` and `update_node_output_contract()` raise on missing rows; optionally add direct tests for `DatabaseOps` rowcount enforcement.
- Risks or migration steps: Ensure any intentional multi-row updates either pass an explicit expected rowcount or use a separate bulk update helper.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:25` (Tier‑1 rules: crash on anomalies, no silent recovery).
- Observed divergence: Tier‑1 audit writes can silently no-op without raising, violating “crash immediately” and “no silent recovery” requirements.
- Reason (if known): `DatabaseOps` write helpers ignore `rowcount`.
- Alignment plan or decision needed: Enforce rowcount checks in `DatabaseOps` and adjust any legitimate bulk updates to use an explicit bulk helper.

## Acceptance Criteria

- `execute_update` and `execute_insert` raise an error when zero rows are affected.
- Recorder update methods fail fast on missing rows instead of silently succeeding.
- New tests cover missing-row updates and pass.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/core/landscape`
- New tests required: Yes, add unit tests for missing-row update behavior.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md`

## Resolution

**Fixed in:** 2026-02-05
**Beads issue:** elspeth-rapid-ozvq (closed)

**Fix:** Added rowcount validation to `DatabaseOps` write helpers:
- `execute_insert()`: Raises `ValueError` if `rowcount == 0` (missing parent row or constraint violation)
- `execute_update()`: Raises `ValueError` if `rowcount == 0` (target row does not exist - audit corruption)
- Per Data Manifesto: "Bad data in the audit trail = crash immediately"

**Evidence:**
- `src/elspeth/core/landscape/_database_ops.py:37-62`: Added rowcount checks to both execute methods
- `tests/core/landscape/test_database_ops.py:96-147`: Added `TestDatabaseOpsTier1Validation` with tests for zero-row and valid updates
- All 556 landscape tests pass
