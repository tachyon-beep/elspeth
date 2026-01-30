# Bug Report: Azure multi-query guarantees a non-existent base field and omits actual output mapping fields

## Summary

- `AzureMultiQueryLLMTransform` declares guaranteed fields using `get_llm_guaranteed_fields(spec.output_prefix)`, which guarantees a base `<prefix>` field that is never emitted while failing to guarantee the real `<prefix>_<suffix>` output fields, breaking DAG contract validation for downstream `required_input_fields`.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-01-30
- Related run/issue ID: N/A

## Environment

- Commit/branch: Unknown
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Unknown

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `src/elspeth/plugins/llm/azure_multi_query.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Configure `azure_multi_query_llm` with `output_mapping` (e.g., `score`, `rationale`) and a dynamic schema.
2. Add a downstream transform with `required_input_fields: ["cs1_crit1_score"]`.
3. Run `elspeth validate --settings <pipeline.yaml>` (or build the DAG).

## Expected Behavior

- DAG validation should accept the pipeline because the multi-query transform guarantees its output mapping fields (e.g., `cs1_crit1_score`).

## Actual Behavior

- DAG validation fails because the upstream transform does not guarantee the actual output mapping fields, and instead guarantees a base field (`cs1_crit1`) that is never produced.

## Evidence

- Output schema config derives guarantees from `get_llm_guaranteed_fields(spec.output_prefix)` instead of the actual output mapping fields. `src/elspeth/plugins/llm/azure_multi_query.py:154-170`
- The transform emits fields as `<prefix>_<suffix>` (e.g., `cs1_crit1_score`), never emitting the bare `<prefix>` field. `src/elspeth/plugins/llm/azure_multi_query.py:446-475`
- `get_llm_guaranteed_fields` explicitly includes the base field (`""` suffix), so `<prefix>` is guaranteed even though it is not emitted. `src/elspeth/plugins/llm/__init__.py:37-73`

## Impact

- User-facing impact: Pipelines that correctly declare `required_input_fields` for multi-query outputs fail validation even though the fields are produced at runtime.
- Data integrity / security impact: Contract guarantees become incorrect (phantom fields guaranteed; real fields omitted), undermining DAG contract checks.
- Performance or cost impact: None directly.

## Root Cause Hypothesis

- The guaranteed field computation reuses `get_llm_guaranteed_fields(spec.output_prefix)`, which assumes a single response field exists. In multi-query mode, outputs are only `<prefix>_<suffix>` fields plus metadata, so the base `<prefix>` guarantee is invalid and real outputs are omitted.

## Proposed Fix

- Code changes (modules/files):
  - Update guaranteed field computation in `src/elspeth/plugins/llm/azure_multi_query.py` to include all `<prefix>_<suffix>` output mapping fields and the metadata fields (`<prefix>_usage`, `<prefix>_model`), and remove the bare `<prefix>` guarantee.
- Config or schema changes: None.
- Tests to add/update:
  - Add a contract test asserting `_output_schema_config.guaranteed_fields` contains all output mapping fields and does **not** include the bare prefix for multi-query.
  - Add a DAG validation test that a downstream `required_input_fields` of an output mapping field passes.
- Risks or migration steps:
  - Low risk; only schema contract metadata changes. Ensure any documentation or expected guarantees align with multi-query output shape.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:432-452` (Schema Contracts / DAG Validation)
- Observed divergence: Multi-query outputs are not declared in guaranteed_fields, so DAG contract validation is inaccurate.
- Reason (if known): Reuse of single-field LLM guarantee helper in multi-query context.
- Alignment plan or decision needed: Adjust multi-query guarantee computation to match actual emitted fields.

## Acceptance Criteria

- `AzureMultiQueryLLMTransform._output_schema_config.guaranteed_fields` includes all `<prefix>_<suffix>` fields and metadata fields, and excludes the bare `<prefix>`.
- A pipeline with a downstream transform requiring an output mapping field validates successfully.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/contracts/transform_contracts/test_azure_multi_query_contract.py`
- New tests required: yes, add contract/DAG validation coverage for multi-query guaranteed fields.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md` Schema Contracts section
