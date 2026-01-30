# Bug Report: compute_grade silently accepts invalid node determinism values

## Summary

- `compute_grade()` does not validate `nodes.determinism` values from the Landscape DB, so corrupted/invalid enum values are silently treated as reproducible and can yield `FULL_REPRODUCIBLE` instead of crashing as required by Tier 1 audit rules.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-01-30
- Related run/issue ID: N/A

## Environment

- Commit/branch: 17f7293805c0c36aa59bf5fad0f09e09c3035fc9 (fix/P2-aggregation-metadata-hardcoded)
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: in-memory LandscapeDB with a manually inserted invalid determinism value

## Agent Context (if relevant)

- Goal or task prompt: static analysis deep bug audit for `src/elspeth/core/landscape/reproducibility.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Create a run in an in-memory `LandscapeDB` and insert a node row with `nodes.determinism = "garbage"` directly into `nodes_table`.
2. Call `compute_grade(db, run_id)` or `LandscapeRecorder.compute_reproducibility_grade(run_id)`.

## Expected Behavior

- The call should raise an error (e.g., `ValueError`) because an invalid enum value in the audit DB is corruption and must crash immediately.

## Actual Behavior

- The call returns `ReproducibilityGrade.FULL_REPRODUCIBLE` because it only checks for the presence of `EXTERNAL_CALL` or `NON_DETERMINISTIC` and ignores invalid determinism values.

## Evidence

- `compute_grade()` only queries for “non_reproducible” values and never validates determinism values for the run. `src/elspeth/core/landscape/reproducibility.py:56-77`
- Tier 1 audit rule requires crashing on invalid enum values in the audit trail. `CLAUDE.md:40-41`

## Impact

- User-facing impact: Reproducibility grades can be overstated (e.g., marked fully reproducible) even when the audit data is corrupted.
- Data integrity / security impact: Violates Tier 1 audit requirements; corrupted audit trail can pass silently, undermining legal traceability.
- Performance or cost impact: None directly; but can increase investigation costs and risk.

## Root Cause Hypothesis

- `compute_grade()` bypasses the strict enum validation used elsewhere (e.g., `NodeRepository.load`) and only checks for two determinism values, so invalid or unexpected determinism strings are treated as reproducible.

## Proposed Fix

- Code changes (modules/files):
  - Add explicit validation of all distinct `nodes.determinism` values for `run_id` in `src/elspeth/core/landscape/reproducibility.py` before classifying grade. Raise on `NULL` or unknown values.
- Config or schema changes: None.
- Tests to add/update:
  - Add a test that inserts a node with invalid determinism and asserts `compute_grade()` raises (e.g., `tests/core/landscape/test_recorder_grades.py`).
- Risks or migration steps:
  - None; behavior change is limited to corrupted data paths.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:40-41`
- Observed divergence: `compute_grade()` does not crash on invalid enum values from the audit DB.
- Reason (if known): Optimization to check only “non_reproducible” values bypassed validation.
- Alignment plan or decision needed: Validate determinism values before computing grade; treat invalid values as fatal.

## Acceptance Criteria

- `compute_grade()` raises on any invalid/NULL `nodes.determinism` for a run.
- New test for invalid determinism passes; existing reproducibility grade tests remain green.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/core/landscape/test_recorder_grades.py::TestReproducibilityGradeComputation -v`
- New tests required: yes, invalid determinism enum test as described.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md` (Tier 1 audit integrity rules)
