# Bug Report: `--json-logs` produces mixed JSON and plain-text lines because stdlib logging bypasses structlog

## Summary

- When `configure_logging(json_output=True)` is used (e.g., via `--json-logs`), only structlog loggers emit JSON while standard-library loggers emit plain text, breaking the “structured JSON logs” contract and machine parsing.

## Severity

- Severity: minor
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-01-30
- Related run/issue ID: N/A

## Environment

- Commit/branch: 17f7293805c0c36aa59bf5fad0f09e09c3035fc9 / fix/P2-aggregation-metadata-hardcoded
- OS: Unknown
- Python version: Unknown
- Config profile / env vars: N/A
- Data set or fixture: Any CLI run with `--json-logs`

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit for /home/john/elspeth-rapid/src/elspeth/core/logging.py
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Call `configure_logging(json_output=True)` (e.g., run any CLI command with `--json-logs`).
2. Emit a log from a module that uses `logging.getLogger(...)` (e.g., engine executors or plugins).
3. Observe stdout contains plain text lines (not JSON), mixed with JSON structlog lines.

## Expected Behavior

- All log lines are structured JSON when `--json-logs` is enabled, as documented for machine processing.

## Actual Behavior

- Structlog lines are JSON, but standard-library logs are plain text (format `%(message)s`), causing mixed, non-uniform output.

## Evidence

- `src/elspeth/core/logging.py:26-32` configures stdlib logging with `format="%(message)s"` and does not attach a structured formatter for JSON mode.
- `src/elspeth/core/logging.py:57-61` uses `structlog.PrintLoggerFactory()` (bypasses stdlib logging handlers).
- `src/elspeth/engine/executors.py:11-71` shows modules using `logging.getLogger(__name__)` (stdlib), which will emit unstructured lines.
- `docs/USER_MANUAL.md:61` states `--json-logs` outputs “structured JSON logs (for machine processing)”.

## Impact

- User-facing impact: CI/log ingestion pipelines expecting JSON will fail to parse or will drop non-JSON lines.
- Data integrity / security impact: None (audit trail is unaffected).
- Performance or cost impact: Log processing overhead from parse failures and dropped lines.

## Root Cause Hypothesis

- `configure_logging()` configures structlog for JSON but leaves standard-library loggers on a plain `%(message)s` formatter and uses `PrintLoggerFactory`, so stdlib log records never pass through structlog processors.

## Proposed Fix

- Code changes (modules/files):
  - `src/elspeth/core/logging.py`: Configure stdlib logging with `structlog.stdlib.ProcessorFormatter` and use `structlog.stdlib.LoggerFactory()` so both structlog and stdlib loggers emit JSON in `json_output=True` mode.
- Config or schema changes: None.
- Tests to add/update:
  - Extend `tests/core/test_logging.py` to emit a stdlib log record under `json_output=True` and assert it is valid JSON.
- Risks or migration steps:
  - Ensure existing console output remains human-readable for `json_output=False`; verify no duplicate log lines.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `docs/USER_MANUAL.md:61` (“--json-logs Output structured JSON logs (for machine processing)”)
- Observed divergence: With `--json-logs`, logs from stdlib loggers are not JSON, so output is not fully structured.
- Reason (if known): stdlib logging is configured with a plain formatter and not routed through structlog processors.
- Alignment plan or decision needed: Route stdlib loggers through structlog’s ProcessorFormatter when JSON mode is enabled.

## Acceptance Criteria

- In JSON mode, both structlog and standard-library loggers emit valid JSON lines.
- No mixed-format output when `--json-logs` is enabled.
- Existing console (human-readable) output remains intact when JSON mode is disabled.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/core/test_logging.py`
- New tests required: yes, add a stdlib logger JSON-output assertion.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `docs/plans/completed/2026-01-23-cli-observability-design.md:313-323`
