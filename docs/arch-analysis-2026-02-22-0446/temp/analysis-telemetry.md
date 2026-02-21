# Telemetry Subsystem Architecture Analysis

**Date:** 2026-02-22
**Branch:** RC3.3-architectural-remediation
**Analyst:** Claude (architectural review pass)
**Confidence:** High — all 10 telemetry files read in full; contracts, event types, and engine wiring examined.

---

## File-by-File Analysis

### 1. `telemetry/manager.py` — TelemetryManager

**Purpose:** Central hub that receives `TelemetryEvent` objects from the engine (via `handle_event()`), filters them by granularity, queues them for async export via a background thread, dispatches to all configured exporters with per-exporter failure isolation, and tracks health metrics.

**Key classes/functions:**

- `HealthMetrics` (TypedDict): Typed snapshot of operational counters — emitted count, dropped count, per-exporter failure counts, consecutive total failures, queue depth and max. Correctly annotated as Tier 1 (our data).
- `TelemetryManager.__init__()`: Starts a non-daemon background export thread (`telemetry-export`), waits for a ready signal (5s timeout) before returning.
- `_export_loop()`: Consumes from queue until `None` sentinel arrives; calls `_dispatch_to_exporters()` per event; calls `task_done()` in a `finally` block covering all code paths including sentinel.
- `_dispatch_to_exporters()`: Iterates exporters with per-exporter `try/except`; tracks partial vs. total failure; increments `_events_dropped` under `_dropped_lock` on total failure; logs aggregate drops every `_LOG_INTERVAL=100` failures; raises `TelemetryExporterError` or disables telemetry when `max_consecutive_failures` is exceeded.
- `handle_event()`: Thread-safe entry point. Checks shutdown, disabled flag, empty exporters, granularity filter, thread readiness, and thread liveness before queuing. In BLOCK mode uses a 30s timeout to prevent permanent deadlock. In DROP mode calls `_drop_oldest_and_enqueue_newest()`.
- `_drop_oldest_and_enqueue_newest()` + `_requeue_shutdown_sentinel_or_raise()`: DROP mode overflow eviction with careful handling of the shutdown sentinel to prevent the export thread from missing its exit signal.
- `flush()`: `queue.join()` + stored exception re-raise + per-exporter `flush()` with logged errors.
- `close()`: Drains queue to guarantee sentinel delivery, joins thread with 5s timeout, closes exporters. Shutdown order is documented and correct (sentinel before join).

**Dependencies:** `queue`, `threading`, `structlog`, `contracts.config.RuntimeTelemetryProtocol`, `contracts.config.defaults.INTERNAL_DEFAULTS`, `contracts.enums.BackpressureMode`, `contracts.events.TelemetryEvent`, `telemetry.errors.TelemetryExporterError`, `telemetry.filtering.should_emit`, `telemetry.protocols.ExporterProtocol`.

**Error handling:** Solid. The export loop catches `TelemetryExporterError` separately from generic `Exception` (for stored re-raise on `fail_on_total=True`). Both branches log but don't propagate. `handle_event()` catches queue overflow explicitly and logs. Every drop path goes through `_dropped_lock` and the aggregate logging threshold.

**Concerns:**

1. **`_dispatch_to_exporters()` uses `self._exporter_failures.get(exporter.name, 0)`**: This is a `.get()` on a dict we own and write ourselves — a mild defensive-programming violation. Should be `self._exporter_failures[exporter.name] = self._exporter_failures.get(...)` or simply initialized with defaultdict. Neither crashes anything here, but it is inconsistent with the codebase's stated prohibition on `.get()` on internal state. Low severity.

2. **Partial failure does not count against `_consecutive_total_failures`**: When only some (not all) exporters fail, the counter resets to zero and the event counts as `emitted`. This is intentional and documented (comment: "at least one exporter worked"), but it means a scenario where one exporter always succeeds while another always fails will never trigger the failure ceiling — per-exporter health is tracked but does not independently disable a broken exporter. This is a policy gap, not a bug.

3. **`_exporter_failures` dict is read by `health_metrics` without holding `_dropped_lock`**: The docstring notes "approximately consistent," which is acceptable for monitoring data. However `_exporter_failures` is written exclusively by the export thread and read from any thread calling `health_metrics`. On CPython with the GIL this is safe, but technically there is no memory barrier. This is unlikely to matter in practice.

4. **`_requeue_shutdown_sentinel_or_raise()` complexity**: The sentinel requeue logic is necessary but intricate — a bounded retry loop that displaces items from the queue when full, tracking `task_done()` accounting. This is the hardest piece of the manager to reason about. It has a bounded iteration limit and defers to the export thread's join timeout if it ultimately fails (logs a warning). The logic is correct but fragile — any future changes to queue accounting must be made carefully.

5. **Queue size comes from `INTERNAL_DEFAULTS["telemetry"]["queue_size"]`**: This is a dict access on our own defaults dict. A misconfigured/missing key would crash at startup with a `KeyError`. Per the trust model, this is correct (our data, should crash). It is fine.

---

### 2. `telemetry/factory.py` — create_telemetry_manager

**Purpose:** Bridges `RuntimeTelemetryConfig` to a fully-initialized `TelemetryManager`. Handles pluggy-based exporter discovery, name resolution, class instantiation, and configuration.

**Key functions:**

- `_resolve_exporter_name()`: Prefers `_name` class attribute (avoids needless instantiation); falls back to instantiating and calling `.name`; validates that the result is a non-empty string.
- `_discover_exporter_registry()`: Creates a fresh `PluginManager`, registers `BuiltinExportersPlugin` plus any caller-supplied plugins, calls `elspeth_get_exporters`, validates the return value (not None, not str/bytes, is iterable), populates a `name -> class` registry with duplicate detection.
- `create_telemetry_manager()`: Returns `None` if `config.enabled=False` (logs at DEBUG); discovers registry; iterates `config.exporter_configs`; raises `TelemetryExporterError` on unknown names; calls `exporter.configure(options)` on each; warns if telemetry is enabled but no exporters are configured; returns `TelemetryManager`.

**Dependencies:** `pluggy`, `structlog`, `contracts.config.RuntimeTelemetryConfig`, `telemetry.errors`, `telemetry.exporters.BuiltinExportersPlugin`, `telemetry.hookspecs`, `telemetry.manager`, `telemetry.protocols`.

**Error handling:** All plugin registration failures and hook call failures are wrapped in `TelemetryExporterError` with context. Missing/invalid exporter names raise at factory time (not runtime). The `pragma: no cover` comments on two defensive branches (plugin without `__name__`, instantiation failure) are legitimate — these are external plugin code boundaries and require runtime defense even though they cannot be easily triggered in unit tests.

**Concerns:**

1. **`exporter.configure(options)` passes `MappingProxyType` from `ExporterConfig.options`**: The exporters all type-hint `config: Mapping[str, Any]` and call `.get()` on it (which `MappingProxyType` supports). This works correctly, but it means the type received by exporters is actually a `MappingProxyType`, not a plain `dict`. The `isinstance(config, dict)` checks in exporters would fail if any exporter tested for `dict` specifically. None currently do, so this is not a live bug — but it is a subtle coupling.

2. **`_discover_exporter_registry()` calls hooks by direct attribute access**: `hook_fn = hook_plugin.elspeth_get_exporters` then `hook_fn()` — this bypasses pluggy's normal hook calling machinery (`plugin_manager.hook.elspeth_get_exporters()`). The result is functionally equivalent since pluggy hooks are just methods, but it is non-idiomatic. The pluggy API approach would be cleaner.

3. **`create_telemetry_manager()` returns `TelemetryManager | None`**: Callers that receive `None` get no telemetry with no indication of why at call site. The `logger.debug(reason="config.enabled=False")` is the only signal. If `enabled=True` but no exporters are configured, the manager is still created (with empty exporter list) and logs a warning. This is correct behavior but may surprise callers who expect a `None` return when telemetry has no effect.

---

### 3. `telemetry/filtering.py` — should_emit

**Purpose:** Single-source-of-truth for granularity-based event filtering. Used by `TelemetryManager.handle_event()` before queuing.

**Key function:**

- `should_emit(event, granularity)`: Structural pattern match (`match`/`case`) on event type:
  - `RunStarted | RunFinished | PhaseChanged` → always `True` (lifecycle, any granularity)
  - `RowCreated | TransformCompleted | GateEvaluated | TokenCompleted | FieldResolutionApplied` → `True` at ROWS or FULL
  - `ExternalCallCompleted` → `True` only at FULL
  - `_` (unknown) → `True` (fail-open for forward compatibility)

**Dependencies:** `contracts.enums.TelemetryGranularity`, `contracts.events` (all 9 event types).

**Error handling:** No exceptions possible. The fail-open default for unknown event types is documented and intentional — new events are visible immediately without filter updates.

**Concerns:**

1. **Fail-open for unknown event types is a forward-compatibility policy, not a safety concern.** It means any new `TelemetryEvent` subclass added to `contracts/events.py` will automatically pass through at all granularity levels until `filtering.py` is explicitly updated. This is the correct tradeoff — better to emit an unexpected event than to silently drop it. But it means operators may see unexpected event types in their observability platforms when new events are added. This should be noted in the filter update checklist when new events are introduced.

2. **Pattern match on concrete types, not on granularity levels**: The filter is expressed as "which event types are in which granularity bucket." Adding a new granularity level (e.g., `MINIMAL`) would require updating this match. The three-level granularity model is simple and well-defined, so this is low risk currently.

---

### 4. `telemetry/hookspecs.py` — ElspethTelemetrySpec

**Purpose:** Defines the pluggy hookspec for telemetry exporter discovery. Single hook: `elspeth_get_exporters()` returns a list of exporter classes.

**Key class:**

- `ElspethTelemetrySpec`: Hookspec class with one `@hookspec`-decorated method.
- Reuses `PROJECT_NAME = "elspeth"` — same namespace as the main plugin system.

**Dependencies:** `pluggy`.

**Error handling:** N/A (hookspec is a declaration, not behavior).

**Concerns:**

1. **Shared `PROJECT_NAME` with the main plugin system**: Both telemetry and the main pipeline plugin system use `"elspeth"` as the pluggy namespace. The factory creates a fresh `PluginManager` per call to `_discover_exporter_registry()`, so there is no cross-contamination at runtime. However, if a component ever tried to use a single shared `PluginManager` for both systems, the namespace collision would cause silent hookspec interference. The current pattern (fresh manager per use) is safe.

2. **`hookimpl` is exported from this module for exporter plugins to import**: Correct and idiomatic. The comment on `elspeth_get_exporters` clarifies that the empty body is a pluggy convention (`# pluggy hookspec: body provided by implementations`). The `type: ignore[empty-body]` comment is correct.

---

### 5. `telemetry/protocols.py` — ExporterProtocol

**Purpose:** Defines the `ExporterProtocol` runtime-checkable Protocol that all exporters must satisfy. Specifies the five-method lifecycle contract: `name`, `configure()`, `export()`, `flush()`, `close()`.

**Key class:**

- `ExporterProtocol`: `@runtime_checkable` Protocol. Critically documents that `export()` MUST NOT raise, `configure()` MUST raise on invalid config, and `close()` MUST be idempotent.

**Dependencies:** `typing.Protocol`, `contracts.events.TelemetryEvent` (TYPE_CHECKING only).

**Error handling:** Documented in docstring rather than enforced. The protocol cannot enforce the "must not raise" contract at the type level — it is a behavioral contract.

**Concerns:**

1. **`export()` "MUST NOT raise" is documented but not mechanically enforced.** A defective exporter that raises from `export()` will have its exception caught by `_dispatch_to_exporters()` in the manager — so the system is safe in practice. But a new exporter author who forgets the contract will get silent swallowing at the manager level rather than a helpful error. This is the correct tradeoff (telemetry must not crash the pipeline), and the docstring is clear. No action needed, but onboarding docs for new exporters should emphasize this.

2. **Thread-safety contract is documented in `export()` docstring**: "export() is always called from the telemetry export thread, never concurrently with itself." This is accurate — the single background thread serializes all calls to `export()`. Exporters may safely use unsynchronized internal state in `export()`. However, `configure()` is called from the main thread and `close()` could also be called from the main thread. Exporters must not hold state that crosses the configure→export→close boundary on a single thread assumption. Current exporters are correctly designed for this.

---

### 6. `telemetry/errors.py` — TelemetryExporterError

**Purpose:** Single exception class for the telemetry subsystem. Used at configuration/initialization time, not during export.

**Key class:**

- `TelemetryExporterError(Exception)`: Two attributes — `exporter_name` (str) and `message` (str). `__init__` formats the message as `"Exporter '{name}' failed: {message}"`.

**Dependencies:** None.

**Error handling:** The class itself is the error boundary.

**Concerns:** None. Simple, clean, well-scoped.

---

### 7. `telemetry/exporters/otlp.py` — OTLPExporter

**Purpose:** Exports telemetry events via OpenTelemetry Protocol (OTLP gRPC) to any OTLP-compatible backend (Jaeger, Tempo, Datadog, Honeycomb, etc.). Converts `TelemetryEvent` objects to OTel spans post-hoc using `_SyntheticReadableSpan`.

**Key classes/functions:**

- `_derive_trace_id(run_id)`: SHA-256 of `run_id`, first 16 bytes → 128-bit int. All events from the same run share the same trace ID.
- `_generate_span_id()`: `secrets.randbits(64)` with non-zero guard. Replaced earlier deterministic approach that had collision risk.
- `OTLPExporter`: `configure()` validates required `endpoint` field and optional `headers`/`batch_size`; imports `OTLPSpanExporter` at configure time (ImportError → `TelemetryExporterError`). Buffers events until `batch_size`, then `_flush_batch()`. `export()` is exception-safe. `flush()`/`close()` wrapped in try/except.
- `_SyntheticReadableSpan(ReadableSpan)`: Subclass of OTel SDK `ReadableSpan` for direct construction. Handles the optional import with a fallback to `object` when opentelemetry is not installed.

**Dependencies:** `opentelemetry.exporter.otlp.proto.grpc`, `opentelemetry.sdk.trace`, `structlog`, `hashlib`, `secrets`.

**Error handling:** `configure()` raises `TelemetryExporterError` on missing `endpoint`, wrong types, or missing optional dep. `export()` catches all exceptions and logs. `_flush_batch()` uses `finally: self._buffer.clear()` so the buffer is always cleared even on export failure.

**Concerns:**

1. **`_SyntheticReadableSpan` fallback to `object`**: When opentelemetry is not installed, `_ReadableSpanBase = object`. At that point, `_SyntheticReadableSpan.__init__` still calls `super().__init__()` — which calls `object.__init__()`. The imports inside `__init__` (from opentelemetry.sdk.resources...) would then `ImportError`, raising at span construction time. Since `export()` wraps span construction in try/except, this would be logged and the event dropped rather than crashing the pipeline. However, `configure()` would also have failed at `OTLPSpanExporter` import, so in practice `_configured` would be `False` and `export()` would return early before ever constructing a span. The fallback to `object` is therefore only reachable in pathological testing scenarios.

2. **`_event_to_span()` assumes naive timestamps should be treated as UTC**: `event.timestamp.replace(tzinfo=UTC)`. This is a reasonable assumption (ELSPETH produces UTC timestamps) but is undocumented at the call site. If a timezone-aware timestamp from a non-UTC timezone were passed, the `else: ts = event.timestamp` branch preserves it correctly.

3. **Azure Monitor exporter reuses `_derive_trace_id`, `_generate_span_id`, and `_SyntheticReadableSpan` from this module** (private symbols prefixed with `_`). This creates a coupling where the Azure Monitor exporter imports private internals from the OTLP module. This is a code organization concern: these shared utilities should live in a shared `_span_utils.py` or similar within the exporters package rather than being "owned" by the OTLP exporter.

4. **Batch buffer cleared on `_flush_batch()` failure**: The `finally: self._buffer.clear()` in `_flush_batch()` means events are dropped on export failure rather than retried. This is the correct telemetry-first tradeoff (never accumulate unboundedly), but operators should be aware that OTLP transient failures lose the batch.

---

### 8. `telemetry/exporters/azure_monitor.py` — AzureMonitorExporter

**Purpose:** Exports telemetry events to Azure Monitor / Application Insights using the `azure-monitor-opentelemetry-exporter` package. Reuses OTLP's `_SyntheticReadableSpan` for span construction.

**Key class:**

- `AzureMonitorExporter`: `configure()` validates `connection_string` (required), `batch_size`, `service_name`, `service_version`, `deployment_environment`; creates OTel `Resource` and `TracerProvider` to work around the `ProxyTracerProvider.resource` AttributeError; instantiates `AzureMonitorTraceExporter` with explicit `tracer_provider`. `export()` buffers then flushes. `_serialize_event_attributes()` serializes dicts as JSON strings (Azure Monitor doesn't support nested attributes). Adds `cloud.provider=azure` and `elspeth.exporter=azure_monitor` attributes.
- `close()` flushes then shuts down the underlying exporter; sets `_azure_exporter = None` (idempotent).

**Dependencies:** `azure.monitor.opentelemetry.exporter`, `opentelemetry.sdk.resources`, `opentelemetry.sdk.trace`, `telemetry.exporters.otlp` (private symbols).

**Error handling:** `configure()` validates all config fields with explicit type checks. Import failures → `TelemetryExporterError`. `export()` and `_flush_batch()` are exception-safe. `flush()` wraps `_flush_batch()` in try/except.

**Concerns:**

1. **Private symbol import from OTLP module**: `from elspeth.telemetry.exporters.otlp import _derive_trace_id, _generate_span_id, _SyntheticReadableSpan`. These three symbols should be extracted to a shared internal utility module (e.g., `telemetry/exporters/_span_utils.py`). Currently the OTLP module effectively owns shared infrastructure used by Azure Monitor. This is a refactoring concern, not a correctness issue.

2. **`_flush_batch()` warning log on empty buffer** (line 245-248): Logs at DEBUG when buffer is empty — actually coded as `logger.debug(...)`. This is harmless but slightly noisy for normal flush-on-shutdown scenarios where the buffer is already empty.

3. **`_serialize_event_attributes()` mutates the dict returned by `event.to_dict()`**: The method calls `data = event.to_dict()` then adds `data["event_type"] = ...` to the returned dict. Since `to_dict()` returns a fresh dict, this mutation is safe. However, it differs from the OTLP exporter's `_serialize_event_attributes()` which builds a new `result` dict without mutating `data`. The Azure Monitor version mutates `data` for the `event_type` key then iterates `data.items()`, which is valid but stylistically inconsistent.

---

### 9. `telemetry/exporters/console.py` — ConsoleExporter

**Purpose:** Writes telemetry events to stdout/stderr in JSON or human-readable format. Development/debugging exporter.

**Key class:**

- `ConsoleExporter`: `configure()` validates `format` ("json"|"pretty") and `output` ("stdout"|"stderr") using `TypeGuard` functions for mypy narrowing. `export()` serializes event and calls `print()` — exception-safe. `_serialize_event()` handles datetime→ISO and Enum→value. `_extract_pretty_details()` uses `dataclasses.fields()` introspection to discover event-specific fields. `flush()` calls `self._stream.flush()` exception-safe. `close()` is intentional no-op (doesn't own stdout/stderr).

**Dependencies:** `sys`, `json`, `dataclasses`, `structlog`, `telemetry.errors`.

**Error handling:** Clean. All I/O wrapped in try/except.

**Concerns:**

1. **`_serialize_event()` mutates the dict from `event.to_dict()` in-place**: `data[key] = value.isoformat()` modifies the dict while iterating `data.items()`. In Python 3.7+ this is safe if no keys are added or removed — only values are changed. But it is fragile. The OTLP exporter's pattern of building a separate `result` dict is safer. Low risk in practice since `datetime` and `Enum` are always present in the same keys.

2. **`_extract_pretty_details()` uses `getattr(event, field_name)` on a known dataclass**: This is `getattr` on our own typed data. Given that `fields(event)` returns the actual field list of the event dataclass, the `getattr` here is guaranteed safe — every field returned by `dataclasses.fields()` must exist on the instance. This does not violate the prohibition on defensive programming; it is correct introspective use of the dataclass API.

---

### 10. `telemetry/exporters/datadog.py` — DatadogExporter

**Purpose:** Exports telemetry events to Datadog via the native `ddtrace` library. Each event becomes a Datadog span with event fields as tags.

**Key class:**

- `DatadogExporter`: `configure()` validates `service_name`, `env`, `version`, `agent_host`, `agent_port`; explicitly rejects `api_key` (agent-only mode); uses env-var scoping to configure ddtrace agent host/port at import time, then restores original env vars in `finally`. `export()` calls `_create_span_for_event()` in try/except. `_create_span_for_event()` creates a ddtrace span, sets explicit `start_ns` from event timestamp, sets tags via `_set_event_tags()`, and finishes the span in `finally` (ensures cleanup even if tag setting fails). `_set_tag_value()` recursively flattens dicts to dotted keys with a depth limit (`_MAX_TAG_DEPTH=5`). `flush()` calls `self._tracer.flush()`. `close()` calls flush + `self._tracer.shutdown()`.

**Dependencies:** `ddtrace`, `structlog`, `telemetry.errors`.

**Error handling:** Import failure at configure time → `TelemetryExporterError`. `export()` exception-safe. Span `finish()` in `finally` ensures spans are not leaked even on tag errors. `flush()` and `close()` exception-safe.

**Concerns:**

1. **Environment variable mutation during `configure()`**: ddtrace reads `DD_AGENT_HOST` and `DD_TRACE_AGENT_PORT` at import time. The code sets env vars, imports ddtrace, then restores originals in `finally`. This is correct but has two issues:
   - If ddtrace was already imported before this configure() call (e.g., in tests or if another component imported it), the env var mutation has no effect — ddtrace's connection config is already set from the earlier import.
   - The pattern is thread-unsafe: if two `DatadogExporter.configure()` calls happen concurrently (unlikely but possible in multi-agent scenarios), they would race on the env vars. Not a real-world concern given the sequential factory creation pattern, but worth noting.

2. **`_tracer` is the module-level ddtrace tracer singleton**: `from ddtrace import tracer` gives the global tracer. Setting `self._tracer = tracer` then later `self._tracer.shutdown()` shuts down the global ddtrace tracer. If any other component is also using ddtrace, this shutdown would break it. In ELSPETH's single-pipeline model this is fine; in multi-pipeline or test scenarios it could cause interference.

3. **`_create_span_for_event()` uses a `None` check guard before creating the span, but `export()` already guards on `self._configured and self._tracer is not None`**: The inner guard at line 232 (`if self._tracer is None: return`) is redundant given the outer guard in `export()`. Harmless, but slightly inconsistent.

4. **Dict flattening to dotted keys has max depth 5**: At depth 5, remaining structure is `str(value)`. This is a reasonable safeguard against unbounded recursion on pathological data, but it produces opaque string representations at deep nesting. The telemetry event data structures are not deeply nested in practice (typically 1-2 levels), so this limit is unlikely to trigger.

---

## Overall Architecture Analysis

### 1. Telemetry Architecture — Manager, Factory, Exporters

The architecture follows a clean layered pattern:

```
Engine (orchestrator/core.py)
    ↓ _emit_telemetry(event)
TelemetryManager (manager.py)
    ↓ filter by granularity (filtering.py)
    ↓ enqueue (thread-safe queue)
Background thread → _dispatch_to_exporters()
    ↓ for each exporter:
ExporterProtocol (protocols.py)
    ├── ConsoleExporter
    ├── OTLPExporter
    ├── AzureMonitorExporter
    └── DatadogExporter
```

The async queue decouples the pipeline thread from export latency. BLOCK mode provides backpressure; DROP mode provides isolation at the cost of data loss. The background thread serializes all exporter calls, so exporters need not be thread-safe within `export()`.

The factory (`factory.py`) creates the manager from config, handling the pluggy exporter discovery lifecycle. The exporter classes are system code (not user-provided), so the `TelemetryExporterError` at config/discovery time is correct for configuration problems. At runtime (export), exceptions are swallowed.

The manager correctly delineates its two concerns: "should I emit this event?" (filtering) and "deliver the event without failing the pipeline" (dispatch with isolation).

### 2. Hookspec Integration — How Telemetry Plugs Into the Engine

The engine integration is straightforward and correctly ordered:

1. `Orchestrator.__init__()` accepts an optional `TelemetryManager | None` parameter.
2. `_emit_telemetry(event)` wraps the `handle_event()` call with a `None` check — telemetry is a no-op when disabled.
3. `_flush_telemetry()` wraps `flush()` similarly.
4. Telemetry is emitted **after** Landscape recording at each event point — this ordering is documented and correct. The legal record (Landscape) is written first; operational visibility (telemetry) follows.
5. Telemetry flush occurs at run completion and also at specific lifecycle phase boundaries.
6. `TelemetryExporterError` from `flush()` (when `fail_on_total=True`) is allowed to propagate to the orchestrator, which treats it as a run failure.

The pluggy hookspecs (`hookspecs.py`) are used only for **exporter class discovery** at factory time, not for event dispatch. Event dispatch is direct method calls (`exporter.export(event)`), not pluggy hooks. This is the correct separation: pluggy is for registration/discovery, direct calls are for hot-path event processing.

### 3. Exporter Pattern — Shared Interface with Platform-Specific Implementations

All four exporters implement `ExporterProtocol` duck-typed (not explicitly subclassed — they satisfy the protocol structurally). The shared lifecycle is:

1. `__init__()`: Unconfigured, stores defaults.
2. `configure(config: Mapping[str, Any])`: Validates config, imports optional deps, initializes platform client.
3. `export(event)`: Buffer or send; must not raise.
4. `flush()`: Force-send buffer contents; exception-safe.
5. `close()`: Flush + release resources; idempotent.

The buffering exporters (OTLP, Azure Monitor) share the same buffer-and-batch pattern: append to `self._buffer`, flush when `len >= batch_size`. The unbuffered exporters (Console, Datadog) write/send immediately on each `export()` call.

The OTLP exporter provides `_derive_trace_id()`, `_generate_span_id()`, and `_SyntheticReadableSpan` as shared utilities that Azure Monitor also imports. This private-symbol sharing is a code organization smell that should be resolved.

**Duplication concern:** `_serialize_event_attributes()` is implemented independently in both `otlp.py` and `azure_monitor.py` with nearly identical logic (datetime → ISO, Enum → value, dict → JSON string, tuple → list). The only difference is that Azure Monitor adds a `cloud.provider=azure` attribute. This duplication should be extracted to a shared helper.

Similarly, `_set_event_tags()` in `datadog.py` handles the same type conversions but uses recursive dict flattening instead of JSON serialization. Three different serialization approaches for the same data — divergence risk as events evolve.

### 4. Filtering — Granularity-Based Event Selection

The `should_emit()` function in `filtering.py` is clean, exhaustive, and has a single responsibility. The three-tier granularity model (LIFECYCLE → ROWS → FULL) is well-designed:

- **LIFECYCLE**: Minimal overhead. `RunStarted`, `RunFinished`, `PhaseChanged` only.
- **ROWS**: Adds row-level events. Suitable for production monitoring.
- **FULL**: Adds external call events (`ExternalCallCompleted`). For debugging LLM/HTTP call performance.

The fail-open default for unknown event types (wildcard `case _: return True`) is correct for forward compatibility. The filter is applied synchronously in `handle_event()` before enqueueing, so filtered events never touch the queue.

Current event type coverage in the filter:

| Event Type | Granularity Level |
|---|---|
| `RunStarted` | LIFECYCLE+ |
| `RunFinished` | LIFECYCLE+ |
| `PhaseChanged` | LIFECYCLE+ |
| `RowCreated` | ROWS+ |
| `TransformCompleted` | ROWS+ |
| `GateEvaluated` | ROWS+ |
| `TokenCompleted` | ROWS+ |
| `FieldResolutionApplied` | ROWS+ |
| `ExternalCallCompleted` | FULL only |

All event types defined in `contracts/events.py` that are `TelemetryEvent` subclasses are covered. This is complete as of the current codebase.

### 5. No-Silent-Failure Requirement — Compliance Assessment

The "No Silent Failures" requirement says any emission point must either send data OR explicitly log that it has nothing. Assessment by layer:

**TelemetryManager (manager.py):**
- Disabled by config → returns early from `handle_event()` silently. **MARGINAL**: There is no log that telemetry is disabled (it's logged once at factory time with `logger.debug("telemetry_disabled")`). The manager itself does not log on every silenced event (correct — that would be noise). Startup log is sufficient.
- All drops are counted and logged at the `_LOG_INTERVAL` threshold. **COMPLIANT**.
- Thread death → logs `CRITICAL` and sets `_disabled = True`. **COMPLIANT**.
- Export thread not ready → logs `WARNING` and increments `_events_dropped`. **COMPLIANT**.
- Total exporter failure (disabled mode) → logs `CRITICAL` once. **COMPLIANT**.
- Per-exporter failure → logs `WARNING` per failure. **COMPLIANT**.

**Exporters:**
- Not configured → `export()` logs `WARNING` and returns. **COMPLIANT**.
- Buffer append failure → logs `WARNING`. **COMPLIANT**.
- Batch export failure → logs `WARNING`, always clears buffer. **COMPLIANT**.
- Flush failure → logs `WARNING`. **COMPLIANT**.
- Close failure → logs `WARNING`. **COMPLIANT**.

**One gap**: When `handle_event()` returns early because `not self._exporters` (empty list), it does so **silently** — no log. The factory does log a `WARNING` when configured with no exporters, but subsequent per-event silencing is completely silent. This is intentional (noise reduction) but technically violates the "explicitly acknowledge having nothing" clause of the no-silent-failure requirement. The factory warning at startup is the acknowledgment. This is borderline acceptable.

**Overall: The requirement is substantially met.** The "log at startup, not per-event" pattern for disabled/no-exporter states is the right design choice. Per-failure logging with aggregate thresholds prevents warning fatigue while maintaining visibility.

### 6. Protocol Definitions — What Governs Telemetry

The telemetry subsystem uses two levels of protocol:

1. **`ExporterProtocol`** (`protocols.py`): Governs the exporter interface. `@runtime_checkable`, so `isinstance(exporter, ExporterProtocol)` works. The factory does not currently perform this check — it trusts the pluggy discovery to return valid classes.

2. **`RuntimeTelemetryProtocol`** (`contracts/config/protocols.py`): Governs what `TelemetryManager.__init__()` expects from its config. This is the Settings→Runtime contract pattern used throughout ELSPETH. `RuntimeTelemetryConfig.from_settings()` performs the mapping and fails fast on unimplemented backpressure modes.

The two protocols cleanly separate concerns: one governs data access (config), the other governs behavior (exporter interface).

**Note on `TelemetryEvent`:** The base class for all telemetry events is in `contracts/events.py`, not `telemetry/`. This is correct — events cross the engine/telemetry boundary and must be visible to both. The `to_dict()` implementation on `TelemetryEvent` uses a custom recursive serializer (not `dataclasses.asdict()`) specifically to handle `MappingProxyType` fields from `FieldResolutionApplied`. This is a well-documented workaround for a real limitation.

---

## Concerns and Recommendations (Prioritized)

### HIGH — Code Organization (Not Correctness)

**H1: Private symbol sharing between OTLP and Azure Monitor exporters**

`azure_monitor.py` imports `_derive_trace_id`, `_generate_span_id`, and `_SyntheticReadableSpan` from `otlp.py`. These are private (`_`-prefixed) symbols "owned" by the OTLP module. This creates an artificial dependency between two peer exporters.

**Recommendation:** Extract these three items to `telemetry/exporters/_span_utils.py`. Both OTLP and Azure Monitor import from the shared utility. This is a two-file change with no behavior change.

**H2: Duplicated event serialization logic across three exporters**

`_serialize_event_attributes()` in `otlp.py` and `azure_monitor.py` are nearly identical. `_set_event_tags()` in `datadog.py` covers the same conversions with a different strategy (dict flattening vs. JSON). If a new `TelemetryEvent` field type is added (e.g., a new enum, a nested dataclass), all three serializers need updating independently.

**Recommendation:** Extract common conversion primitives to `_span_utils.py` or a new `telemetry/exporters/_serialization.py`. Each exporter calls the shared primitives and applies its platform-specific logic (JSON strings for OTLP/Azure, dotted keys for Datadog).

### MEDIUM — Behavioral Gaps

**M1: Per-exporter persistent failures are not independently handled**

If one exporter fails every event but another succeeds, the system records partial success (`_events_emitted` incremented, `_consecutive_total_failures` reset to zero). The broken exporter accumulates failure counts in `_exporter_failures` but is never disabled, rate-limited, or circuit-broken independently. Over a long run, one broken exporter wastes processing time on every event.

**Recommendation:** Add a per-exporter circuit breaker: after N consecutive individual failures, skip the exporter and log a one-time CRITICAL. This would require per-exporter consecutive failure tracking (parallel dict to `_exporter_failures`).

**M2: In-memory serialization mutation in `console.py`**

`_serialize_event()` mutates the dict returned by `event.to_dict()` in-place during iteration. This is safe in current Python (modifying values, not keys, during dict iteration) but fragile.

**Recommendation:** Build a separate `result` dict as done in `otlp.py`'s `_serialize_event_attributes()`.

### LOW — Minor Issues

**L1: `.get()` on internal dict in `_dispatch_to_exporters()`**

`self._exporter_failures.get(exporter.name, 0)` on line 189 of `manager.py`. This dict is initialized by `__init__` and only written by the export thread. A missing key means "first failure for this exporter" — this should be initialized to `0` in `__init__` for each known exporter, then accessed directly. The current form is not wrong but violates the codebase's no-defensive-get principle.

**Recommendation:** Initialize `self._exporter_failures = {e.name: 0 for e in exporters}` in `__init__`, then access with `self._exporter_failures[exporter.name]` directly.

**L2: `BackpressureMode.SLOW` defined but unimplemented**

The enum defines `SLOW = "slow"` but `_IMPLEMENTED_BACKPRESSURE_MODES` excludes it. Configuring `backpressure_mode: slow` causes `NotImplementedError` at startup. This is correct fail-fast behavior, but the enum value creates a false promise. Per ELSPETH's no-legacy-code policy, unimplemented enum values should not exist.

**Recommendation:** Remove `SLOW` from `BackpressureMode` until it is implemented. If it is being planned, track it as a Filigree feature issue, not as dead enum code.

**L3: `_drop_oldest_and_enqueue_newest()` complexity**

The sentinel-preservation logic in `_requeue_shutdown_sentinel_or_raise()` is the most complex section of the manager. It is correct but difficult to maintain. The bounded retry loop, `pending_task_done` accounting, and `RuntimeError` propagation interact subtly.

**Recommendation:** Add a dedicated integration test scenario that exercises the DROP mode overflow + shutdown race (sentinel eviction and recovery path). A targeted property test with a small queue and concurrent producers and shutdown would give confidence here.

**L4: `DatadogExporter.configure()` env var mutation is not thread-safe**

Two concurrent `configure()` calls would race on `DD_AGENT_HOST` / `DD_TRACE_AGENT_PORT`. Not a real risk in the current sequential factory pattern, but worth a comment.

**Recommendation:** Add a comment noting the non-thread-safe env var manipulation and that this is intentional in a sequential-factory context.

---

## Confidence

**High.** All 10 files were read in full. The contracts (`RuntimeTelemetryProtocol`, `RuntimeTelemetryConfig`, `TelemetryGranularity`, `BackpressureMode`), the complete event type hierarchy (`contracts/events.py`), and the engine wiring (`orchestrator/core.py`) were examined. The architecture is internally consistent and the no-silent-failure requirement is substantially satisfied. The identified concerns are real but none are correctness bugs affecting the audit trail or pipeline integrity.
