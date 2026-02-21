## Summary

`resume()` can leave a run permanently in `RUNNING` when any non-shutdown exception occurs during resumed row processing.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/engine/orchestrator/core.py`
- Line(s): 1865, 1937-1951, 1986-2021
- Function/Method: `Orchestrator.resume`

## Evidence

`resume()` marks the run as running, then only handles `GracefulShutdownError`:

```python
# core.py
1865 recorder.update_run_status(run_id, RunStatus.RUNNING)

1937 try:
1938     with shutdown_ctx as active_event:
1939         result = self._process_resumed_rows(...)
1951 except GracefulShutdownError:
...
1986 recorder.finalize_run(run_id, status=RunStatus.COMPLETED)
```

There is no generic `except Exception` path that finalizes `RunStatus.FAILED`.

But `_process_resumed_rows()` can raise regular exceptions (for example via sink writes), because `_write_pending_to_sinks()` calls `SinkExecutor.write()` and that re-raises sink failures (`src/elspeth/engine/executors/sink.py:215-227`).

Recovery then refuses resume on `RUNNING` runs:

- `src/elspeth/core/checkpoint/recovery.py:100-101` returns `can_resume=False` when status is `RUNNING`.

So a failed resume can strand the run in non-terminal status.

## Root Cause Hypothesis

`resume()` implemented explicit success and graceful-shutdown paths, but omitted a failure finalization branch equivalent to `run()`'s generic exception handling.

## Suggested Fix

Add a generic exception handler in `resume()` that:

1. Finalizes run as `RunStatus.FAILED`.
2. Emits `RunFinished(status=FAILED)` and a failed `RunSummary`.
3. Re-raises the original exception.

Mirror the failure handling structure already used in `run()`.

## Impact

- Run lifecycle invariant violation (missing terminal run status on failure).
- Resume can become blocked because recovery rejects `RUNNING` status.
- Operational/audit consumers see inconsistent run state vs actual failure.
