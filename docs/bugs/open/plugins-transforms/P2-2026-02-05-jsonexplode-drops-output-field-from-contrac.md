# Bug Report: JSONExplode Drops `output_field` From Contract for Object Elements, Breaking FIXED-Mode Downstream Access

## Summary

- JSONExplode emits object elements (dict/list) as `output_field` but builds its output contract via `narrow_contract_to_output`, which skips non-primitive types; in FIXED mode this omits `output_field` from the contract, so downstream `PipelineRow` access raises `KeyError` even though the field exists in data.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: 0282d1b441fe23c5aaee0de696917187e1ceeb9b / RC2.3-pipeline-row
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: JSONExplode with fixed schema (`items: any`) and array-of-object rows (see `examples/json_explode/settings.yaml`)

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `src/elspeth/plugins/transforms/json_explode.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Configure a pipeline with a fixed input schema declaring `items: any` and add `json_explode` (example in `examples/json_explode/settings.yaml:17-32`).
2. Process a row where the array contains objects, e.g., `{"order_id": 1, "items": [{"sku": "A1"}]}`.
3. In a downstream transform, construct `PipelineRow(result.rows[0], result.contract)` and access `row["item"]`.

## Expected Behavior

- The output contract includes `output_field` with a permissive type (e.g., `object` / `any`), so downstream access to `row["item"]` works even when elements are dict/list.

## Actual Behavior

- `output_field` is omitted from the contract because type inference skips non-primitive values; in FIXED mode, `PipelineRow.__getitem__` raises `KeyError` for `row["item"]` despite the field existing in the row data.

## Evidence

- JSONExplode explicitly documents object elements as the common case (`src/elspeth/plugins/transforms/json_explode.py:67-72`).
- Output contract is built via `narrow_contract_to_output` for both empty and non-empty arrays (`src/elspeth/plugins/transforms/json_explode.py:158-162`, `src/elspeth/plugins/transforms/json_explode.py:203-206`).
- `narrow_contract_to_output` skips fields when `normalize_type_for_contract` raises `TypeError` for non-primitive values (`src/elspeth/contracts/contract_propagation.py:113-127`).
- `normalize_type_for_contract` raises `TypeError` for dict/list types (`src/elspeth/contracts/type_normalization.py:80-87`).
- Example config uses fixed schema with `items: any`, implying object elements are expected (`examples/json_explode/settings.yaml:17-22`).

## Impact

- User-facing impact: Downstream transforms in FIXED mode cannot access `output_field` (`KeyError`), breaking common pipelines that explode arrays of objects.
- Data integrity / security impact: Output contracts do not reflect actual emitted fields, weakening audit contract guarantees.
- Performance or cost impact: Failures cause retries and manual debugging overhead.

## Root Cause Hypothesis

- JSONExplode relies on `narrow_contract_to_output` without compensating for complex element types, so when `output_field` values are dict/list, contract inference skips the field entirely.

## Proposed Fix

- Code changes (modules/files):
  - `src/elspeth/plugins/transforms/json_explode.py`: After `narrow_contract_to_output`, ensure `output_field` exists in the contract even when element types are complex by explicitly adding a `FieldContract` with `python_type=object` (the “any” type). Optionally do the same for `item_index` if `include_index=True` and it was skipped.
- Config or schema changes: None.
- Tests to add/update:
  - Add a test to `tests/plugins/transforms/test_json_explode.py` where `items` contains dicts and verify `result.contract` includes `output_field` and downstream `PipelineRow` access works in FIXED mode.
- Risks or migration steps:
  - Minimal; contract becomes more permissive for `output_field` when complex types are present, matching documented behavior.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): Unknown
- Observed divergence: Contract metadata omits a field that JSONExplode explicitly emits in common object-element cases.
- Reason (if known): Contract inference skips unsupported value types without JSONExplode-specific fallback.
- Alignment plan or decision needed: Ensure JSONExplode explicitly records `output_field` in its output contract as `any` when elements are non-primitive.

## Acceptance Criteria

- `output_field` appears in `TransformResult.contract` even when array elements are dict/list.
- Downstream `PipelineRow` access to `output_field` succeeds in FIXED mode.
- New test for dict/list elements passes.

## Tests

- Suggested tests to run: `python -m pytest tests/plugins/transforms/test_json_explode.py`
- New tests required: yes, add dict/list element contract coverage

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: Unknown
