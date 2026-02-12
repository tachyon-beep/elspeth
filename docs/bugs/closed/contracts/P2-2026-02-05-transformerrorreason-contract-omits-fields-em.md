# Bug Report: TransformErrorReason Contract Omits Fields Emitted by Contract-Violation Helpers

**Status: CLOSED**

## Pre-Fix Verification (2026-02-11)

- Classification: **Still open**
- Verification summary:
  - `TransformErrorReason` still lacks the contract-violation keys emitted by helper serializers (e.g., `violation_type`, `expected_type`, `count`, `violations`).
  - Violation helper functions still emit those extra keys today, so schema/output mismatch remains.
- Current evidence:
  - `src/elspeth/contracts/errors.py:251`
  - `src/elspeth/contracts/errors.py:607`
  - `src/elspeth/contracts/errors.py:769`

## Resolution (2026-02-13)

- Status: **FIXED**
- Changes applied:
  - Added missing optional fields to `TransformErrorReason` for contract-violation
    helper payloads: `violation_type`, `original_field`, `expected_type`,
    `actual_value`, `count`, and `violations`.
  - Updated `TransformErrorReason` docstring to document contract-violation context.
  - Added an alignment test ensuring all keys emitted by contract-violation
    helpers are declared in `TransformErrorReason`.
- Files changed:
  - `src/elspeth/contracts/errors.py`
  - `tests/unit/contracts/test_contract_violation_error.py`
- Verification:
  - `./.venv/bin/python -m pytest tests/unit/contracts/test_contract_violation_error.py -q` (26 passed)
  - `./.venv/bin/python -m ruff check src/elspeth/contracts/errors.py tests/unit/contracts/test_contract_violation_error.py` (passed)

## Summary

- `ContractViolation.to_error_reason()` and `violations_to_error_reason()` emit fields that are not declared in `TransformErrorReason`, creating a schema/contract mismatch for transform error payloads.

## Severity

- Severity: minor
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: `e0060836d4bb129f1a37656d85e548ae81db8887` on `RC2.3-pipeline-row`
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Unknown

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit for `src/elspeth/contracts/errors.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Create a `TypeMismatchViolation` and call `to_error_reason()`.
2. Create multiple violations and call `violations_to_error_reason([...])`.
3. Compare returned keys to `TransformErrorReason` fields.

## Expected Behavior

- The `TransformErrorReason` schema should declare all fields produced by `ContractViolation.to_error_reason()` and `violations_to_error_reason()` (e.g., `violation_type`, `original_field`, `expected_type`, `actual_type`, `actual_value`, `count`, `violations`) so the contract matches actual payloads.

## Actual Behavior

- `TransformErrorReason` omits several fields produced by contract-violation helpers, so the documented schema does not match emitted error payloads.

## Evidence

- `TransformErrorReason` fields do not include `violation_type`, `original_field`, `expected_type`, `actual_type`, `actual_value`, `count`, or `violations`. See `src/elspeth/contracts/errors.py:270-360`.
- `ContractViolation.to_error_reason()` emits `violation_type` and `original_field`. See `src/elspeth/contracts/errors.py:598-610`.
- `TypeMismatchViolation.to_error_reason()` emits `expected_type`, `actual_type`, `actual_value`. See `src/elspeth/contracts/errors.py:685-700`.
- `violations_to_error_reason()` emits `count` and `violations`. See `src/elspeth/contracts/errors.py:760-803`.

## Impact

- User-facing impact: Audit error payloads may include fields that the declared schema does not acknowledge, causing confusion for plugin authors and reviewers.
- Data integrity / security impact: Potential loss of structured error context if future validation or serialization enforces the declared schema.
- Performance or cost impact: None.

## Root Cause Hypothesis

- The contract-violation helpers evolved to include richer fields, but `TransformErrorReason` was not updated to reflect those fields.

## Proposed Fix

- Code changes (modules/files):
  - Add `NotRequired` fields to `TransformErrorReason` for `violation_type`, `original_field`, `expected_type`, `actual_type`, `actual_value`, `count`, and `violations` in `src/elspeth/contracts/errors.py`.
  - Update the `TransformErrorReason` docstring to document these contract-violation-specific fields.
- Config or schema changes: None.
- Tests to add/update:
  - Add a test asserting that the `TransformErrorReason` contract includes the contract-violation fields (or add a mypy/alignment check if one exists).
- Risks or migration steps:
  - Low risk; only expands the schema contract with optional fields.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): Unknown
- Observed divergence: Schema contract for transform error payloads is incomplete relative to emitted data.
- Reason (if known): Likely overlooked during contract-violation helper additions.
- Alignment plan or decision needed: Update `TransformErrorReason` to include all emitted fields.

## Acceptance Criteria

- `TransformErrorReason` includes all fields emitted by `ContractViolation.to_error_reason()` and `violations_to_error_reason()`.
- Documentation in `TransformErrorReason` reflects these fields.
- Contract-violation error payloads are accepted without schema mismatch.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/contracts/test_contract_violation_error.py`
- New tests required: yes, add a schema alignment test for `TransformErrorReason` fields.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: Unknown
