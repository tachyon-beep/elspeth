# Bug Report: compute_grade accepts invalid determinism values and silently marks run FULL_REPRODUCIBLE

## Summary

- `compute_grade()` never validates determinism values from the audit DB, so corrupted/invalid `nodes.determinism` values are treated as reproducible and the run is incorrectly marked `FULL_REPRODUCIBLE` instead of failing fast.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: Unknown
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: In-memory `LandscapeDB` with manual SQL update to `nodes.determinism`

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `src/elspeth/core/landscape/reproducibility.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Create `LandscapeDB.in_memory()` and begin a run via `LandscapeRecorder`.
2. Insert or update a node row for that run with `determinism = 'garbage_value'` using direct SQL.
3. Call `LandscapeRecorder.compute_reproducibility_grade(run_id)` (or `compute_grade(db, run_id)`).

## Expected Behavior

- The computation crashes with a clear error (e.g., `ValueError`) because audit data contains an invalid enum value.

## Actual Behavior

- The function returns `FULL_REPRODUCIBLE` and does not surface the corrupted determinism value.

## Evidence

- `compute_grade()` only checks for determinism values in a small `non_reproducible` set and never validates that all values are valid enum members: `src/elspeth/core/landscape/reproducibility.py:56-72`.
- Tier 1 audit data rules require crashing on invalid enum values: `CLAUDE.md:25-33`.

## Impact

- User-facing impact: Run metadata can falsely claim full reproducibility.
- Data integrity / security impact: Violates Tier 1 audit integrity; corrupted audit data is silently accepted.
- Performance or cost impact: Low.

## Root Cause Hypothesis

- `compute_grade()` lacks validation of `nodes.determinism` values and treats any unknown value as reproducible by default.

## Proposed Fix

- Code changes (modules/files): Add explicit validation in `compute_grade()` to load distinct determinism values for the run, convert each to `Determinism` enum, and raise on invalid/NULL values before computing the grade.
- Config or schema changes: None.
- Tests to add/update: Add a test that writes an invalid determinism value into `nodes` and asserts `compute_reproducibility_grade()` raises `ValueError`.
- Risks or migration steps: None.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:25-33` (Tier 1 audit data must crash on invalid enums).
- Observed divergence: Invalid determinism values in audit DB do not trigger a crash.
- Reason (if known): Unknown.
- Alignment plan or decision needed: Enforce enum validation in `compute_grade()` before grade calculation.

## Acceptance Criteria

- Invalid determinism values (or NULL) cause `compute_grade()` to raise a clear error.
- Valid determinism values continue to compute correct grades.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/core/landscape/test_recorder_grades.py -v`
- New tests required: yes, add invalid-determinism corruption test for `compute_reproducibility_grade()`.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md`, `docs/design/architecture.md`
