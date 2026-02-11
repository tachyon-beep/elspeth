# Bug Report: FieldMapper Strict Mode Can Emit Errors Without on_error Validation

**Status: FIXED**

## Status Update (2026-02-11)

- Classification: **Fixed**
- Verification summary:
  - Re-verified against current code on 2026-02-11; the originally reported behavior is no longer present.


## Summary

- `field_mapper` can return `TransformResult.error()` in strict mode without enforcing `on_error` configuration, which triggers a runtime crash in the executor instead of a configuration-time validation error.

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
- Data set or fixture: Row missing a mapped field under `strict: true`

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `src/elspeth/plugins/transforms/field_mapper.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Configure `field_mapper` with `strict: true` and a mapping for a field that may be absent.
2. Omit `on_error` in the transform options.
3. Process a row missing the mapped field.

## Expected Behavior

- Configuration validation should fail at startup if `strict: true` and `on_error` is not provided, or the transform should be prevented from returning an error without routing instructions.

## Actual Behavior

- FieldMapper returns `TransformResult.error()`, and the executor raises `RuntimeError` because `on_error` is `None`, crashing the run.

## Evidence

- `src/elspeth/plugins/transforms/field_mapper.py:116-120` returns `TransformResult.error()` when a mapped field is missing and `strict` is enabled.
- `src/elspeth/plugins/transforms/field_mapper.py:33-36` defines config without enforcing `on_error` when `strict` is true.
- `src/elspeth/plugins/protocols.py:164-167` requires transforms that return errors to set `_on_error`.
- `src/elspeth/engine/executors.py:448-456` raises `RuntimeError` when `on_error` is not configured.

## Impact

- User-facing impact: Pipeline crashes mid-run instead of quarantining or routing error rows.
- Data integrity / security impact: None directly, but abrupt failure can leave partial runs.
- Performance or cost impact: Wasted run time before crash.

## Root Cause Hypothesis

- FieldMapperConfig does not enforce `on_error` when `strict` is enabled, even though strict mode can produce error results.

## Proposed Fix

- Code changes (modules/files): `src/elspeth/plugins/transforms/field_mapper.py` add a Pydantic validator (model-level) requiring `on_error` when `strict` is true.
- Config or schema changes: None.
- Tests to add/update: Add a validation test in `tests/plugins/transforms/test_field_mapper.py` or a config validation test ensuring `strict: true` without `on_error` raises `PluginConfigError`.
- Risks or migration steps: This introduces a stricter config requirement for strict mode; update documentation if needed.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `src/elspeth/plugins/protocols.py:164-167`
- Observed divergence: FieldMapper can return errors without enforcing `_on_error` configuration.
- Reason (if known): Missing conditional validation in FieldMapperConfig.
- Alignment plan or decision needed: Enforce `on_error` when strict mode enables error returns.

## Acceptance Criteria

- FieldMapper configuration fails fast when `strict: true` and `on_error` is omitted.
- No runtime `RuntimeError` from `TransformExecutor` for strict-mode missing fields when configs are validated.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/plugins/transforms/test_field_mapper.py`
- New tests required: yes, add config validation coverage for strict mode.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: N/A
