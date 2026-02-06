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
---
# Bug Report: TokenOutcomeRepository Does Not Validate `outcome` vs `is_terminal` Consistency

## Summary

- `TokenOutcomeRepository.load()` accepts inconsistent `outcome` and `is_terminal` combinations (e.g., `outcome='buffered'` with `is_terminal=1`) without crashing.

## Severity

- Severity: major
- Priority: P2

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

1. Insert a `token_outcomes` row with `outcome='buffered'` and `is_terminal=1`.
2. Load it via `TokenOutcomeRepository.load()`.
3. Observe it returns a `TokenOutcome` with `is_terminal=True` and no error.

## Expected Behavior

- The repository should raise a `ValueError` when `RowOutcome(row.outcome).is_terminal` disagrees with the stored `is_terminal` flag.

## Actual Behavior

- The repository only validates that `is_terminal` is 0 or 1, then accepts the value as-is.

## Evidence

- `RowOutcome.is_terminal` defines the authoritative terminal/non-terminal rule (`BUFFERED` is non-terminal). See `src/elspeth/contracts/enums.py:161-182`.
- `TokenOutcomeRepository.load()` converts `row.outcome` but does not compare it to `row.is_terminal`. See `src/elspeth/core/landscape/repositories.py:482-493`.

## Impact

- User-facing impact: Token status reports can be incorrect (e.g., buffered tokens treated as terminal).
- Data integrity / security impact: Audit trail can contain internally inconsistent terminal flags without detection.
- Performance or cost impact: None.

## Root Cause Hypothesis

- Missing cross-field validation between `row.outcome` and `row.is_terminal` in the repository.

## Proposed Fix

- Code changes (modules/files):
- Compute `outcome = RowOutcome(row.outcome)` first, compare `outcome.is_terminal` to `row.is_terminal == 1`, and raise on mismatch in `src/elspeth/core/landscape/repositories.py`.
- Config or schema changes: None.
- Tests to add/update:
- Add tests for mismatched `outcome`/`is_terminal` pairs and for valid pairs.
- Risks or migration steps:
- None; this is stricter validation of Tier 1 data.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `src/elspeth/contracts/enums.py:161-182`
- Observed divergence: Repository does not enforce the terminality implied by the `RowOutcome` enum.
- Reason (if known): Unknown
- Alignment plan or decision needed: Add cross-field validation in the repository.

## Acceptance Criteria

- Loading a row with `outcome='buffered'` and `is_terminal=1` raises `ValueError`.
- Loading a row with `outcome='completed'` and `is_terminal=0` raises `ValueError`.
- Valid combinations load successfully.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/`
- New tests required: yes, add repository validation tests for `outcome`/`is_terminal` consistency.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `src/elspeth/contracts/enums.py`
---
# Bug Report: NodeRepository Accepts Malformed `schema_fields_json` Without Crashing

## Summary

- `NodeRepository.load()` parses `schema_fields_json` but never validates it is a `list[dict]`, allowing malformed JSON types (e.g., object or `null`) to be accepted without crashing.

## Severity

- Severity: minor
- Priority: P2

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

1. Insert a `nodes` row with `schema_fields_json='{\"field\":\"x\"}'` or `schema_fields_json='null'`.
2. Load it via `NodeRepository.load()`.
3. Observe it returns a `Node` with `schema_fields` as a dict or `None` without error.

## Expected Behavior

- The repository should raise a `ValueError` if `schema_fields_json` is not a JSON array of objects.

## Actual Behavior

- The repository accepts any JSON type and forwards it into `Node.schema_fields`.

## Evidence

- `Node.schema_fields` is defined as `list[dict[str, object]] | None`. See `src/elspeth/contracts/audit.py:86-89`.
- `NodeRepository.load()` uses `json.loads()` without type validation. See `src/elspeth/core/landscape/repositories.py:90-93`.

## Impact

- User-facing impact: Schema audit metadata may be malformed without detection.
- Data integrity / security impact: Violates Tier 1 strictness by allowing invalid audit data types.
- Performance or cost impact: None.

## Root Cause Hypothesis

- Missing type checks after `json.loads()` for `schema_fields_json`.

## Proposed Fix

- Code changes (modules/files):
- After `json.loads()`, validate `schema_fields` is a list and each element is a dict; otherwise raise `ValueError` in `src/elspeth/core/landscape/repositories.py`.
- Config or schema changes: None.
- Tests to add/update:
- Add tests that invalid `schema_fields_json` types raise, and valid list-of-dict JSON loads.
- Risks or migration steps:
- None; this is stricter validation of Tier 1 data.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `src/elspeth/contracts/audit.py:86-89`
- Observed divergence: Repository does not enforce the declared `schema_fields` type.
- Reason (if known): Unknown
- Alignment plan or decision needed: Enforce type validation in the repository.

## Acceptance Criteria

- Loading `schema_fields_json` with non-list JSON raises `ValueError`.
- Loading `schema_fields_json` with list elements that are not dicts raises `ValueError`.
- Valid list-of-dict JSON loads successfully.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/`
- New tests required: yes, add repository validation tests for malformed `schema_fields_json`.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `src/elspeth/contracts/audit.py`
