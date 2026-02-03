# Bug Report: propagate_contract Silently Drops Non-Primitive Output Fields

## Summary

- Non-primitive transform outputs (dict/list) are silently skipped, so the schema contract omits fields that exist in output data.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-02-03
- Related run/issue ID: N/A

## Environment

- Commit/branch: RC2.3-pipeline-row (3aa2fa93d8ebd2650c7f3de23b318b60498cd81c)
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Synthetic output row containing a dict field (e.g., LLM `*_usage`)

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `src/elspeth/contracts/contract_propagation.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Create an input `SchemaContract` with one field (e.g., `id: int`).
2. Call `propagate_contract()` with `output_row={"id": 1, "response_usage": {"prompt_tokens": 1}}`.
3. Observe the returned contract does not include `response_usage`.
4. Create `PipelineRow(output_row, output_contract)` and attempt `row["response_usage"]`.

## Expected Behavior

- The output contract should include `response_usage` (preferably as `python_type=object` “any”), or the transform should fail loudly if unsupported types are not allowed.

## Actual Behavior

- The field is skipped and omitted from the contract, making it inaccessible via `PipelineRow` and untracked by contract metadata.

## Evidence

- `src/elspeth/contracts/contract_propagation.py:43-53` skips unsupported types and continues, explicitly noting the field “will still exist in the data, just not tracked in contract.”
- `src/elspeth/contracts/schema_contract.py:518-581` shows `PipelineRow` access is contract-gated; fields not in the contract are inaccessible even if present in data.
- `src/elspeth/plugins/llm/base.py:345-364` adds `*_usage` (likely dict) to output and then calls `propagate_contract`, triggering the skip.

## Impact

- User-facing impact: Downstream transforms cannot access fields like `*_usage` via `PipelineRow` even though they exist in output rows.
- Data integrity / security impact: Contract metadata does not reflect actual output fields, undermining auditability and the “no inference” audit principle.
- Performance or cost impact: None identified.

## Root Cause Hypothesis

- `propagate_contract()` catches `TypeError` from `normalize_type_for_contract()` and silently skips the new field instead of recording it as `object` (any) or raising a contract violation.

## Proposed Fix

- Code changes (modules/files): Update `src/elspeth/contracts/contract_propagation.py` to include unsupported-type fields with `python_type=object` (any) or explicitly raise a contract violation instead of skipping.
- Config or schema changes: N/A
- Tests to add/update: Update `tests/contracts/test_contract_propagation.py` to expect non-primitive fields to be included as `object` (or to expect a hard failure if that policy is chosen).
- Risks or migration steps: If changing to include `object`, downstream consumers must handle “any” types; if changing to raise, LLM transforms may need explicit output schemas for these fields.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md#L11-L19`
- Observed divergence: Fields that exist in output are not recorded in the contract, violating “No inference - if it’s not recorded, it didn’t happen.”
- Reason (if known): Unknown
- Alignment plan or decision needed: Decide whether to represent non-primitive output fields as `object` in contracts or to hard-fail when transforms emit unsupported types.

## Acceptance Criteria

- `propagate_contract()` records non-primitive output fields (as `object`) or fails explicitly; contract metadata matches output rows.
- `PipelineRow` can access fields like `response_usage` when they exist in output data.
- Updated tests pass.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/contracts/test_contract_propagation.py -v`
- New tests required: yes, adjust non-primitive handling expectations.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md#L11-L19`
---
# Bug Report: merge_contract_with_output Drops Input-Only Fields

## Summary

- `merge_contract_with_output()` only iterates over output schema fields, dropping input-only fields from the merged contract.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-03
- Related run/issue ID: N/A

## Environment

- Commit/branch: RC2.3-pipeline-row (3aa2fa93d8ebd2650c7f3de23b318b60498cd81c)
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Synthetic contracts with input-only fields

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `src/elspeth/contracts/contract_propagation.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Create `input_contract` with fields `{"id", "name"}`.
2. Create `output_schema_contract` with only `{"id"}`.
3. Call `merge_contract_with_output(input_contract, output_schema_contract)`.
4. Observe the merged contract lacks the `name` field.

## Expected Behavior

- The merged contract should preserve input fields (including original names) while applying output schema guarantees, resulting in a union of fields.

## Actual Behavior

- The merged contract contains only fields present in `output_schema_contract`, dropping input-only fields entirely.

## Evidence

- `src/elspeth/contracts/contract_propagation.py:99-114` builds `merged_fields` solely by iterating `output_schema_contract.fields`, never incorporating input-only fields.
- `src/elspeth/contracts/contract_propagation.py:80-85` states the goal is to “preserve original names while adding any new guaranteed fields.”
- `src/elspeth/contracts/schema_contract.py:518-581` shows that missing fields in the contract become inaccessible via `PipelineRow`.

## Impact

- User-facing impact: Pass-through fields not declared in output schema disappear from the contract, breaking downstream access and name resolution.
- Data integrity / security impact: Contract no longer reflects actual row content, undermining audit traceability.
- Performance or cost impact: None identified.

## Root Cause Hypothesis

- The merge logic only uses `output_schema_contract.fields` and omits the union with `input_contract.fields`.

## Proposed Fix

- Code changes (modules/files): Update `src/elspeth/contracts/contract_propagation.py` to merge the union of input and output fields, preserving input-only fields and applying output schema requirements where overlapping.
- Config or schema changes: N/A
- Tests to add/update: Add a test case in `tests/contracts/test_contract_propagation.py` where input has extra fields not in output schema and assert they are preserved.
- Risks or migration steps: Ensure deterministic ordering of merged fields to avoid test flakes or changes in serialized contract order.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `src/elspeth/contracts/contract_propagation.py#L80-L85`
- Observed divergence: The implementation does not preserve input fields as described, causing contract shrinkage.
- Reason (if known): Unknown
- Alignment plan or decision needed: Define and enforce a union-based merge policy for input and output schema contracts.

## Acceptance Criteria

- Merged contract includes all input fields plus output schema guarantees.
- Downstream `PipelineRow` access for pass-through fields works after merge.
- Added tests pass.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/contracts/test_contract_propagation.py -v`
- New tests required: yes, add union-preservation test.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `src/elspeth/contracts/contract_propagation.py#L80-L85`
