# Analysis: src/elspeth/telemetry/events.py

**Lines:** 175
**Role:** Defines telemetry event dataclasses for pipeline observability. Events are grouped into lifecycle (RunStarted, RunFinished, PhaseChanged, FieldResolutionApplied), row-level (RowCreated), and external call (ExternalCallCompleted) categories. All inherit from `TelemetryEvent` (defined in `contracts/events.py`).
**Key dependencies:** Imports `CallStatus`, `CallType`, `RunStatus` from `contracts/enums`, and `PhaseAction`, `PipelinePhase`, `TelemetryEvent` from `contracts/events`. Imported by `telemetry/filtering.py`, `plugins/context.py`, `plugins/clients/llm.py`, `plugins/clients/http.py`, `engine/orchestrator/core.py`.
**Analysis depth:** FULL

## Summary

Clean, well-structured dataclass definitions with proper use of frozen/slots for immutability and thread safety. The `ExternalCallCompleted.__post_init__` XOR validation is correct and important. One design observation regarding `FieldResolutionApplied` carrying potentially large mapping data and one missing event type for the filtering module. Confidence is HIGH.

## Warnings

### [80-97] FieldResolutionApplied carries unbounded `resolution_mapping` dict

**What:** The `resolution_mapping: dict[str, str]` field contains the complete original-to-normalized field mapping from source ingestion. For sources with hundreds or thousands of columns, this dict can be large.

**Why it matters:** Since telemetry events are frozen dataclasses queued for export, a large resolution mapping sits in memory in the queue and gets serialized by every exporter. For sources with wide schemas (e.g., 500+ column CSV files or wide database tables), this could consume non-trivial memory in the telemetry queue. This is a telemetry event, not an audit record, so the cost/benefit of carrying the full mapping should be considered.

**Evidence:**
```python
@dataclass(frozen=True, slots=True)
class FieldResolutionApplied(TelemetryEvent):
    source_plugin: str
    field_count: int
    normalization_version: str | None
    resolution_mapping: dict[str, str]  # Could be very large
```

### [167-175] `__post_init__` XOR validation runs on frozen dataclass -- correct but has an interaction note

**What:** `ExternalCallCompleted.__post_init__` validates that exactly one of `state_id` or `operation_id` is set. With `frozen=True`, `__post_init__` runs after `__init__` but before the object is returned, so it correctly prevents construction of invalid instances.

**Why it matters:** This is correct behavior. However, the XOR check `has_state == has_operation` evaluates to True when both are True OR both are False -- this correctly catches both the "neither set" and "both set" cases. The logic is sound but the boolean equality trick is non-obvious. A comment explaining `both True or both False` is already present on line 171, which is good.

**Evidence:**
```python
def __post_init__(self) -> None:
    has_state = self.state_id is not None
    has_operation = self.operation_id is not None
    if has_state == has_operation:  # Both True or both False
        raise ValueError(...)
```

## Observations

### [103-104] Row-level events split across two modules

**What:** The comment on line 103 notes that `TransformCompleted`, `GateEvaluated`, and `TokenCompleted` were moved to `contracts/events.py` because they cross the engine/telemetry boundary. Meanwhile, `RowCreated` remains in this file.

**Why it matters:** The split is documented and has a clear rationale (cross-boundary events live in contracts). However, `RowCreated` is also used by the engine (via orchestrator imports), so the distinction of which row-level events belong in contracts vs. telemetry could be clearer. This is a minor organizational note, not a defect.

### Missing `FieldResolutionApplied` from filtering.py

**What:** The `should_emit` function in `filtering.py` does not explicitly handle `FieldResolutionApplied` events. Since `FieldResolutionApplied` is not listed in any of the match cases in `filtering.py`, it falls through to the wildcard `case _: return True` default.

**Why it matters:** `FieldResolutionApplied` is a lifecycle-adjacent event (happens once per run during source initialization). The fall-through to `True` means it is always emitted regardless of granularity, which is likely correct for a lifecycle-level event, but it is not explicitly documented in the filtering logic. If a future maintainer adds a restrictive default case (e.g., `case _: return False`), this event would silently stop being emitted.

### [163-165] Optional payload fields on ExternalCallCompleted could carry sensitive data

**What:** `request_payload` and `response_payload` are `dict[str, Any] | None` fields that can contain full LLM prompts, HTTP request bodies, and response content.

**Why it matters:** These payloads may contain PII or sensitive data that flows through telemetry exporters to external observability platforms (OTLP, Datadog, Azure Monitor). The payloads are only populated at `FULL` granularity (filtered by `should_emit`), but there is no scrubbing or redaction mechanism at the event level. This is likely acceptable given that FULL granularity is opt-in, but operators should be aware that enabling FULL granularity sends complete request/response data to telemetry backends.

### Frozen dataclass with mutable default (dict)

**What:** `ExternalCallCompleted` has fields `request_payload: dict[str, Any] | None = None`, `response_payload: dict[str, Any] | None = None`, and `token_usage: dict[str, int] | None = None`. The defaults are `None` (immutable), which is correct. However, callers constructing these events pass mutable dicts that become frozen into the dataclass.

**Why it matters:** Since the dataclass is `frozen=True`, the reference cannot be reassigned, but the dict contents could theoretically be mutated by the caller after construction. In practice, the events are created inline with dict literals in the client code (`plugins/clients/llm.py`, `plugins/clients/http.py`), so mutation is unlikely. The `slots=True` attribute further restricts attribute assignment. This is a theoretical concern, not a practical one.

## Verdict

**Status:** SOUND
**Recommended action:** No immediate action required. Consider adding `FieldResolutionApplied` to the explicit lifecycle match case in `filtering.py` for clarity and forward-safety. Consider whether `resolution_mapping` should be truncated or summarized for wide-schema sources.
**Confidence:** HIGH -- Dataclass definitions are straightforward, the XOR validation is correct, and the frozen/slots pattern ensures thread safety. No bugs found.
