# Bug Report: BaseLLMTransform output omits model metadata

## Summary

- BaseLLMTransform builds output rows without adding the actual model used (`<response_field>_model`), so subclasses lose model attribution in row data even though the audited client returns it.

## Severity

- Severity: minor
- Priority: P3

## Reporter

- Name or handle: Codex
- Date: 2026-01-25
- Related run/issue ID: N/A

## Environment

- Commit/branch: 86357898ee109a1dbb8d60f3dc687983fa22c1f0 (fix/rc1-bug-burndown-session-4)
- OS: Unknown
- Python version: Unknown
- Config profile / env vars: N/A
- Data set or fixture: Unknown

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of /home/john/elspeth-rapid/src/elspeth/plugins/llm/base.py
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Create a BaseLLMTransform subclass (as in `tests/plugins/llm/test_base.py`) and stub `chat_completion()` to return `LLMResponse(model="gpt-4", ...)`.
2. Call `process()` and inspect the returned row fields.

## Expected Behavior

- Output row includes `<response_field>_model` with the actual model used (e.g., `llm_response_model`).

## Actual Behavior

- Output row lacks `<response_field>_model`.

## Evidence

- `src/elspeth/plugins/llm/base.py:256` builds the output row and adds response/usage plus template/lookup metadata without adding a model field.
- `src/elspeth/plugins/clients/llm.py:36` defines `LLMResponse.model`, so the model is available to BaseLLMTransform.
- `src/elspeth/plugins/llm/openrouter.py:299` shows other LLM transforms include `<response_field>_model` in their outputs.

## Impact

- User-facing impact: Downstream logic cannot access which model actually produced the response when using BaseLLMTransform subclasses.
- Data integrity / security impact: Row-level audit metadata is incomplete compared to other LLM transforms.
- Performance or cost impact: None.

## Root Cause Hypothesis

- BaseLLMTransform’s output assembly never copies `response.model` into the row.

## Proposed Fix

- Code changes (modules/files):
  - Add `output[f"{self._response_field}_model"] = response.model` in `src/elspeth/plugins/llm/base.py`.
  - Update `tests/plugins/llm/test_base.py` to assert the model field is present.
- Config or schema changes: None (unless strict schemas are later used to validate this field).
- Tests to add/update:
  - Extend the existing success-path test in `tests/plugins/llm/test_base.py` to assert `<response_field>_model`.
- Risks or migration steps:
  - Adds a new output field; strict downstream schemas may need to include it if they validate output rows.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): Unknown
- Observed divergence: BaseLLMTransform output lacks model metadata while other LLM transforms include it.
- Reason (if known): Unknown
- Alignment plan or decision needed: Add model metadata to BaseLLMTransform output for parity.

## Acceptance Criteria

- BaseLLMTransform outputs include `<response_field>_model` populated from `LLMResponse.model`.
- Tests cover the model field in BaseLLMTransform output.

## Tests

- Suggested tests to run: `pytest tests/plugins/llm/test_base.py`
- New tests required: yes, add assertions for `<response_field>_model` in `tests/plugins/llm/test_base.py`

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: Unknown
---
# Bug Report: BaseLLMTransform output_schema does not include response fields

## Summary

- BaseLLMTransform sets `output_schema` equal to `input_schema` even though it appends LLM response and audit fields, preventing strict downstream schemas from requiring those fields and causing edge-compatibility failures.

## Severity

- Severity: minor
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-01-25
- Related run/issue ID: N/A

## Environment

- Commit/branch: 86357898ee109a1dbb8d60f3dc687983fa22c1f0 (fix/rc1-bug-burndown-session-4)
- OS: Unknown
- Python version: Unknown
- Config profile / env vars: N/A
- Data set or fixture: Unknown

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of /home/john/elspeth-rapid/src/elspeth/plugins/llm/base.py
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Configure a BaseLLMTransform subclass with a strict schema containing only the input field(s) (e.g., `text`).
2. Configure a downstream transform/sink that requires `llm_response` and validate the DAG; compatibility fails because the producer schema doesn’t include `llm_response`.

## Expected Behavior

- BaseLLMTransform output_schema reflects the additional response/audit fields so downstream schemas can require them without breaking upstream compatibility.

## Actual Behavior

- `output_schema` equals `input_schema`, so new fields are invisible to DAG validation and required response fields cannot be expressed.

## Evidence

- `src/elspeth/plugins/llm/base.py:170` creates a single schema from config and assigns it to both `input_schema` and `output_schema`.
- `src/elspeth/plugins/llm/base.py:256` adds `response_field`, usage, and template/lookup metadata fields to output rows.
- `src/elspeth/core/dag.py:846` uses `output_schema` to validate required field compatibility, so missing response fields break downstream validation.

## Impact

- User-facing impact: Pipelines with strict schemas cannot declare LLM response fields as required without breaking upstream compatibility; users are forced to use dynamic schemas or optional fields.
- Data integrity / security impact: Schema contracts no longer reflect actual output rows for BaseLLMTransform subclasses.
- Performance or cost impact: None.

## Root Cause Hypothesis

- BaseLLMTransform reuses the input schema for output without extending it to include generated response/audit fields.

## Proposed Fix

- Code changes (modules/files):
  - Build a distinct output schema in `src/elspeth/plugins/llm/base.py` that merges input fields with LLM output metadata fields (response, usage, template hashes, sources, and model).
  - Alternatively, set output_schema to dynamic if strict output typing isn’t available.
- Config or schema changes:
  - Consider allowing an explicit output schema config for LLM transforms or auto-adding response fields as optional.
- Tests to add/update:
  - Add DAG compatibility tests (e.g., in `tests/core/test_edge_validation.py`) covering LLM output fields required downstream.
  - Add BaseLLMTransform tests to ensure output_schema includes response fields when configured.
- Risks or migration steps:
  - Changing output_schema may require updating existing pipeline schemas that rely on strict mode.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `docs/contracts/plugin-protocol.md:336`
- Observed divergence: BaseLLMTransform output schema does not describe the actual outgoing row shape.
- Reason (if known): Single schema_config is reused for both input and output.
- Alignment plan or decision needed: Define output schema to include generated LLM fields or provide separate output schema configuration.

## Acceptance Criteria

- Downstream schemas can require `llm_response` (and related metadata) without breaking the upstream edge into BaseLLMTransform.
- BaseLLMTransform output_schema accurately reflects the fields it adds.

## Tests

- Suggested tests to run: `pytest tests/core/test_edge_validation.py` and `pytest tests/plugins/llm/test_base.py`
- New tests required: yes, add DAG compatibility coverage for LLM response fields

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `docs/contracts/plugin-protocol.md:336`
