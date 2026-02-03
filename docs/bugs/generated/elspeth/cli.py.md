# Bug Report: UnboundLocalError Masks Telemetry Initialization Failures

## Summary

- `telemetry_manager` is referenced in `finally` blocks without being initialized, so any exception before assignment (e.g., invalid telemetry config) raises `UnboundLocalError`, masking the real failure and skipping cleanup.

## Severity

- Severity: minor
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-03
- Related run/issue ID: N/A

## Environment

- Commit/branch: `RC2.3-pipeline-row` @ `3aa2fa93`
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Unknown

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit for `src/elspeth/cli.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Configure telemetry to fail initialization (e.g., invalid exporter config that makes `create_telemetry_manager()` raise).
2. Run `elspeth run --settings <settings.yaml> --execute` (or invoke `_execute_pipeline()` / `_execute_pipeline_with_instances()` directly).
3. Observe the exception raised in cleanup.

## Expected Behavior

- The original telemetry initialization error is surfaced, and cleanup always closes the DB and rate-limit registry.

## Actual Behavior

- `UnboundLocalError: local variable 'telemetry_manager' referenced before assignment` is raised in the `finally` block, masking the original error and skipping `db.close()`.

## Evidence

- `src/elspeth/cli.py:936-983` in `_execute_pipeline()` initializes `rate_limit_registry` but not `telemetry_manager`, then references `telemetry_manager` in `finally`.
- `src/elspeth/cli.py:1219-1268` in `_execute_pipeline_with_instances()` has the same pattern.

## Impact

- User-facing impact: Error messages are misleading; root cause is hidden.
- Data integrity / security impact: DB cleanup can be skipped on failure paths.
- Performance or cost impact: Potential resource leak on failure.

## Root Cause Hypothesis

- `telemetry_manager` is not initialized to `None` before the `try` block, so any failure before assignment leaves it undefined when referenced in `finally`.

## Proposed Fix

- Code changes (modules/files):
  - Initialize `telemetry_manager = None` before the `try` blocks in both `_execute_pipeline()` and `_execute_pipeline_with_instances()` in `src/elspeth/cli.py`.
- Config or schema changes: Unknown
- Tests to add/update:
  - Add a test that forces `create_telemetry_manager()` to raise (monkeypatch) and asserts the original exception is propagated without `UnboundLocalError`.
- Risks or migration steps:
  - Low risk; localized change.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): Unknown
- Observed divergence: Unknown
- Reason (if known): Unknown
- Alignment plan or decision needed: Unknown

## Acceptance Criteria

- Failing telemetry initialization no longer triggers `UnboundLocalError`.
- Original exception is surfaced and cleanup executes without raising.

## Tests

- Suggested tests to run: `./.venv/bin/python -m pytest tests/ -k telemetry`
- New tests required: yes, add a failure-path test for telemetry initialization.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: Unknown
