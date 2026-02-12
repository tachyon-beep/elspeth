# Bug Report: TokenOutcomeRepository Does Not Validate `outcome` vs `is_terminal` Consistency

**Status: CLOSED**

## Status Update (2026-02-11)

- Classification: **Still open**
- Verification summary:
  - Repository still validates only that `is_terminal` is in `(0,1)`, but does not cross-check against `RowOutcome(...).is_terminal`.
  - Repro still loads inconsistent row (`outcome='buffered'`, `is_terminal=1`) without raising.
- Current evidence:
  - `src/elspeth/core/landscape/repositories.py:502`
  - `src/elspeth/core/landscape/repositories.py:513`

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

## Resolution (2026-02-12)

- Status: CLOSED
- Fixed by commit: `19066c1a`
- Fix summary: Validate outcome terminal consistency in TokenOutcomeRepository
- Ticket moved from `docs/bugs/open/` to `docs/bugs/closed/` on 2026-02-12.
