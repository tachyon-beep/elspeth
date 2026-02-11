# Bug Report: Missing-value sentinels (pd.NA, np.datetime64("NaT")) not normalized to `type(None)`

**Status: OPEN**

## Status Update (2026-02-11)

- Classification: **Still open**
- Verification summary:
  - `pd.NA` handling is still missing in contract type normalization.
  - `np.datetime64` values are still normalized as `datetime` without a `np.isnat()` check for `NaT`.
- Current evidence:
  - `src/elspeth/contracts/type_normalization.py:55`
  - `src/elspeth/contracts/type_normalization.py:67`

## Summary

- `normalize_type_for_contract()` treats `pd.NA` as an unsupported type and treats `np.datetime64("NaT")` as a valid `datetime`, which can crash first-row contract inference and allow missing datetimes to pass type checks.

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
- Data set or fixture: Row containing `pd.NA` or `np.datetime64("NaT")`

## Agent Context (if relevant)

- Goal or task prompt: Deep bug audit of `src/elspeth/contracts/type_normalization.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Call `normalize_type_for_contract(pd.NA)` or run `ContractBuilder.process_first_row()` with a row containing `pd.NA`.
2. Call `normalize_type_for_contract(np.datetime64("NaT"))` or validate a row with a required datetime field set to `np.datetime64("NaT")`.

## Expected Behavior

- `pd.NA` and `np.datetime64("NaT")` should normalize to `type(None)` so missing-value handling aligns with canonical policy and optional/required field checks behave correctly.

## Actual Behavior

- `pd.NA` raises `TypeError` as “Unsupported type,” which can crash first-row inference.
- `np.datetime64("NaT")` normalizes to `datetime`, so missing datetimes can pass type validation.

## Evidence

- `src/elspeth/contracts/type_normalization.py:54-76` handles `pd.NaT` and all `np.datetime64` as `datetime`, with no `pd.NA` or `np.isnat()` handling.
- `src/elspeth/contracts/type_normalization.py:80-88` raises `TypeError` for unsupported types, which includes `pd.NA`.
- `src/elspeth/contracts/contract_builder.py:84-95` calls `with_field()` during first-row inference without catching `TypeError`, so `pd.NA` can crash inference.
- `docs/design/architecture.md:421-424` documents `None/pd.NA/NaT` as intentional missing values, implying they should be normalized to `None`.

## Impact

- User-facing impact: Observed/flexible schema inference can crash on first row if missing values are represented as `pd.NA`.
- Data integrity / security impact: Missing datetimes represented as `np.datetime64("NaT")` can be treated as valid datetimes, weakening required-field enforcement.
- Performance or cost impact: Potential pipeline aborts and retries from avoidable inference crashes.

## Root Cause Hypothesis

- `normalize_type_for_contract()` does not recognize `pd.NA` or `np.datetime64("NaT")` as missing-value sentinels, despite the canonical missing-value policy.

## Proposed Fix

- Code changes (modules/files): Update `src/elspeth/contracts/type_normalization.py` to return `type(None)` for `value is pd.NA` and for `isinstance(value, np.datetime64) and np.isnat(value)` before the generic `np.datetime64` branch.
- Config or schema changes: None.
- Tests to add/update: Add unit tests in `tests/contracts/test_type_normalization.py` for `pd.NA` and `np.datetime64("NaT")` normalization to `type(None)`.
- Risks or migration steps: None.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `docs/design/architecture.md:421-424`
- Observed divergence: Canonical policy treats `pd.NA/NaT` as intentional missing values, but contract normalization rejects `pd.NA` and treats NumPy `NaT` as a valid `datetime`.
- Reason (if known): Missing sentinel handling not implemented in `normalize_type_for_contract()`.
- Alignment plan or decision needed: Normalize missing sentinels to `type(None)` to match canonical policy.

## Acceptance Criteria

- `normalize_type_for_contract(pd.NA)` returns `type(None)`.
- `normalize_type_for_contract(np.datetime64("NaT"))` returns `type(None)`.
- First-row contract inference no longer crashes on `pd.NA`.
- Missing datetimes no longer pass type checks as valid `datetime` values.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/contracts/test_type_normalization.py`
- New tests required: yes, add cases for `pd.NA` and `np.datetime64("NaT")`.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `docs/design/architecture.md`
