## Summary

Console run-summary formatter crashes on legitimate `RunCompletionStatus.INTERRUPTED` events due to an incomplete status-symbol map.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/cli_formatters.py`
- Line(s): `50-55`
- Function/Method: `_format_run_summary`

## Evidence

`RunCompletionStatus` defines `INTERRUPTED` as a valid terminal status:
- `src/elspeth/contracts/events.py:53-60`

Orchestrator emits `RunSummary(..., status=RunCompletionStatus.INTERRUPTED, ...)` in both run and resume shutdown paths:
- `src/elspeth/engine/orchestrator/core.py:885-888`
- `src/elspeth/engine/orchestrator/core.py:1969-1972`

But console formatter only maps `completed/partial/failed`:
- `src/elspeth/cli_formatters.py:50-55`

```python
status_symbols = {
    "completed": "✓",
    "partial": "⚠",
    "failed": "✗",
}
symbol = status_symbols[event.status.value]
```

Direct repro (in repo environment) raises:
- `KeyError 'interrupted'`

Event bus propagates handler exceptions (no swallow):
- `src/elspeth/core/events.py:67`
- `src/elspeth/core/events.py:83-85`

So this formatter error can mask graceful-shutdown handling in CLI. `run` then falls into generic exception path (`exit 1`) instead of interrupted path (`exit 3`):
- `src/elspeth/cli.py:515-533` (expected graceful shutdown handling)
- `src/elspeth/cli.py:533-550` (generic exception fallback)

## Root Cause Hypothesis

`RunCompletionStatus.INTERRUPTED` was added and emitted by orchestrator, but `create_console_formatters()` was not updated, leaving status mapping out of sync with the event contract.

## Suggested Fix

Update `_format_run_summary` to handle all `RunCompletionStatus` values, including `INTERRUPTED` (prefer enum-keyed mapping).

Example:

```python
status_symbols = {
    RunCompletionStatus.COMPLETED: "✓",
    RunCompletionStatus.PARTIAL: "⚠",
    RunCompletionStatus.FAILED: "✗",
    RunCompletionStatus.INTERRUPTED: "⏸",
}
symbol = status_symbols[event.status]
```

Also add a unit test for interrupted summaries in `tests/unit/cli/test_cli_formatters.py` to prevent regression.

## Impact

On Ctrl+C/graceful shutdown paths, CLI formatter throws `KeyError`, which can:
- Convert an intended resumable interruption into a generic CLI error path
- Change expected exit semantics (`3` interrupted) to generic failure (`1`)
- Hide operator guidance (`Resume with: ...`) behind formatter failure behavior

Audit DB status may still be finalized as interrupted, but CLI/operator and automation signals become incorrect.
