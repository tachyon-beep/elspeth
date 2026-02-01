# Bug Report: --json-logs produces mixed JSON and plain-text lines

## Summary

- When `json_output=True`, stdlib logging modules bypass structlog and emit plain text, resulting in mixed JSON/plain-text log streams.

## Severity

- Severity: moderate
- Priority: P2

## Reporter

- Name or handle: Codex (triaged by Claude)
- Date: 2026-01-31

## Evidence

- `src/elspeth/core/logging.py:26-31` - stdlib logging configured with `format="%(message)s"`.
- `src/elspeth/core/logging.py:57-62` - uses `structlog.PrintLoggerFactory()` which prints directly.
- Modules using `logging.getLogger(__name__)` emit plain text even when JSON enabled

## Impact

- User-facing impact: Log parsing fails in CI/observability pipelines
- Data integrity: None

## Proposed Fix

- Use `structlog.stdlib.LoggerFactory()` and `ProcessorFormatter` to route stdlib loggers through structlog

## Acceptance Criteria

- All log output is valid JSON when `--json-logs` enabled

## Verification (2026-02-01)

**Status: STILL VALID**

- JSON mode still uses stdlib logging with plain `%(message)s` and `PrintLoggerFactory()`, allowing mixed output. (`src/elspeth/core/logging.py:26-31`, `src/elspeth/core/logging.py:57-62`)
