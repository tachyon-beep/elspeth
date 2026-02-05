# Analysis: src/elspeth/telemetry/exporters/otlp.py

**Lines:** 417
**Role:** OpenTelemetry Protocol exporter -- converts ELSPETH TelemetryEvents to OTLP spans and ships them via gRPC to any compatible backend (Jaeger, Tempo, Honeycomb, etc.). Also defines `_SyntheticReadableSpan`, a shared utility class reused by the Azure Monitor exporter.
**Key dependencies:** Imports `structlog`, `hashlib`, `json`, `rfc8785` (none -- not used here), `dataclasses.asdict`, `datetime`, `enum`. Imports `TelemetryExporterError` from `elspeth.telemetry.errors`. Conditionally imports `OTLPSpanExporter` from `opentelemetry.exporter.otlp.proto.grpc.trace_exporter`. Imported by `azure_monitor.py` (reuses `_derive_trace_id`, `_derive_span_id`, `_SyntheticReadableSpan`). Used by `TelemetryManager` via `ExporterProtocol`.
**Analysis depth:** FULL

## Summary

This file is generally well-structured and follows the ExporterProtocol contract correctly. The biggest concern is a **potential span ID collision risk** under high-throughput scenarios due to the deterministic derivation strategy using timestamp granularity. There is also a **sensitive data leakage vector** where header values (including Authorization tokens) could appear in debug logs or error messages. The `_SyntheticReadableSpan` approach is clever but tightly coupled to the OpenTelemetry SDK internal API, creating fragility across SDK version upgrades.

## Critical Findings

### [64-66] Span ID derivation uses hasattr/getattr -- violates prohibition on defensive patterns

**What:** `_derive_span_id` uses `hasattr(event, field_name)` and `getattr(event, field_name)` to probe for optional fields. The CLAUDE.md prohibition on defensive programming patterns states that `hasattr` and `getattr` should not be used to suppress errors from nonexistent attributes.

**Why it matters:** This is a borderline case. The telemetry events are frozen dataclasses defined in `contracts/events.py` and `telemetry/events.py`. Different event subtypes have different fields (`token_id`, `state_id`, `row_id`, `node_id`). The function handles multiple event types polymorphically, so `hasattr` here is genuinely checking structural variance across typed dataclasses rather than hiding a bug. However, the pattern could be replaced with a more explicit approach using `dataclasses.fields()` or a protocol.

**Evidence:**
```python
for field_name in ("token_id", "state_id", "row_id", "node_id"):
    if hasattr(event, field_name):
        value = getattr(event, field_name)
```

This is a judgment call -- the use is arguably legitimate for polymorphic dispatch over known dataclass subtypes, but it could be made more explicit.

## Warnings

### [60-72] Span ID collision risk under high throughput

**What:** `_derive_span_id` builds its unique identifier from `[event_class_name, timestamp_as_float, optional_identifying_fields]`. The timestamp is converted via `event.timestamp.timestamp()` which returns a `float` with microsecond precision. If two events of the same type occur at the same microsecond with the same identifying fields, they will produce the same span ID.

**Why it matters:** In high-throughput pipelines processing thousands of rows per second, or when events are batched with identical timestamps, this could produce duplicate span IDs within the same trace. OTLP backends handle duplicate span IDs differently -- some deduplicate (losing data), some reject the batch, some silently overwrite. Any of these outcomes corrupts the telemetry view.

**Evidence:**
```python
id_parts = [type(event).__name__, str(event.timestamp.timestamp())]
```
The `str(event.timestamp.timestamp())` call produces at most microsecond resolution (e.g., `"1705312200.123456"`). Two `TransformCompleted` events for different rows at the same microsecond but with different `node_id` values would still collide if the other identifying fields are absent.

### [168-173] Authorization headers logged at debug level

**What:** The `configure` method logs `headers_count=len(self._headers)` which is safe, but the `self._headers` dict itself is stored with raw values including potential `Authorization: Bearer <token>` values. If any future logging change or exception traceback exposes `self._headers`, the token would leak.

**Why it matters:** The current code is safe in this specific method, but the raw header dict persists as `self._headers` for the lifetime of the exporter. If a future contributor adds error logging that includes the exporter's state, or if an exception traceback from `OTLPSpanExporter` includes the headers argument, secrets could leak to log aggregation systems.

**Evidence:**
```python
self._headers = config.get("headers", {})
# ...
self._span_exporter = OTLPSpanExporter(
    endpoint=self._endpoint,
    headers=tuple(self._headers.items()) if self._headers else None,
)
```
The headers are passed to the SDK and also retained in `self._headers`. No HMAC fingerprinting or redaction is performed.

### [141] No type validation on config values

**What:** The `configure` method uses `config.get("batch_size", 100)` and `config.get("headers", {})` without validating types. If `batch_size` is a string `"100"`, the `< 1` check on line 145 would raise a `TypeError` rather than a clear `TelemetryExporterError`. Similarly, if `headers` is not a dict, `self._headers.items()` would fail later. Compare this with the Azure Monitor exporter which validates types for every config parameter.

**Why it matters:** Configuration errors during `configure()` should produce clear `TelemetryExporterError` messages. Untyped config values can produce confusing `TypeError` or `AttributeError` exceptions that are harder to diagnose.

**Evidence:** The Azure Monitor exporter (same codebase) validates every config value type explicitly. The OTLP exporter does not validate `batch_size` type, `headers` type, `endpoint` type, or `flush_interval_ms` type.

### [364-368] Conditional base class pattern is fragile

**What:** `_SyntheticReadableSpan` conditionally inherits from either `ReadableSpan` (when OpenTelemetry SDK is installed) or `object` (when it's not). When the base is `object`, the `super().__init__()` call on line 400 would fail because `object.__init__` doesn't accept keyword arguments.

**Why it matters:** If someone imports `otlp.py` in a context where OpenTelemetry is not installed (e.g., when `azure_monitor.py` imports the helper functions), the class definition succeeds but instantiation would crash. The Azure Monitor exporter imports `_SyntheticReadableSpan` at the module level, meaning if OpenTelemetry is not installed, the Azure Monitor exporter import also fails at span creation time.

**Evidence:**
```python
try:
    from opentelemetry.sdk.trace import ReadableSpan as _ReadableSpanBase
except ImportError:
    _ReadableSpanBase = object  # type: ignore[misc,assignment]
```
When `_ReadableSpanBase = object`, `super().__init__(name=name, context=context, ...)` would raise `TypeError: object.__init__() takes exactly one argument (the instance to initialize)`.

### [109] flush_interval_ms documented but not implemented

**What:** `_flush_interval_ms` is accepted as a config parameter and stored, but never used anywhere. The docstring acknowledges this: "Note: Time-based flushing is not currently implemented."

**Why it matters:** Users may configure `flush_interval_ms` expecting time-based flushing behavior and get no effect. Events will only flush on `batch_size` threshold or explicit `flush()` calls. In a pipeline that produces events slowly (e.g., 1 event per minute with batch_size=100), events could sit in the buffer for over an hour before being exported.

**Evidence:**
```python
self._flush_interval_ms: int = 5000  # Documented but not implemented
```

## Observations

### [308] asdict performs deep copy -- performance concern at high volume

`dataclasses.asdict(event)` creates a deep copy of all event fields including nested dicts and datetimes. At high telemetry volumes, this creates significant GC pressure. Since events are frozen dataclasses, a shallow extraction would suffice.

### [219-234] Buffer cleared in finally block even on export failure

This is correct behavior -- the buffer is cleared whether export succeeds or fails, preventing infinite retry of the same batch. This is well-implemented.

### [99] Thread safety disclaimer accurate but important

The docstring correctly states "Assumes single-threaded access. Buffer is not thread-safe." The `TelemetryManager` calls `export()` exclusively from the export thread, so this is safe in the current architecture. However, this would break if someone called `export()` directly from multiple threads.

### Code duplication with azure_monitor.py

The `_serialize_event_attributes` method on lines 293-327 is duplicated almost identically in `azure_monitor.py` lines 321-360. The Azure Monitor exporter imports `_derive_trace_id`, `_derive_span_id`, and `_SyntheticReadableSpan` from this file, but does not reuse the serialization method.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** (1) Add type validation for config parameters (`batch_size`, `headers`, `endpoint`) to match the validation rigor of the Azure Monitor exporter. (2) Consider adding a nonce or sequence number to `_derive_span_id` to reduce collision risk. (3) Extract the duplicated `_serialize_event_attributes` into a shared utility. (4) Either implement `flush_interval_ms` or remove it from the accepted config to prevent user confusion.
**Confidence:** HIGH -- Full analysis with complete context from protocol, manager, factory, events, and test files.
