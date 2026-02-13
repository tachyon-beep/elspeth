# Bug Report: Optional Float Fields Lose Type Enforcement in Transform Output Contracts

**Status: CLOSED**

## Status Update (2026-02-13)

- Classification: **Resolved**
- Resolution summary:
  - Optional float type extraction is now handled correctly in transform contract
    type resolution by unwrapping `Annotated` and resolving `Optional`/`Union`
    members to primitive contract types.
  - Regression coverage exists for schema-factory optional float behavior and
    validation enforcement.
- Current evidence:
  - `src/elspeth/contracts/transform_contract.py:25`
  - `src/elspeth/contracts/transform_contract.py:36`
  - `tests/unit/contracts/test_transform_contract.py:179`
- Verification summary:
  - `.venv/bin/python -m pytest tests/unit/contracts/test_transform_contract.py -k "optional_float" -q` passes.

## Status Update (2026-02-11)

- Classification: **Still open**
- Verification summary:
  - Optional float schema types still pass through `Annotated[...] | None` extraction and resolve to `python_type=object` in output contracts.
  - Contract validation still skips type enforcement when `python_type is object`.
- Current evidence:
  - `src/elspeth/contracts/transform_contract.py:37`
  - `src/elspeth/contracts/transform_contract.py:44`
  - `src/elspeth/contracts/schema_contract.py:223`

## Summary

- Optional float fields created via `create_schema_from_config()` become `python_type=object` in the output `SchemaContract`, so type mismatches are never flagged.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: Unknown
- OS: Unknown
- Python version: Unknown
- Config profile / env vars: N/A
- Data set or fixture: SchemaConfig with an optional float field (required=False)

## Agent Context (if relevant)

- Goal or task prompt: You are a static analysis agent doing a deep bug audit. Target file: /home/john/elspeth-rapid/src/elspeth/contracts/transform_contract.py
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Create a `SchemaConfig` with a float field marked `required=False` and build a schema with `create_schema_from_config()` (this produces `FiniteFloat | None`).
2. Call `create_output_contract_from_schema()` on the resulting schema class.
3. Observe the field’s `python_type` is `object` instead of `float`, and a non-float value passes `SchemaContract.validate()` without a `TypeMismatchViolation`.

## Expected Behavior

- Optional float fields should retain `python_type=float` (while still allowing `None`), so non-float values are flagged by contract validation.

## Actual Behavior

- Optional float fields are treated as `python_type=object`, which skips type validation entirely.

## Evidence

- `src/elspeth/contracts/transform_contract.py:33-60` — `_get_python_type()` only maps primitive types and does not unwrap `Annotated` inside a `Union`; it returns `object` for unknown union members.
- `src/elspeth/plugins/schema_factory.py:23-35, 107-115, 133-150` — float fields use `FiniteFloat = Annotated[float, Field(...)]` and optional fields are built as `base_type | None`, yielding `Annotated[float, ...] | None`.
- `src/elspeth/contracts/schema_contract.py:214-238` — `python_type is object` explicitly skips type validation.

## Impact

- User-facing impact: Transform outputs with optional float fields can silently emit non-float values without contract violations.
- Data integrity / security impact: Audit trail contract claims type safety but allows arbitrary values for optional float fields, weakening type integrity guarantees.
- Performance or cost impact: Unknown

## Root Cause Hypothesis

- `_get_python_type()` in `src/elspeth/contracts/transform_contract.py` does not unwrap `Annotated` types inside `Union`/`Optional`, so `Annotated[float, ...] | None` resolves to `object` instead of `float`.

## Proposed Fix

- Code changes (modules/files): Update `_get_python_type()` in `src/elspeth/contracts/transform_contract.py` to unwrap `Annotated` types (including within `Union`) before mapping to `_TYPE_MAP`.
- Config or schema changes: None
- Tests to add/update: Add a test in `tests/contracts/test_transform_contract.py` that builds a schema via `create_schema_from_config()` with `field_type="float"` and `required=False`, then asserts `python_type is float` and `validate_output_against_contract` flags a non-float.
- Risks or migration steps: Low risk; change only affects contract type extraction.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md` (Three-Tier Trust Model: transforms should not accept wrong types; schema contracts must enforce expected types)
- Observed divergence: Optional float fields in transform output schemas are treated as `any`, allowing wrong types without violations.
- Reason (if known): Missing `Annotated` unwrapping in `_get_python_type()` when `Optional` is used.
- Alignment plan or decision needed: Add `Annotated` handling in `_get_python_type()` and add a test covering schema_factory-created optional float fields.

## Acceptance Criteria

- Optional float fields created via `create_schema_from_config()` produce `FieldContract.python_type is float`.
- `validate_output_against_contract()` reports `TypeMismatchViolation` for non-float values in those fields.
- New regression test passes.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/contracts/test_transform_contract.py`
- New tests required: yes, add an optional-float schema_factory contract extraction test.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md` (Three-Tier Trust Model)
