# Bug Report: Azure Monitor flush drops “no events” acknowledgment log

**Status: CLOSED**

## Pre-Fix Verification (2026-02-11)

- Classification: **Still open**
- Verification summary:
  - Azure exporter still returns immediately when `_buffer` is empty during flush.
  - That empty-buffer branch still has no acknowledgment log message.
- Current evidence:
  - `src/elspeth/telemetry/exporters/azure_monitor.py:243`
  - `src/elspeth/telemetry/exporters/azure_monitor.py:244`
  - `CLAUDE.md:524`

## Resolution (2026-02-12)

- Status: **FIXED**
- Changes applied:
  - Added explicit empty-buffer acknowledgment log in `_flush_batch()`:
    `src/elspeth/telemetry/exporters/azure_monitor.py`
  - Added unit coverage for empty-buffer flush acknowledgment:
    `tests/unit/telemetry/exporters/test_azure_monitor.py`
- Verification:
  - `./.venv/bin/python -m pytest tests/unit/telemetry/exporters/test_azure_monitor.py -q` (25 passed)
  - `./.venv/bin/python -m ruff check src/elspeth/telemetry/exporters/azure_monitor.py tests/unit/telemetry/exporters/test_azure_monitor.py` (passed)

## Summary

- `AzureMonitorExporter.flush()` / `_flush_batch()` returns silently when the buffer is empty, violating the “No Silent Failures” telemetry requirement to log that telemetry was requested but unavailable.

## Severity

- Severity: minor
- Priority: P3

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: 0282d1b441fe23c5aaee0de696917187e1ceeb9b / RC2.3-pipeline-row
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: N/A

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `src/elspeth/telemetry/exporters/azure_monitor.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Instantiate and configure `AzureMonitorExporter`, then call `flush()` before any events are exported.
2. Observe that no log is emitted indicating telemetry was requested but no events were available.

## Expected Behavior

- When `flush()` is called and there are no buffered events, the exporter should log an explicit “nothing to emit” acknowledgment per the telemetry “No Silent Failures” rule.

## Actual Behavior

- `_flush_batch()` returns early when the buffer is empty without any log entry, so telemetry polling is silent.

## Evidence

- `src/elspeth/telemetry/exporters/azure_monitor.py:243-244` returns immediately when `_buffer` is empty with no log.
- `CLAUDE.md:582-599` requires explicit acknowledgment when telemetry emission is requested but unavailable.

## Impact

- User-facing impact: Troubleshooting telemetry gaps is harder because flush requests with no data are silent.
- Data integrity / security impact: None.
- Performance or cost impact: None.

## Root Cause Hypothesis

- The empty-buffer early return in `_flush_batch()` lacks the required log acknowledgment for telemetry polling.

## Proposed Fix

- Code changes (modules/files):
  - Add a log entry in `src/elspeth/telemetry/exporters/azure_monitor.py` before returning when `_buffer` is empty in `_flush_batch()` (or in `flush()` before calling `_flush_batch()`).
- Config or schema changes: None.
- Tests to add/update:
  - Add a unit test asserting that `flush()` emits a “no telemetry to send” log when the buffer is empty.
- Risks or migration steps:
  - Minimal; only adds a log line.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:582-599` (No Silent Failures).
- Observed divergence: Empty flush requests are silent instead of logging “I have nothing.”
- Reason (if known): Missing log statement on empty buffer path.
- Alignment plan or decision needed: Add explicit log on empty buffer flush.

## Acceptance Criteria

- Calling `flush()` with an empty buffer emits a log acknowledging no telemetry was available.
- No changes to exporter behavior beyond logging.

## Tests

- Suggested tests to run: `python -m pytest tests/telemetry/test_azure_monitor_exporter.py -k flush_empty`
- New tests required: yes, add coverage for empty-buffer flush logging.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md` (Telemetry No Silent Failures section)
