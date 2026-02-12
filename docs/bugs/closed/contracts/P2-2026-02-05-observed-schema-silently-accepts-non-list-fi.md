# Bug Report: Observed schema silently accepts non-list `fields` values

**Status: CLOSED**

## Status Update (2026-02-12)

- Classification: **Resolved**
- Resolution summary:
  - Tightened observed-mode validation in `SchemaConfig.from_dict` to reject any `fields` value other than `None` or `[]` in `src/elspeth/contracts/schema.py`.
  - Added regression tests for string and dict `fields` values in observed mode, plus explicit coverage that `[]` remains allowed in `tests/unit/contracts/test_schema_config.py`.

## Status Update (2026-02-11)

- Classification: **Still open**
- Verification summary:
  - Observed-mode validation still only rejects non-empty list `fields`.
  - Non-list values such as string/dict still bypass the observed-mode `fields` guard.
- Current evidence:
  - `src/elspeth/contracts/schema.py:324`
  - `src/elspeth/contracts/schema.py:334`

## Summary

- `SchemaConfig.from_dict()` in observed mode ignores `fields` when it is a string or dict, silently accepting invalid config instead of raising a validation error.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: 1c70074ef3b71e4fe85d4f926e52afeca50197ab (branch `RC2.3-pipeline-row`)
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Unknown

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit for `src/elspeth/contracts/schema.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Run `SchemaConfig.from_dict({"mode": "observed", "fields": "id: int"})`.
2. Run `SchemaConfig.from_dict({"mode": "observed", "fields": {"id": "int"}})`.

## Expected Behavior

- Both calls should raise `ValueError` because observed schemas cannot include explicit field definitions of any type.

## Actual Behavior

- Both calls return a valid `SchemaConfig(mode="observed", fields=None, ...)` with no error, silently ignoring the invalid `fields` value.

## Evidence

- `SchemaConfig.from_dict` only rejects `fields` in observed mode when it is a non-empty list, so other types bypass validation. See `src/elspeth/contracts/schema.py:324-334` where `fields_value` is checked only for `list` and `len > 0`.
- Empirical check: calling `SchemaConfig.from_dict` with `fields` as a string or dict returns a schema without raising (verified in local Python REPL using `PYTHONPATH=src`).

## Impact

- User-facing impact: Invalid configuration is silently accepted, making it easy to think a schema is defined when it is actually ignored.
- Data integrity / security impact: Pipeline runs in observed mode (no schema enforcement), weakening contract validation and audit guarantees.
- Performance or cost impact: None known.

## Root Cause Hypothesis

- Observed-mode validation only blocks non-empty lists of fields and does not enforce type checking on other `fields` values, so invalid inputs slip through.

## Proposed Fix

- Code changes (modules/files): `src/elspeth/contracts/schema.py` — in observed mode, treat any non-`None` `fields` value as invalid unless it is an empty list; reject strings/dicts with a clear `ValueError`.
- Config or schema changes: None.
- Tests to add/update: `tests/contracts/test_schema_config.py` — add tests asserting `SchemaConfig.from_dict({"mode": "observed", "fields": "id: int"})` and `fields` as dict both raise `ValueError`.
- Risks or migration steps: None; this is stricter validation of clearly invalid configurations.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `src/elspeth/contracts/schema.py:324-334` (documented rule: observed schemas cannot have explicit field definitions).
- Observed divergence: Non-list `fields` values bypass validation in observed mode.
- Reason (if known): Unknown.
- Alignment plan or decision needed: Enforce type validation for `fields` in observed mode (raise on any non-`None` and non-empty list).

## Acceptance Criteria

- Observed mode raises `ValueError` for any non-`None` `fields` value that is not an empty list, including strings and dicts.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/contracts/test_schema_config.py -k observed`
- New tests required: yes, add cases for `fields` as string and dict in observed mode.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `docs/plans/2026-02-02-unified-schema-contracts-design.md`
