# Bug Report: PluginConfig.from_dict crashes on schema: null or non-mapping configs

## Summary

- `PluginConfig.from_dict` assumes both `config` and `schema` are mappings; if either is `None` (or other non-mapping), a raw `TypeError` escapes instead of a clear `PluginConfigError`.

## Severity

- Severity: minor
- Priority: P3

## Reporter

- Name or handle: Codex
- Date: 2026-01-30
- Related run/issue ID: N/A

## Environment

- Commit/branch: Unknown
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Plugin config dict with `schema: null` (or config itself set to `null`)

## Agent Context (if relevant)

- Goal or task prompt: Static analysis bug audit of /home/john/elspeth-rapid/src/elspeth/plugins/config_base.py
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Call `CSVSourceConfig.from_dict({"path": "/tmp/data.csv", "schema": None, "on_validation_failure": "discard"})`.
2. Observe the exception thrown.

## Expected Behavior

- Configuration errors should be reported as `PluginConfigError` with a clear message explaining that `schema` must be a dict with `fields`.

## Actual Behavior

- A raw `TypeError` is raised (e.g., `"argument of type 'NoneType' is not iterable"`) instead of a `PluginConfigError`.

## Evidence

- `src/elspeth/plugins/config_base.py:59-64` converts `config` with `dict(config)` and calls `SchemaConfig.from_dict(schema_dict)` without type checks or `TypeError` handling.
- `src/elspeth/contracts/schema.py:266-284` assumes a dict and executes `"fields" not in config`/`config.get(...)`, which triggers `TypeError` when `config` is `None` or non-mapping.

## Impact

- User-facing impact: Invalid configs can crash with opaque `TypeError`s instead of clear validation errors, making configuration issues hard to diagnose.
- Data integrity / security impact: None observed.
- Performance or cost impact: None observed.

## Root Cause Hypothesis

- `PluginConfig.from_dict` does not validate input types or catch `TypeError` from `dict(config)` or `SchemaConfig.from_dict`, so non-mapping configs escape as raw exceptions.

## Proposed Fix

- Code changes (modules/files):
  - Add explicit type checks in `src/elspeth/plugins/config_base.py` for `config` and `schema` (must be mappings), or catch `TypeError` and re-raise `PluginConfigError` with a clear message.
- Config or schema changes: None.
- Tests to add/update:
  - Add tests for `schema: null` and `config: null` in `tests/plugins/test_validation.py` (or a new unit test for `PluginConfig.from_dict`) asserting a `PluginConfigError` with an actionable message.
- Risks or migration steps:
  - Low risk; only affects error handling for invalid configurations.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): CLAUDE.md (Data Manifesto: Tier 3 external data must be validated at the boundary)
- Observed divergence: External configuration inputs can raise raw `TypeError` instead of validated, explicit errors.
- Reason (if known): Missing type validation and `TypeError` handling in `PluginConfig.from_dict`.
- Alignment plan or decision needed: Add explicit type checks or `TypeError` handling in `PluginConfig.from_dict` to keep failures explicit and user-facing.

## Acceptance Criteria

- Passing `schema: null` or a non-mapping config to `PluginConfig.from_dict` raises `PluginConfigError` with a clear, actionable message.
- Validation/instantiation paths no longer surface raw `TypeError` for malformed config types.

## Tests

- Suggested tests to run: `pytest tests/plugins/test_validation.py -k schema`
- New tests required: yes, add cases for `schema: null` and `config: null`.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: Unknown
