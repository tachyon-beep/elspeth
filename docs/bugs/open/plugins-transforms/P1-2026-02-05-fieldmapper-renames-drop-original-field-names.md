# Bug Report: FieldMapper Renames Drop Original Field Names in Output Contracts

## Summary

- FieldMapper uses `narrow_contract_to_output` without preserving original source header names for renamed fields, so the output contract loses original-name lineage and “headers: original” sinks emit renamed headers instead of source headers.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: 0282d1b441fe23c5aaee0de696917187e1ceeb9b / RC2.3-pipeline-row
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: CSV with normalized headers (e.g., `'Amount USD'` → `amount_usd`)

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `src/elspeth/plugins/transforms/field_mapper.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Configure a CSV source whose header normalizes from `'Amount USD'` to `amount_usd`.
2. Add a `field_mapper` transform with `mapping: { amount_usd: price }`.
3. Configure a CSV sink with `headers: original`.
4. Run the pipeline and inspect output headers.

## Expected Behavior

- Output header should remain the original source header (`'Amount USD'`) because “original” mode is defined as restoring source headers, and the audit contract should preserve source-origin names through renames.

## Actual Behavior

- Output header becomes `price` because the output contract treats the renamed field as a new inferred field with `original_name="price"`, losing the original source name.

## Evidence

- `src/elspeth/plugins/transforms/field_mapper.py:139-143` uses `narrow_contract_to_output` with only `output_row`, discarding rename metadata.
- `src/elspeth/contracts/contract_propagation.py:113-136` assigns `original_name=name` and `source="inferred"` for new fields, which is what the renamed field becomes.
- `src/elspeth/contracts/header_modes.py:1-6, 21-26` defines ORIGINAL mode as “restore original source header names”.
- `docs/plans/completed/2026-02-02-unified-schema-contracts-design.md:19-22` requires preserving original field names and full traceability of field mappings.

## Impact

- User-facing impact: Sinks configured with `headers: original` emit renamed headers instead of true source headers after a FieldMapper rename.
- Data integrity / security impact: Audit trail loses source-name lineage for renamed fields, violating traceability requirements.
- Performance or cost impact: None.

## Root Cause Hypothesis

- FieldMapper constructs its output contract by calling `narrow_contract_to_output` on the post-mapping row, which infers new fields without preserving original-name metadata from the input contract.

## Proposed Fix

- Code changes (modules/files): `src/elspeth/plugins/transforms/field_mapper.py` should construct output contracts with rename awareness by mapping `source -> target` using the input contract’s `FieldContract` (preserve `original_name`, `python_type`, `required`, `source` where the source field exists; only infer types for genuinely new fields such as extracted nested values).
- Config or schema changes: None.
- Tests to add/update: Add a contract propagation test in `tests/plugins/transforms/test_field_mapper.py` asserting that renamed fields keep original source names and that `headers: original` resolves to source headers after rename.
- Risks or migration steps: None; contract metadata changes only.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `docs/plans/completed/2026-02-02-unified-schema-contracts-design.md:19-22`
- Observed divergence: FieldMapper drops original-name lineage for renamed fields, breaking “preserve original names” and “traceability of field mappings”.
- Reason (if known): Contract narrowing logic is not rename-aware.
- Alignment plan or decision needed: Update FieldMapper to preserve original-name metadata for renamed fields and only infer for truly new fields.

## Acceptance Criteria

- Renamed fields keep the original source header name in `SchemaContract`.
- Sinks with `headers: original` emit original source headers even after a FieldMapper rename.
- Audit tooling shows preserved original-name lineage after rename.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/plugins/transforms/test_field_mapper.py`
- New tests required: yes, add contract original-name preservation test for FieldMapper renames.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `docs/plans/completed/2026-02-02-unified-schema-contracts-design.md`
