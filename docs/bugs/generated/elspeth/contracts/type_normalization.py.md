# Bug Report: normalize_type_for_contract misses pandas.NA and NumPy NaT missing-value sentinels

## Summary

- Missing-value sentinels (`pd.NA`, `np.datetime64("NaT")`) are not normalized to `type(None)`, causing contract inference crashes and allowing missing datetimes to pass as valid types.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-02-03
- Related run/issue ID: N/A

## Environment

- Commit/branch: Unknown
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

- Missing-value sentinels (`pd.NA`, `np.datetime64("NaT")`) normalize to `type(None)` so optional-field handling works and required fields can be flagged as missing.

## Actual Behavior

- `pd.NA` raises `TypeError` as an unsupported type, which can crash first-row contract inference.
- `np.datetime64("NaT")` is normalized to `datetime`, allowing missing datetime values to pass type checks as if valid.

## Evidence

- `src/elspeth/contracts/type_normalization.py:57-76` only handles `pd.NaT` and normalizes all `np.datetime64` to `datetime`, with no `pd.NA` or `np.isnat()` handling.
- `src/elspeth/contracts/type_normalization.py:80-88` raises `TypeError` for unsupported types, which includes `pd.NA` (NAType).
- `src/elspeth/contracts/contract_builder.py:84-95` calls `with_field()` during first-row inference without catching `TypeError`, so `pd.NA` can crash inference.
- `src/elspeth/core/canonical.py:44-100` documents that intentional missing values are `None/pd.NA/NaT`, so contract normalization should accept them.

## Impact

- User-facing impact: Pipelines can crash on first-row inference when missing values are represented as `pd.NA`.
- Data integrity / security impact: Missing datetime values represented as `np.datetime64("NaT")` can be treated as valid datetimes, weakening required-field enforcement.
- Performance or cost impact: N/A

## Root Cause Hypothesis

- `normalize_type_for_contract()` does not recognize `pd.NA` or `np.datetime64("NaT")` as missing-value sentinels, despite the canonical policy that these represent missing data.

## Proposed Fix

- Code changes (modules/files): Update `src/elspeth/contracts/type_normalization.py` to return `type(None)` for `value is pd.NA` and for `isinstance(value, np.datetime64) and np.isnat(value)` before the generic `np.datetime64` path.
- Config or schema changes: None.
- Tests to add/update: Add unit tests in `tests/contracts/test_type_normalization.py` for `pd.NA` and `np.datetime64("NaT")` normalization to `type(None)`.
- Risks or migration steps: Low risk; aligns with existing canonical missing-value policy.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `src/elspeth/core/canonical.py:44-100`
- Observed divergence: Canonical policy treats `pd.NA/NaT` as missing, but contract normalization rejects `pd.NA` and treats NumPy `NaT` as a valid datetime type.
- Reason (if known): Missing sentinel handling not implemented in `normalize_type_for_contract()`.
- Alignment plan or decision needed: Add missing-sentinel checks to match canonical policy.

## Acceptance Criteria

- `normalize_type_for_contract(pd.NA)` returns `type(None)`.
- `normalize_type_for_contract(np.datetime64("NaT"))` returns `type(None)`.
- First-row contract inference no longer crashes on `pd.NA`.
- New unit tests pass.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/contracts/test_type_normalization.py`
- New tests required: yes, add cases for `pd.NA` and `np.datetime64("NaT")`.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `src/elspeth/core/canonical.py`
