# Bug Report: AzureLLMTransform output_schema omits LLM response fields it actually emits

## Summary

- AzureLLMTransform sets `output_schema` equal to `input_schema` but always appends LLM response/metadata fields to the output row, so declared schema does not match actual output and can cause schema compatibility validation failures downstream.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-01-25
- Related run/issue ID: N/A

## Environment

- Commit/branch: 8635789
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Any pipeline using `azure_llm` with a strict/free schema and a downstream transform/sink that requires the LLM response field.

## Agent Context (if relevant)

- Goal or task prompt: Deep static bug audit of `/home/john/elspeth-rapid/src/elspeth/plugins/llm/azure.py` with audit/contract checks.
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Configure `azure_llm` with a strict/free schema that defines only input fields (e.g., `text`) and omits the LLM response fields.
2. Add a downstream transform/sink whose input schema requires `llm_response` (or `response_field`).
3. Run `elspeth validate -s settings.yaml` (or any command that calls graph validation).

## Expected Behavior

- The LLM transform’s `output_schema` reflects the fields it adds (e.g., `llm_response`, usage, template hashes), so graph validation accepts downstream consumers expecting those fields.

## Actual Behavior

- Graph validation rejects the edge due to missing required fields because the producer’s `output_schema` does not include the LLM response fields.

## Evidence

- `src/elspeth/plugins/llm/azure.py:124` sets `self.output_schema = schema` identical to input schema.
- `src/elspeth/plugins/llm/azure.py:270` appends response and metadata fields to the output row (`response_field`, usage, template/lookup hashes, model).
- `src/elspeth/core/dag.py:667` enforces schema compatibility and errors on missing required fields.

## Impact

- User-facing impact: Pipelines with strict/free schemas and downstream dependencies on LLM response fields fail validation even though the transform emits those fields at runtime.
- Data integrity / security impact: Declared schema in audit metadata is inaccurate, undermining contract correctness for audit and compatibility checks.
- Performance or cost impact: None.

## Root Cause Hypothesis

- AzureLLMTransform assigns `output_schema` directly from the input schema and never augments it to reflect fields added in `process()`.

## Proposed Fix

- Code changes (modules/files):
  - In `src/elspeth/plugins/llm/azure.py`, build a separate output schema that extends the configured schema with the LLM response field and metadata fields (as optional fields), or explicitly enforce dynamic schema for output.
- Config or schema changes: If schema is not dynamic, merge in response/metadata fields with types (`str` or `any`) and optional defaults.
- Tests to add/update:
  - Add a unit test in `tests/plugins/llm/test_azure.py` verifying `output_schema` includes `response_field` (and metadata) even when input schema is strict.
  - Add a graph validation test in `tests/core/test_dag.py` showing a strict-schema pipeline with downstream `llm_response` passes.
- Risks or migration steps:
  - Existing configs may need to tolerate extra optional fields in output schema; ensure defaults are optional to avoid breaking strict schemas.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:56`
- Observed divergence: Output schema does not reflect actual output fields added by the transform.
- Reason (if known): Output schema is set equal to input schema without augmentation.
- Alignment plan or decision needed: Extend output schema to include LLM response/metadata fields or mandate dynamic output schema for LLM transforms.

## Acceptance Criteria

- `azure_llm` output schema includes response and metadata fields added in `process()`.
- ExecutionGraph schema compatibility validation succeeds for downstream transforms requiring LLM response fields.
- Tests cover the strict-schema scenario.

## Tests

- Suggested tests to run: `pytest tests/plugins/llm/test_azure.py`; `pytest tests/core/test_dag.py`
- New tests required: yes, output schema augmentation and graph validation coverage.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md`
