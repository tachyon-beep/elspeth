# Analysis: src/elspeth/telemetry/filtering.py

**Lines:** 73
**Role:** Granularity-based event filtering. Provides the `should_emit()` function that determines whether a telemetry event should be emitted based on the configured granularity level (LIFECYCLE, ROWS, FULL). Used by TelemetryManager as the single source of truth for event filtering.
**Key dependencies:** Imports `TelemetryGranularity` from `contracts/enums`, `GateEvaluated`, `TelemetryEvent`, `TokenCompleted`, `TransformCompleted` from `contracts/events`, and `ExternalCallCompleted`, `PhaseChanged`, `RowCreated`, `RunFinished`, `RunStarted` from `telemetry/events`. Imported by `telemetry/manager.py`.
**Analysis depth:** FULL

## Summary

Compact, correct filtering logic using Python's structural pattern matching. The match/case approach is clean and readable. There is one event type (`FieldResolutionApplied`) that is not explicitly handled and falls through to the permissive wildcard default. The fail-open wildcard default is a conscious design choice for forward compatibility but creates a risk that new event types are never explicitly categorized. Confidence is HIGH.

## Warnings

### [72-73] Fail-open wildcard default passes unknown event types unconditionally

**What:** The wildcard `case _: return True` means any event type not explicitly listed will always be emitted, regardless of granularity setting. This includes both future event types and the existing `FieldResolutionApplied` event.

**Why it matters:** The fail-open default means that if a developer adds a new high-volume event type (e.g., a per-field validation event) and forgets to add it to the filtering, it will be emitted at all granularity levels including LIFECYCLE. For a LIFECYCLE-only configuration expecting ~10-20 events per run, an un-categorized high-frequency event could generate thousands of unexpected events, overwhelming exporters.

The comment says "forward compatibility" but ELSPETH's No Legacy Code policy suggests that new events should be added with explicit filtering, not relied upon to fall through correctly. The fail-open approach optimizes for not losing events at the cost of potential event storms.

**Evidence:**
```python
# Unknown event types: pass through (forward compatibility)
case _:
    return True
```

### [58-73] `FieldResolutionApplied` not explicitly categorized

**What:** `FieldResolutionApplied` is imported by the orchestrator and emitted during source processing, but it does not appear in any match case in `should_emit()`. It falls through to the wildcard default and is always emitted.

**Why it matters:** `FieldResolutionApplied` is logically a lifecycle event (emitted once per run during source initialization). It should be in the lifecycle match case alongside `RunStarted`, `RunFinished`, and `PhaseChanged`. The current behavior (always emit) happens to be correct for a lifecycle event, but it is not intentionally correct -- it is accidentally correct via the wildcard. If the wildcard default were changed to `False`, this event would silently stop being emitted.

**Evidence:**
```python
# Lifecycle events: always emit at any granularity
case RunStarted() | RunFinished() | PhaseChanged():
    return True
# FieldResolutionApplied is NOT listed here but IS a lifecycle-level event
```

## Observations

### [58-69] Match/case pattern is clean and correct

**What:** The structural pattern matching correctly maps event types to granularity tiers:
- Lifecycle events (RunStarted, RunFinished, PhaseChanged): always emit
- Row events (RowCreated, TransformCompleted, GateEvaluated, TokenCompleted): ROWS or FULL
- External call events (ExternalCallCompleted): FULL only

**Why it matters:** Positive finding -- the mapping is correct and the hierarchical granularity (LIFECYCLE < ROWS < FULL) is properly implemented.

### [64-65] Granularity check uses `in` tuple, not ordered comparison

**What:** Row events check `granularity in (TelemetryGranularity.ROWS, TelemetryGranularity.FULL)` rather than `granularity >= TelemetryGranularity.ROWS`. Since `TelemetryGranularity` is a `str` enum, ordered comparison would use string ordering (alphabetical), which would be incorrect (`"full" < "lifecycle" < "rows"`).

**Why it matters:** Positive finding -- using explicit `in` tuple avoids the trap of relying on enum ordering. The granularity levels are semantically ordered (LIFECYCLE < ROWS < FULL) but their string values are not alphabetically ordered, so `>=` comparison would produce wrong results.

### Function is pure and stateless

**What:** `should_emit()` is a pure function with no side effects, no state, and no I/O. It takes an event and a granularity level and returns a boolean.

**Why it matters:** Positive finding -- pure functions are easy to test, reason about, and thread-safe by nature.

### No import of FieldResolutionApplied

**What:** The filtering module imports `RunStarted`, `RunFinished`, `PhaseChanged`, `RowCreated`, `ExternalCallCompleted` from the telemetry events module, but does not import `FieldResolutionApplied`. This confirms the missing case is an oversight, not an intentional omission.

**Why it matters:** Reinforces the finding that `FieldResolutionApplied` should be added to the lifecycle match case.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** Add `FieldResolutionApplied` to the lifecycle events match case and import it from `telemetry/events`. Consider whether the fail-open wildcard default is the right choice for this project -- a fail-closed default with explicit categorization of all event types would be more consistent with ELSPETH's "no silent assumptions" philosophy and could use an assertion or warning for uncategorized events.
**Confidence:** HIGH -- The logic is simple and fully understood. The missing event type is confirmed by import analysis.
