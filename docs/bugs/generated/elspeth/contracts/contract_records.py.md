# Bug Report: Missing Tier‑1 Validation of Audit Record Fields Allows Invalid Schema Modes

## Summary

- `ContractAuditRecord.from_json()` and `to_schema_contract()` accept unvalidated `mode` values from the audit trail, allowing corrupted or invalid modes (e.g., `"fixed"`) to bypass FIXED‑mode enforcement without crashing, violating Tier‑1 “crash on any anomaly.”

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-02-03
- Related run/issue ID: N/A

## Environment

- Commit/branch: Unknown
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Crafted audit record JSON with invalid `mode` value (e.g., `"fixed"`)

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `src/elspeth/contracts/contract_records.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Create a JSON string for `ContractAuditRecord` with `mode` set to `"fixed"` (lowercase) and a matching `version_hash` computed from a `SchemaContract(mode="fixed", ...)` instance.
2. Call `ContractAuditRecord.from_json(json_str)` and then `to_schema_contract()`.
3. Call `SchemaContract.validate()` on a row containing extra fields.

## Expected Behavior

- Restoring from audit JSON should raise immediately on invalid `mode` values (Tier‑1: crash on any anomaly). The contract should not be constructed.

## Actual Behavior

- The invalid `mode` value is accepted and propagated into `SchemaContract`. FIXED‑mode extra‑field checks are skipped because `self.mode == "FIXED"` is false, allowing extra fields through silently.

## Evidence

- `ContractAuditRecord.from_json()` accepts `mode` directly from JSON with no validation. `src/elspeth/contracts/contract_records.py:155-179`
- `ContractAuditRecord.to_schema_contract()` passes `mode=self.mode` directly into `SchemaContract` with no validation. `src/elspeth/contracts/contract_records.py:181-211`
- `SchemaContract.validate()` only enforces extra‑field rejection when `mode == "FIXED"`. Any other value silently disables the check. `src/elspeth/contracts/schema_contract.py:262-273`
- Tier‑1 policy requires crashing on invalid enum values from the audit trail. `CLAUDE.md:25-32`

## Impact

- User-facing impact: Resume/explain paths can accept invalid schema modes and mis-validate rows.
- Data integrity / security impact: Audit trail integrity is weakened; FIXED‑mode protections can be bypassed without detection.
- Performance or cost impact: None expected.

## Root Cause Hypothesis

- `ContractAuditRecord.from_json()` and `to_schema_contract()` do not validate `mode` (and related enum fields like `source`) against allowed literals, and `SchemaContract` does not enforce runtime validation either.

## Proposed Fix

- Code changes (modules/files): `src/elspeth/contracts/contract_records.py` add explicit validation that `mode` is one of `{"FIXED","FLEXIBLE","OBSERVED"}` before constructing `SchemaContract`; validate `source` is one of `{"declared","inferred"}` and `locked/required` are `bool`.
- Config or schema changes: None.
- Tests to add/update: Add unit tests for `ContractAuditRecord.from_json()`/`to_schema_contract()` rejecting invalid `mode` and `source` values.
- Risks or migration steps: None, except existing corrupted audit records will now raise (intended Tier‑1 behavior).

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:25-32` (Tier‑1 audit data must crash on invalid enum/type values).
- Observed divergence: Invalid `mode` values from the audit trail are accepted and used.
- Reason (if known): Missing explicit validation in audit record restoration.
- Alignment plan or decision needed: Add strict enum/type validation in `ContractAuditRecord` restoration path.

## Acceptance Criteria

- Restoring a contract audit record with invalid `mode` or `source` raises a `ValueError` (or equivalent) before constructing `SchemaContract`.
- FIXED‑mode enforcement cannot be bypassed by malformed audit records.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/unit/test_contract_records.py`
- New tests required: yes, add cases for invalid `mode` and `source` during `ContractAuditRecord.from_json()`/`to_schema_contract()`.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md` Tier‑1 trust model (lines 25‑32)
