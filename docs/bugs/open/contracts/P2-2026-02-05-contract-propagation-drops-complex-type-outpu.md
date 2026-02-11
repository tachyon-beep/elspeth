# Bug Report: Contract propagation drops complex-type output fields, breaking downstream access

**Status: OPEN**

## Status Update (2026-02-11)

- Classification: **Still open**
- Verification summary:
  - Contract propagation still skips new fields when type normalization raises `TypeError` (for dict/list values).
  - Existing unit tests currently assert and preserve this skip behavior.
- Current evidence:
  - `src/elspeth/contracts/contract_propagation.py:47`
  - `src/elspeth/contracts/contract_propagation.py:113`
  - `tests/unit/contracts/test_contract_propagation.py:431`

## Summary

- New output fields with non-primitive values (dict/list) are silently skipped during contract propagation, so the output contract omits fields that actually exist in the data (e.g., JSONExplode `item`, LLM `{response_field}_usage`), which breaks downstream access in FIXED mode and undermines contract guarantees.

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
- Data set or fixture: JSONExplode with fixed schema and array-of-object rows; LLM response usage dicts

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `src/elspeth/contracts/contract_propagation.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Configure a pipeline with a fixed input schema and `json_explode`, and pass a row where the array contains objects, e.g., `{"id": 1, "items": [{"name": "a"}]}`.
2. Process the row and inspect `TransformResult.contract` or create `PipelineRow` from `result.row` and `result.contract`.
3. Attempt to access `row["item"]` in a downstream transform.

## Expected Behavior

- The output contract includes the new field (`item`) even when its value is a dict/list, using a permissive type (e.g., `object`) so downstream access works and contracts reflect actual output fields.

## Actual Behavior

- The contract propagation code skips the field entirely when type inference fails, so `item` (and LLM `_usage`) are missing from the contract; in FIXED mode, downstream access raises `KeyError` and contract guarantees are violated.

## Evidence

- `src/elspeth/contracts/contract_propagation.py:47` and `src/elspeth/contracts/contract_propagation.py:54` skip new fields when `normalize_type_for_contract` raises `TypeError`, with no fallback type.
- `src/elspeth/contracts/contract_propagation.py:113` and `src/elspeth/contracts/contract_propagation.py:117` skip new fields on `TypeError` in `narrow_contract_to_output`, meaning dict/list outputs are omitted from the contract.
- `src/elspeth/contracts/type_normalization.py:80` shows `normalize_type_for_contract` raises `TypeError` for unsupported types (e.g., dict/list), so complex outputs will be skipped.
- `src/elspeth/plugins/transforms/json_explode.py:67` shows JSONExplode commonly emits dict elements as `item`, which will be skipped from the contract under current logic.
- `src/elspeth/plugins/llm/base.py:349` sets `{response_field}_usage` to a dict, and `src/elspeth/plugins/llm/__init__.py:20` describes it as a guaranteed field, but it is omitted from contracts by the skip logic.

## Impact

- User-facing impact: Downstream transforms in FIXED mode cannot access emitted fields like `item` or `{response_field}_usage`, causing runtime `KeyError`s or blocked workflows.
- Data integrity / security impact: Output contracts become incomplete, violating contract guarantees and reducing audit trail fidelity (fields exist in data but are absent from contract metadata).
- Performance or cost impact: Indirect; failures trigger retries or manual debugging, increasing operational overhead.

## Root Cause Hypothesis

- Contract propagation treats unsupported value types as “skip this field” instead of recording them as permissive `object` types, so complex outputs disappear from the contract.

## Proposed Fix

- Code changes (modules/files): Update `src/elspeth/contracts/contract_propagation.py` to treat `TypeError` from `normalize_type_for_contract` as `python_type=object` (the allowed “any” type) rather than skipping; keep `ValueError` (NaN/Infinity) as a hard error or explicit quarantine path.
- Config or schema changes: None.
- Tests to add/update: Add contract propagation tests for JSONExplode with dict items and for LLM `_usage` ensuring the contract includes those fields with `python_type=object`.
- Risks or migration steps: Minimal; contracts become more permissive for complex fields, which is expected for “any”-typed outputs.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `docs/plans/completed/2026-02-02-unified-schema-contracts-design.md:19`
- Observed divergence: Contract propagation drops field metadata for complex outputs, failing the “preserve type information through the pipeline” goal.
- Reason (if known): Likely an intentional short-term workaround for non-primitive types, but it causes contract omissions.
- Alignment plan or decision needed: Use `object` as the inferred type for complex outputs so contracts retain field presence.

## Acceptance Criteria

- Output contracts include complex-type fields (dict/list) with `python_type=object`.
- Downstream access to these fields via `PipelineRow` works in FIXED mode.
- Tests cover JSONExplode dict items and LLM `_usage` contract propagation.

## Tests

- Suggested tests to run: `python -m pytest tests/plugins/transforms/test_field_mapper.py tests/plugins/transforms/test_json_explode.py tests/plugins/llm/test_*.py`
- New tests required: yes, add tests for contract propagation with dict/list outputs.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `docs/plans/completed/2026-02-02-unified-schema-contracts-design.md`
