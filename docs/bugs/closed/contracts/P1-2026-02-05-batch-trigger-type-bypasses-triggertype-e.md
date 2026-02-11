# Bug Report: Batch `trigger_type` Bypasses `TriggerType` Enum Validation

## Summary

- `Batch.trigger_type` is declared as `str | None` and never validated, so invalid trigger types can be loaded from the audit DB without crashing, violating Tier 1 audit integrity.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: `e0060836d4bb129f1a37656d85e548ae81db8887` on `RC2.3-pipeline-row`
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: N/A (contract-only)

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `src/elspeth/contracts/audit.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Instantiate `Batch` with `trigger_type="not_a_trigger"` (or stub a DB row with that value and pass it through `BatchRepository.load`).
2. Observe that no exception is raised and the invalid value is accepted.

## Expected Behavior

- Invalid `trigger_type` values should crash immediately (TypeError/ValueError), and the field should be typed as `TriggerType | None`.

## Actual Behavior

- Any string is accepted for `trigger_type`, allowing invalid values to pass silently into the audit model.

## Evidence

- `Batch.trigger_type` is typed as `str | None` with no validation; only `status` is validated. `src/elspeth/contracts/audit.py:330`, `src/elspeth/contracts/audit.py:343`, `src/elspeth/contracts/audit.py:347`
- `BatchRepository.load` passes `row.trigger_type` through without conversion or validation. `src/elspeth/core/landscape/repositories.py:250`, `src/elspeth/core/landscape/repositories.py:260`
- `TriggerType` enum exists and is defined for `batches.trigger_type`. `src/elspeth/contracts/enums.py:60`

## Impact

- User-facing impact: Audit exports may contain invalid trigger types, confusing analysts or tooling.
- Data integrity / security impact: Violates Tier 1 rule (“invalid enum value = crash”), allowing silent corruption of audit trail.
- Performance or cost impact: None.

## Root Cause Hypothesis

- The audit contract defines `trigger_type` as a raw string instead of `TriggerType`, and no validation is performed on load.

## Proposed Fix

- Code changes (modules/files): Update `src/elspeth/contracts/audit.py:343` to use `TriggerType | None` and validate in `__post_init__`; update `src/elspeth/core/landscape/repositories.py:260` to convert `row.trigger_type` to `TriggerType` when not `None`.
- Config or schema changes: None.
- Tests to add/update: Adjust `tests/engine/test_aggregation_audit.py` to expect enums (or `.value` only in serialization) and add a test asserting invalid trigger types raise on load.
- Risks or migration steps: Update any serialization/exporters to emit `trigger_type.value` if they currently assume a string.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:25`
- Observed divergence: Audit data with invalid enum values does not crash immediately.
- Reason (if known): Contract uses `str` instead of enum and omits validation.
- Alignment plan or decision needed: Enforce `TriggerType` enum in audit contracts and repository conversions.

## Acceptance Criteria

- Loading or constructing a `Batch` with an invalid `trigger_type` raises, and valid values round-trip as `TriggerType`.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/engine/test_aggregation_audit.py -k trigger_type`
- New tests required: yes, add invalid trigger type validation test.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md:25`

## Closure Update (2026-02-11)

- Status: Closed after enforcing strict `TriggerType` enum handling in the Batch audit contract and repository load path.
- Fix summary:
  - Updated `Batch.trigger_type` from `str | None` to `TriggerType | None`.
  - Added Tier-1 enum validation in `Batch.__post_init__`.
  - Updated `BatchRepository.load()` to convert DB strings via `TriggerType(...)` (or `None`).
  - Added/updated tests for valid enum behavior and invalid trigger type rejection.
- Verification:
  - Direct repro now fails fast:
    - constructing `Batch(..., trigger_type="not_a_trigger")` raises `TypeError`.
  - Targeted tests passing:
    - `uv run pytest -q tests/unit/contracts/test_audit.py`
    - `uv run pytest -q tests/unit/core/landscape/test_repositories.py`
    - `uv run pytest -q tests/unit/core/landscape/test_exporter.py`
- Evidence:
  - `src/elspeth/contracts/audit.py`
  - `src/elspeth/core/landscape/repositories.py`
  - `tests/unit/contracts/test_audit.py`
  - `tests/unit/core/landscape/test_repositories.py`
  - `tests/unit/core/landscape/test_exporter.py`
