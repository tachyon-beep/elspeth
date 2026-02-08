# Bug Report: NodeStateRepository Allows Invalid OPEN/PENDING Rows Without Crashing

## Summary

- `NodeStateRepository.load()` does not enforce the “forbidden NULL” invariants for `OPEN` and `PENDING` node states, so corrupted audit rows (e.g., `output_hash` or `completed_at` set when they must be NULL) are accepted without crashing.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: RC2.3-pipeline-row (1c70074ef3b71e4fe85d4f926e52afeca50197ab)
- OS: Unknown
- Python version: Unknown
- Config profile / env vars: Unknown
- Data set or fixture: Unknown

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `src/elspeth/core/landscape/repositories.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Insert a `node_states` row with `status='open'` and `completed_at` or `output_hash` non-NULL.
2. Load it via `NodeStateRepository.load()` (e.g., `LandscapeRecorder.get_node_state()`).
3. Observe it returns `NodeStateOpen` without error.

## Expected Behavior

- The repository should raise a `ValueError` when forbidden fields are non-NULL for `OPEN` or `PENDING` states.

## Actual Behavior

- The repository returns `NodeStateOpen` or `NodeStatePending` without validating forbidden fields.

## Evidence

- `NodeStateOpen` and `NodeStatePending` invariants explicitly require no `output_hash`, and `OPEN` must not have `completed_at` or `duration_ms`. See `src/elspeth/contracts/audit.py:154-185`.
- `NodeStateRepository.load()` does not check `output_hash`, `completed_at`, or `duration_ms` for `OPEN`, and does not check `output_hash` for `PENDING`. See `src/elspeth/core/landscape/repositories.py:300-335`.

## Impact

- User-facing impact: Corrupted audit rows can appear valid, undermining audit explanations.
- Data integrity / security impact: Violates Tier 1 audit integrity by allowing invalid state data without crashing.
- Performance or cost impact: None.

## Root Cause Hypothesis

- The repository validates only required fields for `PENDING/COMPLETED/FAILED`, but omits validation of fields that must be NULL for `OPEN` and `PENDING`.

## Proposed Fix

- Code changes (modules/files):
- Add explicit NULL checks for forbidden fields in `NodeStateRepository.load()` for `OPEN` and `PENDING` (`output_hash`, `completed_at`, `duration_ms` as applicable) in `src/elspeth/core/landscape/repositories.py`.
- Config or schema changes: None.
- Tests to add/update:
- Add unit tests to assert `NodeStateRepository.load()` raises on `OPEN` with `completed_at/duration_ms/output_hash` set and `PENDING` with `output_hash` set.
- Risks or migration steps:
- None; this only tightens validation on Tier 1 data.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `src/elspeth/contracts/audit.py:154-185`
- Observed divergence: Repository does not enforce the stated invariants for `OPEN`/`PENDING` states.
- Reason (if known): Unknown
- Alignment plan or decision needed: Enforce invariants in the repository and add tests.

## Acceptance Criteria

- Loading an `OPEN` state with non-NULL `completed_at`, `duration_ms`, or `output_hash` raises `ValueError`.
- Loading a `PENDING` state with non-NULL `output_hash` raises `ValueError`.
- Existing valid rows continue to load successfully.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/`
- New tests required: yes, add targeted repository validation tests for invalid OPEN/PENDING rows.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `src/elspeth/contracts/audit.py`
