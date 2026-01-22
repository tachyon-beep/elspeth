# Bug Report: RunRepository masks invalid export_status values

## Summary

`RunRepository.load` treats falsy `export_status` values as None, so invalid values like "" bypass `ExportStatus` coercion and do not crash. This masks Tier 1 data corruption and misreports export status, violating the audit DB "crash on anomaly" rule.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex (static analysis agent)
- Date: 2026-01-22
- Related run/issue ID: Unknown

## Environment

- Commit/branch: main (d8df733)
- OS: Linux
- Python version: 3.12+
- Config profile / env vars: Any
- Data set or fixture: Corrupted audit DB with invalid export_status

## Agent Context (if relevant)

- Goal or task prompt: Static analysis bug audit of repositories.py
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): sandbox_mode=read-only, approval_policy=never
- Determinism details (seed, run ID): Unknown
- Notable tool calls or steps: Reviewed repository, contracts, schema, and recorder mappings

## Steps To Reproduce

1. Create a mock row with `export_status=""` (or another falsy non-None value) and valid required fields
2. Call `RunRepository.load(mock_row)`
3. Inspect `Run.export_status`

## Expected Behavior

- Invalid `export_status` values should raise `ValueError` (or otherwise crash) during `ExportStatus` coercion
- Only `None` should map to `None`

## Actual Behavior

- `export_status` is returned as `None` with no exception, masking the invalid value

## Evidence

- Logs or stack traces: Unknown
- Artifacts (paths, IDs, screenshots):
  - `src/elspeth/core/landscape/repositories.py:55`
  - `src/elspeth/core/landscape/recorder.py:338`
  - `src/elspeth/contracts/audit.py:43`
- Minimal repro input (attach or link): Mock row with `export_status=""`

## Impact

- User-facing impact: Export status can appear "unset" when the DB contains an invalid value
- Data integrity / security impact: Violates Tier 1 crash-on-anomaly rule by silently accepting corrupted audit data
- Performance or cost impact: Unknown

## Root Cause Hypothesis

`export_status` is gated by a truthiness check instead of an explicit `None` check, so falsy invalid values bypass enum validation.

## Proposed Fix

- Code changes (modules/files): Update `RunRepository.load` in `src/elspeth/core/landscape/repositories.py:55` to use `row.export_status is not None` before coercion
- Config or schema changes: None
- Tests to add/update: Add a test for empty-string `export_status` in `tests/core/landscape/test_repositories.py`
- Risks or migration steps: None

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:40` - "invalid enum value = crash"
- Observed divergence: Invalid audit DB values can be silently coerced to None instead of crashing
- Reason (if known): Unknown
- Alignment plan or decision needed: Enforce explicit None checks and allow invalid values to raise

## Acceptance Criteria

- `RunRepository.load` raises `ValueError` for `export_status=""` (or other non-None invalid values)
- Preserves `None` as `None`
- Valid strings coerce to `ExportStatus` enums correctly

## Tests

- Suggested tests to run: `pytest tests/core/landscape/test_repositories.py::TestRunRepository`
- New tests required: Add a case asserting empty-string `export_status` raises `ValueError`

## Notes / Links

- Related issues/PRs: Unknown
- Related design docs: `CLAUDE.md:32`

## Verification Status

- [ ] Bug confirmed via reproduction
- [ ] Root cause verified
- [ ] Fix implemented
- [ ] Tests added
- [ ] Fix verified
