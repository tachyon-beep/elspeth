## Summary

`get_run_contract()` claims integrity verification but ignores the persisted `schema_contract_hash` column, so DB-level hash mismatches are never detected.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/core/landscape/_run_recording.py`
- Line(s): 341-353
- Function/Method: `get_run_contract`

## Evidence

`begin_run()` and `update_run_contract()` both persist `schema_contract_hash` (`_run_recording.py:79-83`, `_run_recording.py:316-323`), and schema documents it as integrity material (`src/elspeth/core/landscape/schema.py:62`).

But `get_run_contract()` only selects `schema_contract_json` (`_run_recording.py:341`) and restores via:

- `ContractAuditRecord.from_json(...)`
- `audit_record.to_schema_contract()`

That path validates only the hash embedded inside JSON (`src/elspeth/contracts/contract_records.py:153-157`, `src/elspeth/contracts/contract_records.py:203-209`), not the DB column hash.

So a row where `schema_contract_json` is modified to a self-consistent (payload + embedded hash) value but `schema_contract_hash` differs is accepted silently.

## Root Cause Hypothesis

Integrity verification was implemented at the JSON-record layer, but retrieval code in `_run_recording.py` never cross-checks against the separately persisted hash column intended for verification.

## Suggested Fix

In `get_run_contract()`:

1. Select both `schema_contract_json` and `schema_contract_hash`.
2. Restore contract from JSON as today.
3. Recompute `version_hash()` from restored contract and compare to `schema_contract_hash`.
4. Raise `AuditIntegrityError` on mismatch (and on unexpected null hash when JSON exists).

## Impact

Audit-trail tampering/corruption detection is weakened. Resume and downstream analysis can consume an incorrect contract while the DB hash mismatch goes unnoticed.
