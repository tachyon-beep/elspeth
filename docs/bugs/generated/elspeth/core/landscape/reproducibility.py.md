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
---
# Bug Report: IO_READ/IO_WRITE nodes misclassified as FULL_REPRODUCIBLE

## Summary

- `compute_grade()` treats `IO_READ` and `IO_WRITE` as fully reproducible, but protocol and architecture docs define them as external/side-effectful operations that require replay, so runs with these nodes should be `REPLAY_REPRODUCIBLE`.

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
- Data set or fixture: In-memory `LandscapeDB` with a node declared as `Determinism.IO_READ` or `Determinism.IO_WRITE`

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `src/elspeth/core/landscape/reproducibility.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Create `LandscapeDB.in_memory()` and begin a run via `LandscapeRecorder`.
2. Register a node with `determinism=Determinism.IO_READ` (or `IO_WRITE`).
3. Call `LandscapeRecorder.compute_reproducibility_grade(run_id)`.

## Expected Behavior

- The run should be graded `REPLAY_REPRODUCIBLE` because IO-based nodes depend on external state or side effects that require captured data for replay.

## Actual Behavior

- The run is graded `FULL_REPRODUCIBLE`.

## Evidence

- `compute_grade()` explicitly treats `IO_READ` and `IO_WRITE` as reproducible and only flags `EXTERNAL_CALL` and `NON_DETERMINISTIC` for replay: `src/elspeth/core/landscape/reproducibility.py:42-60`.
- Determinism contract defines `IO_READ` and `IO_WRITE` as external/side-effectful, requiring capture/replay: `docs/contracts/plugin-protocol.md:1327-1337`.
- Run-level grade definition says `FULL_REPRODUCIBLE` requires all transforms deterministic: `docs/design/architecture.md:675-680`.

## Impact

- User-facing impact: Runs with IO-based transforms are mislabeled as fully reproducible.
- Data integrity / security impact: Overstates reproducibility; replay expectations become incorrect.
- Performance or cost impact: Low.

## Root Cause Hypothesis

- The `non_reproducible` set in `compute_grade()` omits `IO_READ` and `IO_WRITE`, so IO-dependent nodes do not trigger replay grading.

## Proposed Fix

- Code changes (modules/files): Treat `IO_READ` and `IO_WRITE` as replay-required in `compute_grade()` (e.g., add them to `non_reproducible` or compute FULL only if all values are `{DETERMINISTIC, SEEDED}`); update docstring to match behavior.
- Config or schema changes: None.
- Tests to add/update: Add tests that verify `IO_READ` and `IO_WRITE` nodes produce `REPLAY_REPRODUCIBLE`.
- Risks or migration steps: None.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `docs/design/architecture.md:675-680`, `docs/contracts/plugin-protocol.md:1327-1337`.
- Observed divergence: IO-based determinism values are treated as full reproducibility rather than replay-required.
- Reason (if known): Unknown.
- Alignment plan or decision needed: Align `compute_grade()` with determinism contract by classifying IO-based nodes as replay-required.

## Acceptance Criteria

- A run containing any `IO_READ` or `IO_WRITE` nodes is graded `REPLAY_REPRODUCIBLE`.
- Tests cover IO-based determinism values.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/core/landscape/test_recorder_grades.py -v`
- New tests required: yes, add IO_READ/IO_WRITE grade tests.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `docs/contracts/plugin-protocol.md`, `docs/design/architecture.md`
