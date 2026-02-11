# Bug Report: CLI crashes on non-mapping settings YAML before validation

**Status: RESOLVED ✅**

## Status Update (2026-02-11)

- Classification: **Resolved**
- Resolution summary:
  - `_load_raw_yaml()` now enforces a mapping/object YAML root and raises `ValueError` for list/scalar roots.
  - CLI entrypoints using `_load_settings_with_secrets()` now handle that `ValueError` as a clean user-facing config error.
  - Verified on `run`, `validate`, `resume`, and `purge` code paths.
- Fix evidence:
  - `src/elspeth/cli.py` (`_load_raw_yaml`, `run`, `resume`, `purge`)
  - `tests/unit/core/security/test_config_secrets.py`
  - `tests/unit/cli/test_error_boundaries.py`

## Summary

- `_load_raw_yaml()` accepted any YAML root type and downstream code assumed mapping semantics, causing uncaught `AttributeError` for non-mapping roots.

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
- Data set or fixture: `settings.yaml` with a top-level list or scalar

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `src/elspeth/cli.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Create a `settings.yaml` whose top level is a list or scalar (e.g., `- foo: bar`).
2. Run `elspeth validate -s settings.yaml` or `elspeth run -s settings.yaml --dry-run`.
3. Observe an `AttributeError: 'list' object has no attribute 'get'` instead of a config error.

## Expected Behavior

- CLI should emit a clear configuration validation error indicating the YAML root must be a mapping.

## Actual Behavior

- CLI raises an uncaught `AttributeError` during secrets extraction.

## Evidence

- `_load_raw_yaml()` now validates parsed YAML root type before returning.
- `run`, `resume`, and `purge` now catch and surface `ValueError` from config-boundary validation.
- Regression tests now cover non-mapping roots across helper + CLI commands.

## Impact

- User-facing impact: confusing stack trace instead of actionable config error.
- Data integrity / security impact: none direct, but config boundary is not validated as required.
- Performance or cost impact: none.

## Root Cause Hypothesis

- Missing type validation for external YAML root object before accessing mapping-only operations.

## Proposed Fix

- Code changes (modules/files):
  - `src/elspeth/cli.py`: validate `safe_load` result root type in `_load_raw_yaml()`.
  - `src/elspeth/cli.py`: add `ValueError` handling in `run`, `resume`, and `purge`.
- Config or schema changes: None.
- Tests added/updated:
  - `tests/unit/core/security/test_config_secrets.py`: helper rejects non-mapping root.
  - `tests/unit/cli/test_error_boundaries.py`: non-mapping YAML handled cleanly in `run`, `validate`, `resume`, `purge`.
- Risks or migration steps: None.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:59-69` (Tier 3 boundary requires validation at the boundary).
- Observed divergence: External config input isn’t validated before being accessed as a mapping.
- Reason (if known): Missing type check on raw YAML parse result.
- Alignment plan or decision needed: Add explicit root-type validation and surface a clean error.

## Acceptance Criteria

- Non-mapping YAML produces a readable validation error (no stack trace).
- `run`, `validate`, and any other path that uses `_load_raw_yaml()` handle this error consistently.

## Tests

- Validation run:
  - `uv run pytest -q tests/unit/core/security/test_config_secrets.py tests/unit/cli/test_error_boundaries.py`
  - `uv run pytest -q tests/unit/cli/test_validate_command.py`
  - `uv run ruff check src/elspeth/cli.py tests/unit/cli/test_error_boundaries.py tests/unit/core/security/test_config_secrets.py`
- New tests required: no (covered by new regression tests).

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md` (Tier 3 validation guidance)
