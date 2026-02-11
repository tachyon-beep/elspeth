# Bug Report: BaseLLMTransform Output Contract Omits `_usage` Metadata, Violating Guaranteed Fields

**Status: OPEN**

## Status Update (2026-02-11)

- Classification: **Still open**
- Verification summary:
  - Re-verified against current code on 2026-02-11; the behavior described in this ticket is still present.


## Summary

- `BaseLLMTransform` adds `<response_field>_usage` to output but uses `propagate_contract()`, which skips dict types, so the usage field is missing from the output `SchemaContract` despite being documented as a guaranteed field.

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
- Data set or fixture: Unknown

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit for `/home/john/elspeth-rapid/src/elspeth/plugins/llm/base.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Use a `BaseLLMTransform` subclass with a FIXED schema and default `response_field`.
2. Process a row to produce output with `<response_field>_usage` set (dict).
3. In a downstream transform or template, access `row["<response_field>_usage"]`.

## Expected Behavior

- The output contract should include `<response_field>_usage` (type `any`/`object`), and downstream access via `PipelineRow` should succeed.

## Actual Behavior

- `<response_field>_usage` is absent from the contract, so `PipelineRow` access raises `KeyError` in FIXED mode, despite the field being documented as guaranteed.

## Evidence

- Base LLM output adds usage and then calls `propagate_contract()` in `src/elspeth/plugins/llm/base.py:345-364`.
- `propagate_contract()` explicitly skips non-primitive types (dict/list) in `src/elspeth/contracts/contract_propagation.py:47-57`.
- `normalize_type_for_contract()` raises `TypeError` for dict types in `src/elspeth/contracts/type_normalization.py:80-88`, triggering the skip.
- LLM usage is documented as a guaranteed field in `src/elspeth/plugins/llm/__init__.py:20-43`.

## Impact

- User-facing impact: Downstream transforms/templates cannot access LLM usage metadata in FIXED mode, causing `TemplateError` and row failures.
- Data integrity / security impact: Contract guarantees are violated, undermining schema trust and auditability.
- Performance or cost impact: Additional error handling or reruns due to avoidable contract mismatches.

## Root Cause Hypothesis

- `BaseLLMTransform` relies on `propagate_contract()` for new fields, but that helper intentionally skips dict types, so `_usage` is omitted from the contract.

## Proposed Fix

- Code changes (modules/files):
  - In `src/elspeth/plugins/llm/base.py`, explicitly add a `FieldContract` for `<response_field>_usage` (and any other non-primitive metadata) with `python_type=object` when building `output_contract`.
- Config or schema changes: None.
- Tests to add/update:
  - Add a test ensuring `BaseLLMTransform` output contracts include `<response_field>_usage` and allow access via `PipelineRow` in FIXED mode.
- Risks or migration steps:
  - None beyond updating contract generation logic.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `src/elspeth/plugins/llm/__init__.py:20-43`
- Observed divergence: The documented guaranteed `_usage` field is not present in the runtime contract.
- Reason (if known): Contract propagation skips dict types and `BaseLLMTransform` does not compensate.
- Alignment plan or decision needed: Ensure LLM guaranteed metadata fields are always represented in the contract.

## Acceptance Criteria

- `BaseLLMTransform` output contracts include `<response_field>_usage` with a permissive type.
- Downstream access to `<response_field>_usage` succeeds in FIXED schemas.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/ -k llm`
- New tests required: yes, contract propagation test covering `_usage`.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `src/elspeth/plugins/llm/__init__.py`
