# Bug Report: Noisy Logger Levels Override Higher Root Thresholds

**Status: RESOLVED ✅**

## Status Update (2026-02-11)

- Classification: **Resolved**
- Verification summary:
  - `configure_logging(level='ERROR')` now sets noisy logger levels to at least the configured root threshold.
  - Effective level mismatch no longer occurs (`root=ERROR`, `azure=ERROR`), so warnings from noisy loggers are suppressed.
- Current evidence:
  - `src/elspeth/core/logging.py`
  - `tests/unit/core/test_logging.py`

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

- `src/elspeth/core/logging.py` now computes `noisy_level = max(log_level, logging.WARNING)` and applies it to all noisy loggers.
- `tests/unit/core/test_logging.py` includes regression coverage that verifies noisy warnings are suppressed at root `ERROR`.

## Impact

- User-facing impact: Log output includes warnings even when the system is configured to emit only errors.
- Data integrity / security impact: Low, but can reveal unwanted operational details in logs when users expect stricter filtering.
- Performance or cost impact: Minor additional log volume.

## Root Cause Hypothesis

- The code sets noisy loggers to a fixed `WARNING` level, which can be less restrictive than the configured root level. In Python logging, ancestor logger levels are not re-applied during propagation, so `WARNING` records from these loggers are still emitted.

## Proposed Fix

- Code changes (modules/files):
  - `src/elspeth/core/logging.py`: set noisy loggers to `max(log_level, logging.WARNING)` to avoid lowering verbosity below the configured threshold.
- Config or schema changes: None.
- Tests to add/update:
  - Added a regression test ensuring noisy logger warnings are suppressed when `level="ERROR"`.
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

- Validation run:
  - `uv run pytest -q tests/unit/core/test_logging.py`
  - `uv run ruff check src/elspeth/core/logging.py tests/unit/core/test_logging.py`
- New tests required: no (covered by regression test).

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: docs/plans/2026-02-03-pipelinerow-migration.md
