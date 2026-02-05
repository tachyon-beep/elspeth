# Bug Report: Noisy Logger Levels Override Higher Root Thresholds

## Summary

- `configure_logging()` forces noisy third-party loggers to `WARNING` even when the configured root level is higher (e.g., `ERROR`), causing warnings to be emitted unexpectedly.

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
- Data set or fixture: N/A

## Agent Context (if relevant)

- Goal or task prompt: Deep static bug audit of `/home/john/elspeth-rapid/src/elspeth/core/logging.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Call `configure_logging(level="ERROR")`.
2. Log a warning from a noisy logger (e.g., `logging.getLogger("azure").warning("warn")`).

## Expected Behavior

- No warning is emitted because the configured log level is `ERROR`.

## Actual Behavior

- Warning is emitted because noisy loggers are explicitly set to `WARNING`, which bypasses the higher root threshold.

## Evidence

- `src/elspeth/core/logging.py:137-141` sets noisy loggers to `WARNING` unconditionally, regardless of `log_level`.

## Impact

- User-facing impact: Log output includes warnings even when the system is configured to emit only errors.
- Data integrity / security impact: Low, but can reveal unwanted operational details in logs when users expect stricter filtering.
- Performance or cost impact: Minor additional log volume.

## Root Cause Hypothesis

- The code sets noisy loggers to a fixed `WARNING` level, which can be less restrictive than the configured root level. In Python logging, ancestor logger levels are not re-applied during propagation, so `WARNING` records from these loggers are still emitted.

## Proposed Fix

- Code changes (modules/files):
  - In `src/elspeth/core/logging.py`, set noisy loggers to `max(log_level, logging.WARNING)` to avoid lowering verbosity below the configured threshold.
- Config or schema changes: None.
- Tests to add/update:
  - Add a test ensuring noisy logger effective level is at least the configured root level when `level="ERROR"`.
- Risks or migration steps:
  - Low risk; only affects log filtering.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): Unknown
- Observed divergence: Unknown
- Reason (if known): Unknown
- Alignment plan or decision needed: Unknown

## Acceptance Criteria

- When `configure_logging(level="ERROR")` is used, noisy loggers do not emit `WARNING` messages.
- Test coverage includes a case verifying noisy logger levels respect the configured root threshold.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/core/test_logging.py`
- New tests required: yes, add a test for `level="ERROR"` noisy logger behavior

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: docs/plans/2026-02-03-pipelinerow-migration.md
