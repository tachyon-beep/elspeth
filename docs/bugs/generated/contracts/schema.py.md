# Bug Report: Explicit Schema Contracts Allow Undefined Fields

## Summary

- Explicit (strict/free) schemas accept `guaranteed_fields`/`required_fields`/`audit_fields` that are not declared in `fields`, so invalid contract fields silently pass validation and influence DAG checks.

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
- Data set or fixture: Minimal schema config dict

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of /home/john/elspeth-rapid/src/elspeth/contracts/schema.py
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Call `SchemaConfig.from_dict({"mode": "strict", "fields": ["id: int"], "required_fields": ["amount"]})`.
2. Build a DAG where a downstream node requires `amount` or rely on guaranteed/required fields for validation.

## Expected Behavior

- `SchemaConfig.from_dict` rejects contract fields that are not declared in explicit schemas, failing fast with a clear `ValueError`.

## Actual Behavior

- `SchemaConfig.from_dict` accepts the config and returns a SchemaConfig; the invalid field propagates into DAG validation, allowing impossible or misleading contracts.

## Evidence

- `SchemaConfig.from_dict` parses `guaranteed_fields`/`required_fields`/`audit_fields` but never validates them against declared fields for explicit schemas. (`/home/john/elspeth-rapid/src/elspeth/contracts/schema.py:283-351`)
- `get_effective_guaranteed_fields` unions explicit `guaranteed_fields` with declared required fields, so invalid names become “guaranteed.” (`/home/john/elspeth-rapid/src/elspeth/contracts/schema.py:389-407`)
- DAG validation consumes these values via `_get_guaranteed_fields` and `_get_required_fields`, so typos or undefined fields affect edge validation. (`/home/john/elspeth-rapid/src/elspeth/core/dag.py:1129-1160`)

## Impact

- User-facing impact: Pipelines can pass DAG validation with impossible contracts, leading to runtime failures or confusing validation errors later.
- Data integrity / security impact: Audit trail claims guarantees for fields that are not actually defined in the schema, undermining traceability.
- Performance or cost impact: Wasted runs/retries due to avoidable configuration errors.

## Root Cause Hypothesis

- Missing consistency checks in `SchemaConfig.from_dict` for explicit schemas allow contract fields outside the declared field list (and potentially contradictory to optional/required declarations).

## Proposed Fix

- Code changes (modules/files):
  - Add validation in `/home/john/elspeth-rapid/src/elspeth/contracts/schema.py` after `parsed_fields` creation:
    - For explicit schemas, ensure `guaranteed_fields`, `required_fields`, and `audit_fields` are subsets of declared field names.
    - Optionally enforce `guaranteed_fields` ⊆ required declared fields to prevent guaranteeing optional fields.
- Config or schema changes: N/A
- Tests to add/update:
  - Add tests in `tests/contracts/test_schema_config.py` to assert `ValueError` when contract fields reference undeclared names in explicit schemas.
  - Add tests covering optional vs guaranteed conflicts if enforced.
- Risks or migration steps:
  - Existing configs with mismatched contract fields will start failing validation; this is a desired fail-fast change but may require config cleanup.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): CLAUDE.md – “Schema Contracts (DAG Validation)” (explicit schemas implicitly guarantee declared fields; contract fields are for dynamic schemas)
- Observed divergence: Explicit schemas can declare guarantees/requirements for fields not in the declared schema list.
- Reason (if known): Missing validation in `SchemaConfig.from_dict`.
- Alignment plan or decision needed: Enforce contract-field subset checks for explicit schemas.

## Acceptance Criteria

- `SchemaConfig.from_dict` raises `ValueError` when `guaranteed_fields`, `required_fields`, or `audit_fields` include undeclared fields in explicit schemas.
- DAG validation no longer treats undefined fields as guaranteed/required from explicit schemas.
- New tests in `tests/contracts/test_schema_config.py` pass.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/contracts/test_schema_config.py`
- New tests required: yes, explicit-schema contract-field validation cases

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: CLAUDE.md (“Schema Contracts (DAG Validation)”)
