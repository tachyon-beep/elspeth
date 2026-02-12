# Bug Report: Azure Multi-Query Drops PipelineRow Dual-Name Resolution

**Status: CLOSED**

## Status Update (2026-02-11)

- Classification: **Still open**
- Verification summary:
  - Re-verified against current code on 2026-02-11; the behavior described in this ticket is still present.


## Summary

- `AzureMultiQueryLLMTransform` converts `PipelineRow` to a raw dict before template context building, which strips original field-name access and causes `KeyError` when configs use original CSV headers.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: 0282d1b4
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: CSV source with original header names referenced in `input_fields`

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `src/elspeth/plugins/llm/azure_multi_query.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Configure a CSV source with headers that require dual-name resolution (e.g., original header `"Patient Name"` normalized to `patient_name`).
2. Configure `azure_multi_query_llm` with `input_fields: ["'Patient Name'"]` (original header name).
3. Run the pipeline through the engine.

## Expected Behavior

- The transform should use `PipelineRow` for field access so original names resolve via `SchemaContract`, and queries should render successfully.

## Actual Behavior

- `KeyError` is raised during template context building because the transform passes a normalized-only dict to `QuerySpec.build_template_context`, which cannot resolve original field names. This crashes the transform instead of producing a row-level error.

## Evidence

- `src/elspeth/plugins/llm/azure_multi_query.py:645-655` converts `PipelineRow` to dict (`row.to_dict()`) and passes it into `_process_single_row_internal`, discarding dual-name resolution.
- `src/elspeth/plugins/llm/azure_multi_query.py:374-375` passes that dict into `QuerySpec.build_template_context`.
- `src/elspeth/plugins/llm/multi_query.py:96-115` checks `if field_name not in row` and then `row[field_name]`, which fails for original names when `row` is a plain dict.
- `src/elspeth/contracts/schema_contract.py:518-537` documents dual-name access in `PipelineRow.__getitem__`, which is bypassed by `to_dict()`.
- `src/elspeth/contracts/schema_contract.py:590-596` shows `to_dict()` returns normalized keys only.

## Impact

- User-facing impact: Pipelines that use original header names in `input_fields` fail at runtime, despite PipelineRow’s dual-name access contract.
- Data integrity / security impact: Row processing crashes and rows are not processed; audit trail records a failed node state rather than a structured transform error.
- Performance or cost impact: None beyond failed runs and retried executions.

## Root Cause Hypothesis

- The transform converts `PipelineRow` to a raw dict too early, which removes the contract-based dual-name resolution required for original field name access during template rendering.

## Proposed Fix

- Code changes (modules/files):
  - `src/elspeth/plugins/llm/azure_multi_query.py`: Pass `PipelineRow` through `_process_row` → `_process_single_row_internal` → `_process_single_query` (or at minimum, pass `PipelineRow` into `QuerySpec.build_template_context`). Only call `to_dict()` when constructing the final output dict.
- Config or schema changes: None.
- Tests to add/update:
  - Add a plugin test that uses `PipelineRow` with an original header name in `input_fields` and asserts the query renders successfully.
- Risks or migration steps:
  - Low risk; aligns with PipelineRow migration expectations and preserves existing normalized-name behavior.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `docs/plans/2026-02-03-pipelinerow-migration.md:909-934` (LLM plugins should operate on `PipelineRow` for dual-name access).
- Observed divergence: Transform uses `row.to_dict()` before field access, bypassing PipelineRow’s dual-name resolution.
- Reason (if known): Likely leftover from pre-migration dict-based implementation.
- Alignment plan or decision needed: Update azure multi-query processing path to operate on `PipelineRow` until output serialization.

## Acceptance Criteria

- Configs using original field names in `input_fields` execute without `KeyError`.
- `AzureMultiQueryLLMTransform` uses `PipelineRow` for template context building, preserving dual-name access.
- Added test passes and existing LLM plugin tests remain green.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/plugins/llm/test_azure_multi_query.py`
- New tests required: yes, add a case using original header names in `input_fields`.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `docs/plans/2026-02-03-pipelinerow-migration.md`

## Resolution (2026-02-12)

- Status: CLOSED
- Fixed by commit: `ca932d66`
- Fix summary: Fix multi-query dual-name resolution for PipelineRow inputs
- Ticket moved from `docs/bugs/open/` to `docs/bugs/closed/` on 2026-02-12.

