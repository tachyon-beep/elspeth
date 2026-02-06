# Bug Report: Resume Fails for Observed Schemas Due to Empty `properties` Rejection

**Status: CLOSED (Fixed)**
**Closed Date:** 2026-02-06
**Fixed By:** Claude Opus 4.5

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

## Resolution

### Fix Applied

Modified `reconstruct_schema_from_json` in `src/elspeth/engine/orchestrator/export.py` (lines 196-212):

When `properties` is empty:
- If `additionalProperties` is `True`: Return a dynamic schema with `extra="allow"` (same as `_create_dynamic_schema` in schema_factory.py)
- If `additionalProperties` is missing or `False`: Raise error (genuinely malformed - a fixed schema with no fields)

This correctly handles observed/dynamic schemas which output:
```json
{
  "properties": {},
  "additionalProperties": true,
  "type": "object"
}
```

### Tests Added

Added `TestReconstructSchemaFromJson` class to `tests/engine/orchestrator/test_export.py` with 6 tests:
1. `test_observed_schema_empty_properties_with_additional` - Verifies empty properties with additionalProperties=true reconstructs
2. `test_observed_schema_validates_arbitrary_data` - Verifies reconstructed schema accepts any row data
3. `test_empty_properties_without_additional_raises` - Verifies empty properties without additionalProperties raises
4. `test_empty_properties_with_additional_false_raises` - Verifies empty properties with additionalProperties=false raises
5. `test_fixed_schema_with_fields` - Verifies normal fixed schemas still work
6. `test_missing_properties_key_raises` - Verifies missing properties key raises

### Acceptance Criteria Met

1. Resuming a run with an observed source schema succeeds (schema reconstructs to dynamic model)
2. Reconstructed schema allows arbitrary fields (`extra="allow"`)
3. Unit tests cover observed schema reconstruction (6 new tests, all passing)
