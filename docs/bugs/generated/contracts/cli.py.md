## Summary

No concrete bug found in /home/john/elspeth/src/elspeth/contracts/cli.py

## Severity

- Severity: trivial
- Priority: P3

## Location

- File: /home/john/elspeth/src/elspeth/contracts/cli.py
- Line(s): 1-52
- Function/Method: Unknown

## Evidence

`/home/john/elspeth/src/elspeth/contracts/cli.py:9-28` defines `ProgressEvent` with the same fields emitted by the orchestrator at `/home/john/elspeth/src/elspeth/engine/orchestrator/core.py:2013-2020` and `/home/john/elspeth/src/elspeth/engine/orchestrator/core.py:2544-2550`:

```python
ProgressEvent(
    rows_processed=counters.rows_processed,
    rows_succeeded=counters.rows_succeeded + counters.rows_routed,
    rows_failed=counters.rows_failed,
    rows_quarantined=counters.rows_quarantined,
    elapsed_seconds=elapsed,
)
```

`/home/john/elspeth/src/elspeth/cli_formatters.py:74-80` and `/home/john/elspeth/src/elspeth/cli_formatters.py:147-159` consume exactly those fields and the formatter tests at `/home/john/elspeth/tests/unit/cli/test_cli_formatters.py:108-146` cover the main edge case (`elapsed_seconds == 0`).

`/home/john/elspeth/src/elspeth/contracts/cli.py:31-52` defines `ExecutionResult`. Its actual producer at `/home/john/elspeth/src/elspeth/cli.py:941-1020` returns a dict matching the required contract keys:

```python
return {
    "run_id": result.run_id,
    "status": result.status,
    "rows_processed": result.rows_processed,
}
```

The contract is also explicitly locked by tests at `/home/john/elspeth/tests/unit/cli/test_execution_result.py:48-83`.

I did not find a credible runtime bug whose primary fix belongs in `contracts/cli.py`; the file is a small L0 contract module and its current fields line up with the verified producer/consumer paths above.

## Root Cause Hypothesis

No bug identified

## Suggested Fix

Unknown

## Impact

No confirmed breakage from `/home/john/elspeth/src/elspeth/contracts/cli.py` based on the verified integration paths.
