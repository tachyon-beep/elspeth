## Summary

`resume()` does not flush telemetry before returning/raising, so strict telemetry failure mode (`fail_on_total_exporter_failure`) is not enforced on resume path.

## Severity

- Severity: minor
- Priority: P2

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/engine/orchestrator/core.py`
- Line(s): 952-974, 1824-2021
- Function/Method: `Orchestrator.run`, `Orchestrator.resume`

## Evidence

`run()` has a telemetry-flush `finally` block:

```python
952 finally:
966     self._flush_telemetry()
967 except TelemetryExporterError ...
```

`resume()` has no equivalent flush path across success/failure branches (`core.py:1824-2021`).

In telemetry manager, stored total-failure exceptions are re-raised only by `flush()`:

- `src/elspeth/telemetry/manager.py:437-441`

`close()` does not re-raise stored telemetry failure:

- `src/elspeth/telemetry/manager.py:453-519`

So resume can complete without surfacing configured strict telemetry failure.

## Root Cause Hypothesis

Telemetry flush/failure-propagation logic was added to `run()` but not mirrored in `resume()`.

## Suggested Fix

Add a `finally` block in `resume()` matching `run()` semantics:

1. Call `_flush_telemetry()`.
2. If `TelemetryExporterError` occurs and no prior exception is pending, raise it.
3. If another exception is pending, preserve original exception and log telemetry flush failure.

## Impact

- Silent observability degradation on resume path.
- Inconsistent behavior between `run()` and `resume()` under the same telemetry policy.
- `fail_on_total_exporter_failure=True` is effectively bypassed for resumes.

## Triage

- Status: open
- Source report: `docs/bugs/generated/engine/orchestrator/core.py.md`
- Finding index in source report: 3
- Beads: pending
