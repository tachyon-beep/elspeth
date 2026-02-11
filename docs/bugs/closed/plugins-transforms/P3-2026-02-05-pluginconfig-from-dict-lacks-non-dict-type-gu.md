# Bug Report: PluginConfig.from_dict Lacks Non-Dict Type Guard

**Status: CLOSED**

## Status Update (2026-02-11)

- Classification: **Resolved**
- Resolution summary:
  - `PluginConfig.from_dict` now performs an explicit top-level type guard and raises `PluginConfigError` when input is not a dict.
  - Added parameterized regression coverage for non-dict payloads (`None`, `int`, `str`, `list`) to ensure consistent error handling.


## Summary

- `PluginConfig.from_dict` assumes the input is a dict; non-dict inputs raise `TypeError` and bypass `PluginConfigError`, producing unclear crashes instead of a consistent validation error.

## Severity

- Severity: minor
- Priority: P3

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: Unknown
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Unknown

## Agent Context (if relevant)

- Goal or task prompt: static analysis deep bug audit of `src/elspeth/plugins/config_base.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Call `PluginConfig.from_dict(None)` or `PluginConfig.from_dict("not a dict")`.
2. Observe the exception type and message.

## Expected Behavior

- A `PluginConfigError` with a clear message that config must be a dict.

## Actual Behavior

- `TypeError` is raised by `dict(config)` and is not wrapped.

## Evidence

- `src/elspeth/plugins/config_base.py:60-82` now type-checks `config` before coercion and routes malformed input through `PluginConfigError`.

## Impact

- User-facing impact: Unclear error messages for malformed configs; validation pipeline bypassed.
- Data integrity / security impact: None known.
- Performance or cost impact: None known.

## Root Cause Hypothesis

- Missing explicit type validation for `config` and missing `TypeError` handling in `from_dict`.

## Proposed Fix

- Code changes (modules/files): Add a type guard at the start of `PluginConfig.from_dict` in `src/elspeth/plugins/config_base.py` and raise `PluginConfigError` when `config` is not a dict.
- Config or schema changes: None.
- Tests to add/update: Add a test in `tests/plugins/test_config_base.py` asserting non-dict input raises `PluginConfigError`.
- Risks or migration steps: None.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): Unknown
- Observed divergence: Unknown
- Reason (if known): Unknown
- Alignment plan or decision needed: Unknown

## Acceptance Criteria

- Non-dict inputs to `PluginConfig.from_dict` raise `PluginConfigError` with a clear message.
- Test coverage exists for the non-dict input case.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/unit/plugins/test_config_base.py -v`
- New tests required: yes, add non-dict input validation test.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: Unknown

---

## Verification (2026-02-11)

- Reproduced prior failure:
  - `PluginConfig.from_dict(None)` and `PluginConfig.from_dict(123)` raised raw `TypeError` from `dict(config)`.
- Post-fix behavior:
  - Non-dict inputs now consistently raise `PluginConfigError` with a clear type-specific message.
- Tests executed:
  - `PYTHONPATH=src .venv/bin/python -m pytest -q tests/unit/plugins/test_config_base.py`
  - `.venv/bin/ruff check src/elspeth/plugins/config_base.py tests/unit/plugins/test_config_base.py`
