## Summary

`create_json_formatters()` drops `RunSummary.routed` and `RunSummary.routed_destinations`, so JSON CLI consumers lose the routing breakdown that the orchestrator emits and the console formatter displays.

## Severity

- Severity: minor
- Priority: P2

## Location

- File: /home/john/elspeth/src/elspeth/cli_formatters.py
- Line(s): 130-143
- Function/Method: `_format_run_summary_json`

## Evidence

`RunSummary` explicitly includes routing metrics as part of its contract:

```python
# src/elspeth/contracts/events.py:128-142
# - routed: Total rows routed to non-default sinks (gates or error routing)
# - routed_destinations: Count per destination sink {sink_name: count}
...
routed: int = 0
routed_destinations: tuple[tuple[str, int], ...] = ()
```

The orchestrator populates those fields on every completed, partial, and interrupted summary:

```python
# src/elspeth/engine/orchestrator/core.py:1203-1214
RunSummary(
    ...
    routed=result.rows_routed,
    routed_destinations=tuple(result.routed_destinations.items()),
)
```

The console formatter preserves that information:

```python
# src/elspeth/cli_formatters.py:57-63
if event.routed > 0:
    dest_parts = [f"{name}:{count}" for name, count in event.routed_destinations]
    ...
    routed_summary = f" | →{event.routed:,} routed"
    if dest_str:
        routed_summary += f" ({dest_str})"
```

But the JSON formatter silently omits both fields:

```python
# src/elspeth/cli_formatters.py:130-143
{
    "event": "run_completed",
    "run_id": event.run_id,
    "status": event.status.value,
    "total_rows": event.total_rows,
    "succeeded": event.succeeded,
    "failed": event.failed,
    "quarantined": event.quarantined,
    "duration_seconds": event.duration_seconds,
    "exit_code": event.exit_code,
}
```

The current unit test suite codifies the omission instead of catching it:

```python
# tests/unit/cli/test_cli_formatters.py:148-178
event = RunSummary(... routed=1, routed_destinations=(("error_sink", 1),))
...
assert payload == {
    "event": "run_completed",
    "run_id": "run-3",
    "status": "failed",
    "total_rows": 1,
    "succeeded": 0,
    "failed": 1,
    "quarantined": 0,
    "duration_seconds": 0.0,
    "exit_code": 2,
}
```

What the code does:
- Console mode shows routing metrics.
- JSON mode discards them.

What it should do:
- Emit the same summary facts in JSON mode, including `routed` and a structured `routed_destinations` field.

## Root Cause Hypothesis

`cli_formatters.py` appears to have been updated for routed-run summaries on the console side only, while the JSON path and its tests were left on the older pre-routing payload shape. That created a formatter-specific contract drift between the `RunSummary` event model and the structured CLI output.

## Suggested Fix

Extend `_format_run_summary_json()` to serialize the routing fields, and update the unit test to expect them.

Example shape:

```python
{
    "event": "run_completed",
    "run_id": event.run_id,
    "status": event.status.value,
    "total_rows": event.total_rows,
    "succeeded": event.succeeded,
    "failed": event.failed,
    "quarantined": event.quarantined,
    "duration_seconds": event.duration_seconds,
    "exit_code": event.exit_code,
    "routed": event.routed,
    "routed_destinations": [
        {"sink": name, "count": count} for name, count in event.routed_destinations
    ],
}
```

A tuple/list-of-pairs form would also work, but the key requirement is that JSON mode must stop dropping the routing breakdown.

## Impact

Automation consuming `elspeth ... --json` cannot tell how many rows were diverted or where they went, even though that outcome is part of the emitted `RunSummary` and part of the human-readable output. This creates an observability/integration blind spot for routed-row workflows and makes JSON summaries materially less informative than the underlying event contract.
