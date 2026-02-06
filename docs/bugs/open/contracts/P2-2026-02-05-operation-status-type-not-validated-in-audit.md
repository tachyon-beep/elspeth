# Bug Report: Operation Status/Type Not Validated in Audit Contract

## Summary

- `Operation.operation_type` and `Operation.status` are plain string Literals with no runtime validation, so invalid values can be loaded from the audit DB without crashing.

## Severity

- Severity: major
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
- Data set or fixture: N/A (contract-only)

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `src/elspeth/contracts/audit.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Instantiate `Operation(operation_type="bad_type", status="oops", ...)`.
2. Observe that no exception is raised and the invalid values are accepted.

## Expected Behavior

- Invalid `operation_type`/`status` values should crash immediately when constructing or loading `Operation` objects.

## Actual Behavior

- Any string value is accepted for these fields; no validation exists at the contract layer.

## Evidence

- `Operation.operation_type` and `Operation.status` are declared as Literal strings with no validation. `src/elspeth/contracts/audit.py:622`, `src/elspeth/contracts/audit.py:625`, `src/elspeth/contracts/audit.py:627`
- `get_operation` returns `Operation` using raw DB values without validation. `src/elspeth/core/landscape/recorder.py:2557`, `src/elspeth/core/landscape/recorder.py:2561`, `src/elspeth/core/landscape/recorder.py:2564`
- The operations schema explicitly documents allowed values, but contract does not enforce them. `src/elspeth/core/landscape/schema.py:231`, `src/elspeth/core/landscape/schema.py:234`

## Impact

- User-facing impact: Audit reads may show invalid operation states without any error, reducing confidence in audit output.
- Data integrity / security impact: Tier 1 audit integrity rule (“invalid enum value = crash”) is violated for operations data.
- Performance or cost impact: None.

## Root Cause Hypothesis

- Audit contract lacks enums or validation for `Operation` fields that are constrained in the schema.

## Proposed Fix

- Code changes (modules/files): Add `__post_init__` validation in `src/elspeth/contracts/audit.py:601` to enforce allowed values, or introduce `OperationStatus`/`OperationType` enums in `src/elspeth/contracts/enums.py` and use `_validate_enum`.
- Config or schema changes: None.
- Tests to add/update: Add a contract validation test for invalid operation status/type.
- Risks or migration steps: If introducing enums, update recorder and any callers to pass enums or `.value`.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:25`
- Observed divergence: Audit data does not crash on invalid operation status/type.
- Reason (if known): No validation in `Operation` contract for constrained string values.
- Alignment plan or decision needed: Enforce allowed values at contract layer per Tier 1 requirements.

## Acceptance Criteria

- Constructing or loading an `Operation` with invalid `operation_type` or `status` raises immediately.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/core/landscape -k operation`
- New tests required: yes, add invalid operation status/type validation test.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md:25`
