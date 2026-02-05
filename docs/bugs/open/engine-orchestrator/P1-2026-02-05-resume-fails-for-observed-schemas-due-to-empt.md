# Bug Report: Resume Fails for Observed Schemas Due to Empty `properties` Rejection

## Summary

- `reconstruct_schema_from_json` rejects schemas with empty `properties`, which is the normal JSON schema output for observed/dynamic source schemas. This causes resume to fail for pipelines using `schema.mode: observed`.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: Unknown
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Any pipeline using source schema mode `observed` (dynamic schema)

## Agent Context (if relevant)

- Goal or task prompt: You are a static analysis agent doing a deep bug audit. Target file: `/home/john/elspeth-rapid/src/elspeth/engine/orchestrator/export.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Configure a source schema with `mode: observed` (dynamic schema).
2. Run a pipeline to create a checkpointed run.
3. Attempt `resume`, which calls `reconstruct_schema_from_json` for the stored schema.

## Expected Behavior

- Observed schemas should reconstruct to a dynamic Pydantic model (extra allowed, no fixed fields), allowing resume to proceed.

## Actual Behavior

- Resume fails with `ValueError` because `reconstruct_schema_from_json` rejects empty `properties`.

## Evidence

- `src/elspeth/engine/orchestrator/export.py:191-202` raises on empty `properties`, treating empty schema as fatal.
- `src/elspeth/plugins/schema_factory.py:70-91` shows observed mode returns a dynamic schema with no fields.
- `src/elspeth/engine/orchestrator/core.py:413-427` persists `output_schema.model_json_schema()` for all sources, including dynamic schemas.

## Impact

- User-facing impact: Resume fails for any run using observed/dynamic source schemas.
- Data integrity / security impact: N/A (resume is blocked, no data corruption).
- Performance or cost impact: Operators must restart pipelines from scratch, increasing compute cost.

## Root Cause Hypothesis

- `reconstruct_schema_from_json` treats empty `properties` as an error, but observed schemas intentionally have no declared fields.

## Proposed Fix

- Code changes (modules/files):
  - `src/elspeth/engine/orchestrator/export.py`: When `properties` is empty, return a dynamic schema (equivalent to `_create_dynamic_schema`) instead of raising.
- Config or schema changes: None
- Tests to add/update:
  - Add tests for observed schema reconstruction in `tests/unit/engine/test_export.py`.
- Risks or migration steps:
  - Low risk; behavior only changes for empty-property schemas.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): Unknown
- Observed divergence: Observed schemas are valid but treated as fatal during resume.
- Reason (if known): Strict guard intended to prevent empty schemas, but doesn’t account for observed mode.
- Alignment plan or decision needed: Permit empty-property schemas as dynamic.

## Acceptance Criteria

1. Resuming a run with an observed source schema succeeds.
2. Reconstructed schema allows arbitrary fields (extra allowed).
3. Unit test covers observed schema reconstruction.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/unit/engine/test_export.py -v`
- New tests required: yes, cover observed schema reconstruction.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: Unknown
