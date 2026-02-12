# Bug Report: Schema Config Errors Escape Validator as Exceptions Instead of Structured Errors

**Status: CLOSED**

## Status Update (2026-02-12)

- Classification: **Fixed and verified**
- Resolution summary:
  - Updated `PluginConfigValidator` to catch `PluginConfigError` explicitly and convert wrapped schema `ValueError` causes into structured `ValidationError` entries.
  - Applied this conversion path consistently across source, transform, and sink validators.
  - Added regression coverage for invalid embedded `schema.mode` on source/transform/sink validation paths.
- Verification:
  - `.venv/bin/python -m pytest tests/unit/plugins/test_validation.py -q` (24 passed)
  - `.venv/bin/python -m pytest tests/unit/plugins -q` (1810 passed, 3 xfailed, 3 deselected)
  - `.venv/bin/ruff check src/elspeth/plugins/validation.py tests/unit/plugins/test_validation.py` (passed)

## Status Update (2026-02-11)

- Classification: **Still open**
- Verification summary:
  - Re-verified against current code on 2026-02-11; the behavior described in this ticket is still present.


## Summary

- Invalid `schema` configs in plugin options raise `PluginConfigError` and propagate out of `PluginConfigValidator`, violating the validator’s “structured errors” contract and bypassing formatted error reporting.

## Severity

- Severity: minor
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: 0282d1b441fe23c5aaee0de696917187e1ceeb9b / RC2.3-pipeline-row
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Any plugin config with invalid `schema` (e.g., `{"schema": {"mode": "bad"}}`)

## Agent Context (if relevant)

- Goal or task prompt: Static analysis bug audit of `src/elspeth/plugins/validation.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Call `PluginConfigValidator().validate_source_config("csv", {"path": "...", "schema": {"mode": "bad"}, "on_validation_failure": "quarantine"})`.
2. Observe a `PluginConfigError` (or uncaught exception) instead of a structured error list.

## Expected Behavior

- Validator should return a `ValidationError` list describing the schema failure (e.g., field `schema`, message about invalid mode).

## Actual Behavior

- Validator re-raises the exception because it only extracts `PydanticValidationError` and ignores `PluginConfigError` / `ValueError` from `SchemaConfig.from_dict`.

## Evidence

- Validator only handles `PydanticValidationError` and re-raises others: `src/elspeth/plugins/validation.py:72-83`, `src/elspeth/plugins/validation.py:129-139`, `src/elspeth/plugins/validation.py:188-199`.
- `PluginConfig.from_dict()` converts schema parsing errors into `PluginConfigError` with a `ValueError` cause: `src/elspeth/plugins/config_base.py:61-76`.
- `SchemaConfig.from_dict()` raises `ValueError` for invalid schema modes: `src/elspeth/contracts/schema.py:302-343`.

## Impact

- User-facing impact: Invalid schema configurations produce unformatted exceptions instead of structured validation errors; CLI error output loses field-level context.
- Data integrity / security impact: None directly.
- Performance or cost impact: None.

## Root Cause Hypothesis

- `PluginConfigValidator` assumes only Pydantic errors will surface from `from_dict`, but schema parsing errors are wrapped as `PluginConfigError` and not converted to `ValidationError` entries.

## Proposed Fix

- Code changes (modules/files):
  - In `src/elspeth/plugins/validation.py`, catch `PluginConfigError` (or `ValueError`) in `validate_*_config()` and convert to `ValidationError` with `field="schema"` or a generic field.
  - Optionally call `validate_schema_config()` when `schema` is present and merge errors.
- Config or schema changes: None.
- Tests to add/update:
  - Add a test in `tests/plugins/test_validation.py` asserting invalid schema returns a structured error list rather than raising.
- Risks or migration steps:
  - None; improves error handling without changing validation rules.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `src/elspeth/plugins/validation.py:6-9`
- Observed divergence: Validator promises “Returns structured errors (not exceptions)” but schema parsing errors propagate as exceptions.
- Reason (if known): Unknown
- Alignment plan or decision needed: Catch and convert `PluginConfigError` in validator methods.

## Acceptance Criteria

- Invalid `schema` values in any plugin config result in a non-empty `ValidationError` list and do not raise exceptions.
- New unit test covers invalid schema handling.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/plugins/test_validation.py -k schema`
- New tests required: yes, add a test for schema error propagation.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: N/A
