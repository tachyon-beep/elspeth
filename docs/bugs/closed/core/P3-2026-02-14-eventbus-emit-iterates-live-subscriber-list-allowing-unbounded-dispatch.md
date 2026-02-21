## Summary

`EventBus.emit()` iterates a live subscriber list, so handlers that call `subscribe()` during emission mutate iteration state and can trigger unbounded same-event dispatch in a single `emit()` call.

## Severity

- Severity: minor
- Priority: P3 (downgraded from P1 — no production handler calls subscribe() during emission; purely theoretical with synthetic self-subscribing handlers)

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/core/events.py`
- Line(s): `59-61`, `83-85`
- Function/Method: `EventBus.subscribe`, `EventBus.emit`

## Evidence

`subscribe()` appends directly into the per-event list (`_subscribers[event_type].append(handler)`), and `emit()` then iterates that same list object retrieved from `_subscribers`:

- `/home/john/elspeth-rapid/src/elspeth/core/events.py:59-61`
- `/home/john/elspeth-rapid/src/elspeth/core/events.py:83-85`

Because Python list iteration observes appended items, a handler that subscribes during dispatch is executed immediately in the same emission cycle. Repro on current code:

- Subscribe `h1` for event `E`
- `h1` calls `bus.subscribe(E, h2)`
- One `bus.emit(E(...))` calls both `h1` and newly-added `h2` in that same emit

A stronger repro (self-subscribing handler) produced `21` handler calls from a single `emit()` before forced stop, showing unbounded growth risk.

Related integration context:
- Re-entrant handler behavior is explicitly exercised in `/home/john/elspeth-rapid/tests/unit/telemetry/test_reentrance.py:289-313`
- Duplicate subscriptions are allowed by design in `/home/john/elspeth-rapid/tests/unit/core/test_events.py:199-215`

## Root Cause Hypothesis

Dispatch uses mutable shared state directly instead of a snapshot. `emit()` assumes subscriber membership is stable for the duration of dispatch, but `subscribe()` is callable during handler execution, so this assumption is false.

## Suggested Fix

In `emit()`, snapshot handlers before iterating so the dispatch set is fixed at emit-start:

```python
def emit(self, event: T) -> None:
    handlers = tuple(self._subscribers.get(type(event), ()))
    for handler in handlers:
        handler(event)
```

This keeps current semantics (no-subscriber is silent, exceptions still propagate) while preventing same-cycle list growth effects.

## Impact

- Potential infinite/unbounded handler execution in observability path
- Unbounded subscriber list growth and memory/perf degradation
- Pipeline progress can stall/hang due to event dispatch behavior instead of failing fast on the actual handler bug
