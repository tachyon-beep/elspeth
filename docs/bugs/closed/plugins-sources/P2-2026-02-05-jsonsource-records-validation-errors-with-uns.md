# Bug Report: JSONSource records validation errors with unsupported `schema_mode="structure"`

**Status: CLOSED**

## Status Update (2026-02-11)

- Classification: **Resolved**
- Resolution summary:
  - JSONSource now records `schema_mode="parse"` for `data_key` structural boundary errors.
  - Added a regression test that verifies the recorded schema mode is contract-valid.


## Summary

- JSONSource uses `schema_mode="structure"` for data_key structural errors, but audit contracts/documentation only allow `fixed`, `flexible`, `observed`, or `parse`, creating a schema-mode contract violation.

## Severity

- Severity: minor
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: 0282d1b441fe23c5aaee0de696917187e1ceeb9b on `RC2.3-pipeline-row`
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: JSON file with `data_key` configured but root is a list or missing key

## Agent Context (if relevant)

- Goal or task prompt: Static analysis agent doing a deep bug audit of `src/elspeth/plugins/sources/json_source.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Configure JSONSource with `format: json`, `data_key: "results"`, and `on_validation_failure: "quarantine"`.
2. Provide a JSON file where the root is a list or where `results` is missing.
3. Run `JSONSource.load(ctx)` with a Landscape-backed context and inspect validation error records.

## Expected Behavior

- Validation errors should be recorded with a `schema_mode` that matches the allowed contract values (`fixed`, `flexible`, `observed`, or `parse`).

## Actual Behavior

- Structural errors are recorded with `schema_mode="structure"`, which is not part of the documented/contracted set.

## Evidence

- `src/elspeth/plugins/sources/json_source.py:224-275` uses `schema_mode="structure"` when recording structural errors.
- `src/elspeth/contracts/plugin_context.py:364-383` documents allowed `schema_mode` values as `fixed`, `flexible`, `observed`, or `parse`.
- `src/elspeth/contracts/audit.py:462-476` documents `ValidationErrorRecord.schema_mode` with the same allowed set.

## Impact

- User-facing impact: Validation error analytics or UI filters that assume the documented schema_mode values may ignore or misclassify structural errors.
- Data integrity / security impact: Audit metadata violates the documented contract for validation error records.
- Performance or cost impact: None.

## Root Cause Hypothesis

- JSONSource introduced a custom `schema_mode="structure"` label without updating the contract or downstream expectations.

## Proposed Fix

- Code changes (modules/files): In `src/elspeth/plugins/sources/json_source.py`, replace `schema_mode="structure"` with an allowed value (likely `parse` for structural boundary failures or `self._schema_config.mode` for schema-context errors).
- Config or schema changes: None, unless the team decides to officially extend `schema_mode` to include `structure` across contracts and docs.
- Tests to add/update: Add or update JSONSource tests to assert recorded `schema_mode` is one of the allowed values on data_key structural errors.
- Risks or migration steps: If choosing to add a new schema_mode, update audit contracts, schema docs, and any analytics consumers.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `src/elspeth/contracts/plugin_context.py:364-383`, `src/elspeth/contracts/audit.py:473-478`.
- Observed divergence: JSONSource records `schema_mode="structure"` outside the documented contract.
- Reason (if known): Unknown.
- Alignment plan or decision needed: Decide whether to conform to existing allowed values or formally extend the schema_mode contract.

## Acceptance Criteria

- No validation error record is created with `schema_mode="structure"` from JSONSource structural errors.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/unit/plugins/sources/test_json_source.py -k "data_key_structural_error"`
- New tests required: yes, add assertion on schema_mode for structural errors

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `src/elspeth/contracts/audit.py`, `src/elspeth/contracts/plugin_context.py`

---

## Verification (2026-02-11)

- Reproduced prior failure:
  - `data_key` structural failures recorded `schema_mode="structure"` in validation error records.
- Post-fix behavior:
  - Structural failures now record `schema_mode="parse"` across all three branches (non-object root, missing key, non-list extracted payload).
- Tests executed:
  - `PYTHONPATH=src .venv/bin/python -m pytest -q tests/unit/plugins/sources/test_json_source.py -k "data_key_structural_error or data_key_on_list_root or data_key_missing_in_object or data_key_extracts_non_list"`
  - `PYTHONPATH=src .venv/bin/python -m pytest -q tests/unit/plugins/sources/test_json_source.py`
  - `.venv/bin/ruff check src/elspeth/plugins/sources/json_source.py tests/unit/plugins/sources/test_json_source.py`
