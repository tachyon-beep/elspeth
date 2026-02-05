# Analysis: src/elspeth/contracts/events.py

**Lines:** 194
**Role:** Defines observability event types for the pipeline event bus. These events are emitted by the orchestrator/engine and consumed by CLI formatters (for human-readable output) and telemetry exporters (for external observability platforms). Includes lifecycle events (PhaseStarted/Completed/Error), run summary, and row-level telemetry events (TransformCompleted, GateEvaluated, TokenCompleted).
**Key dependencies:** Imports enums from `elspeth.contracts.enums` (NodeStateStatus, RoutingMode, RowOutcome). Consumed by `engine/orchestrator/core.py`, `telemetry/events.py`, `telemetry/exporters/*`, `cli.py`, and many test files (~31 consumers).
**Analysis depth:** FULL

## Summary

This file defines clean, immutable dataclass event types with good documentation. The types serve as the contract between the engine (producer) and observability systems (consumers). The code is well-structured with frozen+slots dataclasses for thread safety and memory efficiency. There are no critical issues. The main observations relate to design completeness: `RunSummary` lacks a `forked` count, `TelemetryEvent` stores `datetime` but does not enforce UTC, and `PhaseError` stores a `BaseException` which may cause issues with serialization.

## Critical Findings

None.

## Warnings

### [Lines 99-101] PhaseError stores BaseException which complicates serialization and telemetry export

**What:** `PhaseError` stores the full `BaseException` object as `error: BaseException`. While the docstring explains this preserves traceback and chained causes, `BaseException` objects are not JSON-serializable and may hold references to large frame objects, preventing garbage collection.

**Why it matters:** Telemetry exporters that consume these events must handle the non-serializable `BaseException`. If any exporter attempts to serialize `PhaseError` without special handling, it will fail. Additionally, storing the exception object keeps the entire traceback chain alive in memory, which can prevent garbage collection of local variables in the exception frames.

**Evidence:**
```python
@dataclass(frozen=True, slots=True)
class PhaseError:
    phase: PipelinePhase
    error: BaseException  # Not JSON-serializable, holds frame references
    target: str | None = None

    @property
    def error_message(self) -> str:
        return str(self.error)
```

The `error_message` property provides a serializable alternative, but the event itself carries the live exception. Consumers must know to use `error_message` for serialization and `error` for debugging.

### [Lines 140-153] TelemetryEvent.timestamp is datetime but UTC is not enforced

**What:** `TelemetryEvent` declares `timestamp: datetime` without any constraint on timezone awareness. The docstring says "When the event occurred (UTC)" but there is no runtime enforcement.

**Why it matters:** If any event producer creates a `TelemetryEvent` with `datetime.now()` (naive local time) instead of `datetime.now(timezone.utc)` or `datetime.utcnow()`, the timestamp will be in local time while being described as UTC. Telemetry consumers may then compute incorrect durations or display wrong times. In distributed systems, timezone mismatches are a common source of subtle bugs.

**Evidence:**
```python
@dataclass(frozen=True, slots=True)
class TelemetryEvent:
    """Base class for all telemetry events.

    All events include:
    - timestamp: When the event occurred (UTC)  # <-- docstring says UTC
    """
    timestamp: datetime  # <-- no enforcement of timezone awareness
    run_id: str
```

### [Lines 109-131] RunSummary counts do not cover all terminal states

**What:** `RunSummary` tracks `succeeded`, `failed`, `quarantined`, and `routed` counts. However, the `RowOutcome` enum defines additional terminal states: `FORKED`, `CONSUMED_IN_BATCH`, `COALESCED`, and `EXPANDED`. These are not tracked in the summary.

**Why it matters:** The sum `succeeded + failed + quarantined + routed` will not equal `total_rows` when the pipeline uses fork/join, aggregation, or deaggregation patterns. This could confuse CI integration consumers who check `exit_code` against row counts for validation.

**Evidence:**
```python
@dataclass(frozen=True, slots=True)
class RunSummary:
    total_rows: int
    succeeded: int     # COMPLETED outcome
    failed: int        # FAILED outcome
    quarantined: int   # QUARANTINED outcome
    routed: int = 0    # ROUTED outcome
    # Missing: FORKED, CONSUMED_IN_BATCH, COALESCED, EXPANDED
```

## Observations

### [Lines 57-80] PhaseStarted provides good observability contract

The `PhaseStarted` event with `PipelinePhase`, `PhaseAction`, and optional `target` provides a clean observability contract. The docstring at lines 59-76 comprehensively documents each phase. This is good design.

### [Lines 156-172] TransformCompleted allows None hashes for edge cases

The optional `input_hash` and `output_hash` fields on `TransformCompleted` are well-documented: failed transforms may not produce output, and error handling edge cases may not compute input hash. This is a pragmatic design choice that avoids forcing sentinel values.

### [Lines 19-25] PipelinePhase enum uses (str, Enum) pattern consistently

The `PipelinePhase`, `PhaseAction`, and `RunCompletionStatus` enums all use the `(str, Enum)` pattern for serialization consistency. This matches the established pattern in `contracts/enums.py`.

### [Lines 187-194] TokenCompleted has optional sink_name

`TokenCompleted` has `sink_name: str | None` because not all terminal outcomes involve a sink (e.g., FORKED, CONSUMED_IN_BATCH). This is correct.

### No `__post_init__` validation on RunSummary

`RunSummary` does not validate that `succeeded + failed + quarantined <= total_rows` or that `exit_code` is consistent with the `status` field (e.g., `exit_code=0` implies `status=COMPLETED`). Adding a `__post_init__` check would catch producer bugs early.

### No slots on url.py dataclasses but slots used here consistently

All dataclasses in this file use `slots=True` for memory efficiency. This is a good pattern for event objects that may be created in high volume.

## Verdict

**Status:** SOUND
**Recommended action:** Consider adding a `__post_init__` to `TelemetryEvent` that validates `timestamp` is timezone-aware (or documents that naive datetimes are acceptable). The `RunSummary` row count gap is a known consequence of the DAG model and could be documented with a comment. No urgent changes required.
**Confidence:** HIGH -- events are simple data carriers with no complex logic. The observations are design considerations, not bugs.
