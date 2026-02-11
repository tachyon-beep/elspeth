# Bug Report: Array and Nested Object Schemas Lose Type Fidelity on Resume

**Status: OPEN**

## Status Update (2026-02-11)

- Classification: **Still open**
- Verification summary:
  - Schema reconstruction still returns bare `list` for arrays and bare `dict` for objects.
  - Recursive handling of `items`/`properties` is still not implemented, so nested type fidelity is still lost on resume.
- Current evidence:
  - `src/elspeth/engine/orchestrator/export.py:326`
  - `src/elspeth/engine/orchestrator/export.py:329`
  - `src/elspeth/engine/orchestrator/export.py:332`
  - `src/elspeth/engine/orchestrator/export.py:334`

## Summary

- `_json_schema_to_python_type` ignores `items` for arrays and `properties` for objects, returning bare `list`/`dict`. This drops item and nested field types, violating the stated intent to reconstruct full schemas.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: Unknown
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Pipelines with list fields (e.g., `list[int]`) or nested object fields in source schema

## Agent Context (if relevant)

- Goal or task prompt: You are a static analysis agent doing a deep bug audit. Target file: `/home/john/elspeth-rapid/src/elspeth/engine/orchestrator/export.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Define a source schema containing a list field or nested object field.
2. Run a pipeline and resume from checkpoint.
3. Inspect the reconstructed schema or validate a row with incorrect list item types.

## Expected Behavior

- Array item types and nested object property types should be reconstructed and validated.

## Actual Behavior

- Arrays are reconstructed as `list` without item type validation.
- Objects are reconstructed as `dict` without nested schema validation.

## Evidence

- `src/elspeth/engine/orchestrator/export.py:169-175` claims arrays and nested objects are handled.
- `src/elspeth/engine/orchestrator/export.py:307-316` returns bare `list`/`dict` and never inspects `items` or `properties`.

## Impact

- User-facing impact: Resume permits invalid types inside lists or nested objects without error.
- Data integrity / security impact: Type fidelity is lost across resume boundaries, violating the three-tier trust model.
- Performance or cost impact: Potential downstream failures or silent data drift.

## Root Cause Hypothesis

- `_json_schema_to_python_type` was implemented with placeholder handling for arrays/objects and never expanded to recursive type reconstruction.

## Proposed Fix

- Code changes (modules/files):
  - `src/elspeth/engine/orchestrator/export.py`: Recursively resolve `items` for arrays and `properties` for objects, constructing nested Pydantic models for object fields.
- Config or schema changes: None
- Tests to add/update:
  - Add schema reconstruction tests for list and nested object fields in `tests/unit/engine/test_export.py`.
- Risks or migration steps:
  - Low risk; increases validation fidelity on resume.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): Unknown
- Observed divergence: Docstring claims support for arrays and nested objects but implementation drops type details.
- Reason (if known): Placeholder implementation left in place.
- Alignment plan or decision needed: Implement recursive schema reconstruction.

## Acceptance Criteria

1. Arrays reconstruct as `list[InnerType]` with item validation.
2. Nested objects reconstruct as nested Pydantic models with property validation.
3. Tests cover list and nested object schemas on resume.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/unit/engine/test_export.py -v`
- New tests required: yes, list and nested object reconstruction cases.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: Unknown
