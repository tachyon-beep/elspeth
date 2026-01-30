# Bug Report: BaseLLMTransform output_schema omits LLM-added fields, breaking schema contract

## Summary

- BaseLLMTransform builds `output_schema` from the input schema config and then adds LLM-specific fields at runtime, so the declared output schema does not match actual output rows.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-01-30
- Related run/issue ID: N/A

## Environment

- Commit/branch: 290716a2563735271d162f1fac7d40a7690e6ed6
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: synthetic row with explicit schema (strict/free) and default `response_field`

## Agent Context (if relevant)

- Goal or task prompt: static analysis agent doing deep bug audit for `/home/john/elspeth-rapid/src/elspeth/plugins/llm/base.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Implement a minimal `BaseLLMTransform` subclass with an explicit schema (mode `strict` or `free`) that declares only input fields (e.g., `id`, `text`).
2. Run `process()` on a row and observe the output includes LLM fields (e.g., `llm_response`, `llm_response_model`, `llm_response_usage`) that are not part of `output_schema`. Validate output with `output_schema.model_validate(...)` (or observe DAG schema checks/coalesce compatibility).

## Expected Behavior

- `output_schema` should include LLM-added fields (response content, model, usage, audit metadata), or otherwise be dynamic so output rows conform to the declared schema.

## Actual Behavior

- `output_schema` is identical to the input schema, while `process()` always injects LLM fields, producing rows that violate the declared output schema.

## Evidence

- BaseLLMTransform sets `input_schema` and `output_schema` to the same schema derived from config (no LLM fields): `/home/john/elspeth-rapid/src/elspeth/plugins/llm/base.py:223-233`.
- It separately computes `_output_schema_config` with LLM guaranteed/audit fields but does not regenerate `output_schema` from it: `/home/john/elspeth-rapid/src/elspeth/plugins/llm/base.py:234-249`.
- `process()` always adds LLM fields to the output row: `/home/john/elspeth-rapid/src/elspeth/plugins/llm/base.py:329-341`.
- ExecutionGraph treats `output_schema` as the runtime validation schema: `/home/john/elspeth-rapid/src/elspeth/core/dag.py:27-34`.

## Impact

- User-facing impact: explicit schemas (strict/free) can silently drift; downstream expectations based on schema may be incorrect.
- Data integrity / security impact: output rows no longer conform to declared schema; auditability contracts are weakened.
- Performance or cost impact: none.

## Root Cause Hypothesis

- `BaseLLMTransform` updates `_output_schema_config` with LLM metadata fields but never regenerates `output_schema`, leaving it equal to the input schema even though output rows always include additional LLM fields.

## Proposed Fix

- Code changes (modules/files):
  - Update `/home/john/elspeth-rapid/src/elspeth/plugins/llm/base.py` to build a distinct `output_schema` that includes LLM fields (response content, usage, model, and audit metadata). For explicit schemas, extend `schema_config.fields` with appropriate `FieldDefinition`s (e.g., `str`/`any`, optional where appropriate) before calling `create_schema_from_config`.
- Config or schema changes: None (unless you choose to enforce a minimum schema extension for LLM fields in config parsing).
- Tests to add/update:
  - Unit test for `BaseLLMTransform` with explicit schema to assert `output_schema` accepts LLM fields and rejects unrelated extras.
  - Integration test for branch coalesce compatibility where one branch includes a BaseLLMTransform and the other does not (should fail if schemas differ).
- Risks or migration steps:
  - Existing pipelines with explicit schemas may start validating correctly (potentially exposing previously hidden mismatches).

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `/home/john/elspeth-rapid/src/elspeth/core/dag.py:27-34` (output_schema used for runtime validation)
- Observed divergence: BaseLLMTransform’s `output_schema` does not reflect actual output fields added by the transform.
- Reason (if known): `_output_schema_config` is computed but not used to regenerate `output_schema`.
- Alignment plan or decision needed: Update BaseLLMTransform to generate an output schema that matches emitted fields.

## Acceptance Criteria

- `output_schema` includes all LLM-added fields and `output_schema.model_validate(output_row)` succeeds for valid transform outputs.
- DAG/coalesce compatibility checks reflect the presence of LLM fields when a branch includes a BaseLLMTransform.

## Tests

- Suggested tests to run: `./.venv/bin/python -m pytest tests/unit/` (or targeted tests for LLM/base schema behavior)
- New tests required: yes, BaseLLMTransform explicit-schema coverage and branch compatibility validation.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `/home/john/elspeth-rapid/CLAUDE.md#L432` (Schema Contracts section)
