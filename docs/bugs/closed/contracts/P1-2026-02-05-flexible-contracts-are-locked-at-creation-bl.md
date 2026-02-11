# Bug Report: FLEXIBLE contracts are locked at creation, blocking infer-and-lock for extra fields

**Status: CLOSED**

## Status Update (2026-02-12)

- Classification: **Fixed**
- Resolution summary:
  - `create_contract_from_config` now locks only `fixed` mode, so FLEXIBLE starts unlocked for first-row infer-and-lock.
  - JSON and Azure Blob sources now lock pending contracts at end-of-load when no valid rows are seen, preserving consistent contract availability.
  - Regression tests now cover FLEXIBLE contract creation, first-row extra inference, and all-invalid-row fallback behavior.
- Key changes:
  - `src/elspeth/contracts/schema_contract_factory.py`
  - `src/elspeth/plugins/sources/json_source.py`
  - `src/elspeth/plugins/azure/blob_source.py`
  - `tests/unit/contracts/test_schema_contract_factory.py`
  - `tests/unit/contracts/test_contract_builder.py`
  - `tests/unit/plugins/sources/test_json_source.py`
  - `tests/unit/plugins/transforms/azure/test_blob_source.py`
  - `tests/integration/plugins/sources/test_contract.py`
- Verification:
  - `uv run pytest -q tests/unit/contracts/test_schema_contract_factory.py tests/unit/contracts/test_contract_builder.py tests/unit/plugins/sources/test_json_source.py tests/unit/plugins/transforms/azure/test_blob_source.py tests/integration/plugins/sources/test_contract.py`
  - `uv run ruff check src/elspeth/contracts/schema_contract_factory.py src/elspeth/plugins/sources/json_source.py src/elspeth/plugins/azure/blob_source.py tests/unit/contracts/test_schema_contract_factory.py tests/unit/contracts/test_contract_builder.py tests/unit/plugins/sources/test_json_source.py tests/unit/plugins/transforms/azure/test_blob_source.py tests/integration/plugins/sources/test_contract.py`
  - `uv run mypy src/elspeth/contracts/schema_contract_factory.py src/elspeth/plugins/sources/json_source.py src/elspeth/plugins/azure/blob_source.py`

## Summary

- `create_contract_from_config` locks FLEXIBLE schemas immediately, so extra fields are never inferred or type-validated on the first row as required by the schema contract design.

## Severity

- Severity: major
- Priority: P1

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

- Goal or task prompt: You are a static analysis agent doing a deep bug audit. Target file: /home/john/elspeth-rapid/src/elspeth/contracts/schema_contract_factory.py
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Build a `SchemaConfig` with `mode="flexible"` and a declared field (e.g., `["id: int"]`), then call `create_contract_from_config`.
2. Pass the resulting contract to `ContractBuilder.process_first_row()` with a first row containing an extra field (e.g., `{"id": 1, "extra": "x"}`).
3. Validate a second row where the extra field changes type (e.g., `{"id": 2, "extra": 3}`).

## Expected Behavior

- FLEXIBLE contracts start unlocked, infer extra fields on the first row, lock, and then enforce types for those inferred extras on subsequent rows.

## Actual Behavior

- FLEXIBLE contracts are created locked, so `ContractBuilder` skips inference and extras are never added or type-validated; type drift in extra fields goes undetected.

## Evidence

- `src/elspeth/contracts/schema_contract_factory.py:91-94` sets `locked = not config.is_observed`, which locks FLEXIBLE schemas at creation.
- `src/elspeth/contracts/contract_builder.py:51-98` returns early when `contract.locked` is True, preventing inference for FLEXIBLE.
- `src/elspeth/contracts/schema_contract.py:225-274` only validates fields that are in the contract; extra fields are only type-validated if they were inferred into the contract.
- `docs/plans/completed/2026-02-02-unified-schema-contracts-design.md:30-74` specifies FLEXIBLE extras are allowed and inferred/locked on the first row.

## Impact

- User-facing impact: Extra fields in FLEXIBLE schemas can silently change types without quarantine, violating schema expectations.
- Data integrity / security impact: Audit trail lacks inferred type/original-name metadata for extra fields, weakening traceability.
- Performance or cost impact: Unknown

## Root Cause Hypothesis

- The factory treats all explicit schemas as locked, but FLEXIBLE requires an unlocked contract so `ContractBuilder` can infer and lock extra fields on the first row.

## Proposed Fix

- Code changes (modules/files):
  - Update `src/elspeth/contracts/schema_contract_factory.py` to lock only FIXED schemas (e.g., `locked = config.mode == "fixed"`), leaving FLEXIBLE and OBSERVED unlocked for first-row inference.
- Config or schema changes: N/A
- Tests to add/update:
  - Add a test in `tests/contracts/test_schema_contract_factory.py` asserting FLEXIBLE contracts start unlocked.
  - Add or update a ContractBuilder test confirming extra-field inference and type enforcement in FLEXIBLE mode.
- Risks or migration steps:
  - Behavior change for FLEXIBLE schemas; aligns with documented contract semantics and may require updating tests that currently assume locked FLEXIBLE behavior.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `docs/plans/completed/2026-02-02-unified-schema-contracts-design.md:30-74`
- Observed divergence: FLEXIBLE contracts are locked at creation, so extra fields are not inferred or type-validated on first row.
- Reason (if known): Unknown
- Alignment plan or decision needed: Align factory locking behavior with FLEXIBLE infer-and-lock semantics.

## Acceptance Criteria

- FLEXIBLE contracts are created unlocked and lock after the first valid row.
- Extra fields in FLEXIBLE mode are inferred into the contract and type-validated on subsequent rows.
- Tests covering FLEXIBLE infer-and-lock behavior pass.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/contracts/test_schema_contract_factory.py tests/contracts/test_contract_builder.py`
- New tests required: yes, FLEXIBLE infer-and-lock coverage.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `docs/plans/completed/2026-02-02-unified-schema-contracts-design.md`
