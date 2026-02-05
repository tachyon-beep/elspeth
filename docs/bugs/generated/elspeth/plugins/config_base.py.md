# Bug Report: Legacy Sink Header Options Violate No-Legacy Policy

## Summary

- Sink config still exposes and prioritizes legacy `display_headers` and `restore_source_headers`, explicitly labeled as backwards compatibility, which violates the No Legacy Code Policy.

## Severity

- Severity: major
- Priority: P2

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

1. Configure a sink with `display_headers` or `restore_source_headers` in options (no `headers`).
2. Parse with `SinkPathConfig.from_dict(...)`.

## Expected Behavior

- Legacy header options are rejected; only `headers` is accepted.

## Actual Behavior

- Legacy options are accepted and used for header resolution.

## Evidence

- `src/elspeth/plugins/config_base.py:214-243` documents and defines legacy options as “backwards compatibility.”
- `src/elspeth/plugins/config_base.py:220-305` enforces legacy precedence and behavior (legacy fields actively used).
- `tests/plugins/test_sink_header_config.py:60-83` asserts legacy options are accepted and mapped.

## Impact

- User-facing impact: Confusing, dual configuration surface with “legacy” behavior still supported.
- Data integrity / security impact: Increases risk of configuration drift and hidden compatibility paths in an audit-focused system.
- Performance or cost impact: None known.

## Root Cause Hypothesis

- Legacy compatibility fields were kept in the base sink config despite the explicit “No Legacy Code Policy.”

## Proposed Fix

- Code changes (modules/files): Remove `display_headers` and `restore_source_headers` from `SinkPathConfig` and delete the associated precedence/validation logic in `src/elspeth/plugins/config_base.py`.
- Config or schema changes: Remove legacy options from supported config surface; enforce `headers` only.
- Tests to add/update: Update `tests/plugins/test_sink_header_config.py` and any sink tests to reflect removal of legacy options.
- Risks or migration steps: Breaking change for configs using legacy options; update examples and docs in the same change.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:841-885` (No Legacy Code Policy).
- Observed divergence: Legacy/backwards-compatibility options explicitly present and supported in sink config.
- Reason (if known): Unknown.
- Alignment plan or decision needed: Remove legacy options and update all call sites/tests to use `headers`.

## Acceptance Criteria

- `SinkPathConfig` rejects `display_headers` and `restore_source_headers`.
- Only `headers` is supported and documented.
- Tests updated to reflect the single configuration path.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/plugins/test_sink_header_config.py -v`
- New tests required: yes, adjust existing tests to validate rejection of legacy options.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md` (No Legacy Code Policy)
---
# Bug Report: PluginConfig.from_dict Lacks Non-Dict Type Guard

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

- `src/elspeth/plugins/config_base.py:60-76` calls `dict(config)` without a type guard and only catches `ValidationError` and `ValueError`.

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

- Suggested tests to run: `.venv/bin/python -m pytest tests/plugins/test_config_base.py -v`
- New tests required: yes, add non-dict input validation test.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: Unknown
