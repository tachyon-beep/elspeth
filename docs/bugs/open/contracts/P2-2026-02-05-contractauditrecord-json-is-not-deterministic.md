# Bug Report: ContractAuditRecord JSON Is Not Deterministic After Contract Merges

**Status: OPEN**

## Status Update (2026-02-11)

- Classification: **Still open**
- Verification summary:
  - Contract audit serialization still preserves incoming field order and does not sort fields before emitting JSON.
  - Merge ordering can still originate from set-union iteration, so deterministic ordering is not guaranteed.
- Current evidence:
  - `src/elspeth/contracts/contract_records.py:115`
  - `src/elspeth/contracts/contract_records.py:139`
  - `src/elspeth/contracts/schema_contract.py:416`

## Summary

- `ContractAuditRecord.to_json()` claims deterministic serialization, but field ordering is inherited from `SchemaContract.fields`, which can be non-deterministic after merges, yielding different JSON strings for identical contracts.

## Severity

- Severity: minor
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: RC2.3-pipeline-row @ 1c70074ef3b71e4fe85d4f926e52afeca50197ab
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: In-memory SchemaContract merge (no external data)

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `src/elspeth/contracts/contract_records.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. In two separate Python processes with different `PYTHONHASHSEED` values, create two `SchemaContract` instances with overlapping fields, then call `SchemaContract.merge()` to produce a merged contract.
2. Build `ContractAuditRecord.from_contract(merged_contract)` and call `to_json()` in each process.
3. Compare the JSON strings; the `fields` array order differs even though the contract is semantically identical.

## Expected Behavior

- `ContractAuditRecord.to_json()` should emit the same canonical JSON for identical contracts regardless of field insertion order or hash seed.

## Actual Behavior

- The `fields` array order follows `SchemaContract.fields`, which is non-deterministic when built from set iteration in `SchemaContract.merge()`, leading to different JSON strings for the same contract.

## Evidence

- `ContractAuditRecord.from_contract()` preserves `contract.fields` order and `to_json()` serializes `[f.to_dict() for f in self.fields]` without ordering. `src/elspeth/contracts/contract_records.py#L118-L151`
- `SchemaContract.merge()` builds `all_names` from a set union and iterates it directly, then uses `tuple(merged_fields.values())`, which depends on that set iteration order. `src/elspeth/contracts/schema_contract.py#L424-L476`
- Design plan explicitly states contract audit JSON should be deterministic via canonical JSON. `docs/plans/completed/2026-02-03-phase5-audit-trail-integration.md#L566-L583`

## Impact

- User-facing impact: Audit records for identical contracts can differ between runs, making diffs and audits noisy or misleading.
- Data integrity / security impact: Violates the determinism guarantee for audit records, undermining reproducibility expectations.
- Performance or cost impact: None.

## Root Cause Hypothesis

- `ContractAuditRecord` does not impose a stable field ordering before serialization, and `SchemaContract.merge()` yields non-deterministic field order due to set iteration.

## Proposed Fix

- Code changes (modules/files):
  - `src/elspeth/contracts/contract_records.py`: Sort fields by `normalized_name` (or a deterministic key) in `from_contract()` or `to_json()` before serialization.
- Config or schema changes: None.
- Tests to add/update:
  - Add a test where two contracts with identical fields but different order produce identical `to_json()` output.
  - Add a test for merged contracts to ensure deterministic JSON across field order changes.
- Risks or migration steps:
  - Low risk; only affects serialization order in audit records.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `docs/plans/completed/2026-02-03-phase5-audit-trail-integration.md#L566-L583`
- Observed divergence: Deterministic serialization is claimed, but field ordering is not stabilized before JSON generation.
- Reason (if known): Field ordering is inherited from `SchemaContract.fields`, which can be non-deterministic after merges.
- Alignment plan or decision needed: Enforce stable ordering in `ContractAuditRecord` serialization path.

## Acceptance Criteria

- Identical contracts always serialize to identical JSON strings from `ContractAuditRecord.to_json()` regardless of field order or merge path.
- Tests covering differing field order pass.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/contracts/test_contract_records.py -v`
- New tests required: yes, add deterministic ordering tests for `ContractAuditRecord.to_json()`.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `docs/plans/completed/2026-02-03-phase5-audit-trail-integration.md`
