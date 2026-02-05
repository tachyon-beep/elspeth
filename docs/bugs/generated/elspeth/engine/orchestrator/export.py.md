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
---
# Bug Report: Array and Nested Object Schemas Lose Type Fidelity on Resume

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
---
# Bug Report: Export Context Omits Landscape Recorder, Breaking `restore_source_headers`

## Summary

- `export_landscape` builds a `PluginContext` with `landscape=None`. CSV/JSON sinks configured with `restore_source_headers=True` require `ctx.landscape` and will raise a `ValueError`, causing export to fail even though a `LandscapeDB` is available.

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
- Data set or fixture: Any run with `landscape.export.enabled: true` and export sink configured with `restore_source_headers: true`

## Agent Context (if relevant)

- Goal or task prompt: You are a static analysis agent doing a deep bug audit. Target file: `/home/john/elspeth-rapid/src/elspeth/engine/orchestrator/export.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Configure `landscape.export.enabled: true` and set export sink to `csv` or `json` with `restore_source_headers: true`.
2. Run a pipeline to completion and trigger export.
3. Observe export failure with a `ValueError` about missing Landscape in context.

## Expected Behavior

- Export should provide a `PluginContext` with `landscape` set so sinks can resolve headers.

## Actual Behavior

- Export constructs `PluginContext` with `landscape=None`, and sinks raise `ValueError`, failing the export.

## Evidence

- `src/elspeth/engine/orchestrator/export.py:83-85` sets `landscape=None` in `PluginContext`.
- `src/elspeth/plugins/sinks/json_sink.py:489-494` raises if `ctx.landscape` is `None` when `restore_source_headers=True`.
- `src/elspeth/plugins/sinks/csv_sink.py:556-561` has the same requirement.

## Impact

- User-facing impact: Export fails for common sink configurations that rely on header restoration.
- Data integrity / security impact: Audit trail export becomes unavailable for compliance workflows.
- Performance or cost impact: Operational overhead to re-run export with altered sink settings.

## Root Cause Hypothesis

- Export path does not supply a LandscapeRecorder to the sink context despite having access to `LandscapeDB`.

## Proposed Fix

- Code changes (modules/files):
  - `src/elspeth/engine/orchestrator/export.py`: Instantiate `LandscapeRecorder(db)` and pass it as `ctx.landscape` for export sink writes.
- Config or schema changes: None
- Tests to add/update:
  - Add a unit/integration test that exports with `restore_source_headers=True` and verifies no exception.
- Risks or migration steps:
  - Low risk; context only enriched for export.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): Unknown
- Observed divergence: Sinks expect `ctx.landscape` for header restoration, but export context omits it.
- Reason (if known): Export context set with minimal fields only.
- Alignment plan or decision needed: Ensure export contexts satisfy sink expectations.

## Acceptance Criteria

1. Export succeeds with `restore_source_headers=True` for CSV/JSON sinks.
2. No `ValueError` is raised due to missing `ctx.landscape`.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/unit/engine/test_export.py -v`
- New tests required: yes, export with header restoration.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: Unknown
