# Telemetry Design: Two-Tier Observability for ELSPETH

> **Priority:** P2 (Operational visibility, complements audit trail)
> **Effort:** Medium (2-3 sessions)
> **Risk:** Low (additive feature, existing EventBus pattern, failure isolation)
> **Status:** Design approved, ready for implementation

## Executive Summary

ELSPETH needs operational visibility alongside its audit trail. This design introduces a **two-tier telemetry model**:

1. **Global Telemetry (Tier 1)** — Framework-level audit events streamed to external observability platforms via pluggable exporters
2. **Plugin Telemetry (Tier 2)** — Plugin-internal tracing handled autonomously by individual plugins (Azure AI, Langfuse, etc.)

**Key principle:** Landscape remains the legal record. Telemetry is operational visibility — best-effort, not guaranteed.

---

## Problem Statement

ELSPETH's Landscape audit trail provides complete, legally defensible records of pipeline execution. However:

- **No real-time visibility** — Operators can't monitor pipelines during execution
- **No integration with existing observability stacks** — Teams using Datadog, Grafana, Azure Monitor have no native integration
- **No LLM-specific tracing** — LLM calls aren't visible in provider tracing tools (Azure AI, Langfuse)

### What We're NOT Solving

- Replacing Landscape (it remains the source of truth)
- Providing guaranteed delivery of telemetry events
- Managing plugin-internal tracing from the framework level

---

## Architecture Overview

### Two-Tier Model

```
┌─────────────────────────────────────────────────────────────────────┐
│                        ELSPETH Framework                            │
│                                                                     │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────────────┐ │
│  │   Engine/    │────▶│  Landscape   │     │      EventBus        │ │
│  │ Orchestrator │     │  Recorder    │     │  (existing)          │ │
│  └──────┬───────┘     └──────────────┘     └──────────┬───────────┘ │
│         │              (audit storage)                │             │
│         │                                             │             │
│         └───────────── TelemetryEvent ───────────────▶│             │
│                                                       │             │
│                              ┌────────────────────────┼─────────────┐
│                              │   Telemetry Exporters  │             │
│                              │   (pluggy plugins)     ▼             │
│                              │  ┌─────────┐ ┌─────────┐ ┌─────────┐ │
│                              │  │  OTLP   │ │  Azure  │ │ Console │ │
│                              │  │Exporter │ │ Monitor │ │Exporter │ │
│                              │  └────┬────┘ └────┬────┘ └────┬────┘ │
│                              └───────┼──────────┼───────────┼──────┘│
└──────────────────────────────────────┼──────────┼───────────┼───────┘
                                       ▼          ▼           ▼
                               ┌───────────┐ ┌─────────┐ ┌────────┐
                               │OTLP       │ │Azure    │ │stdout  │
                               │Collector  │ │Monitor  │ │        │
                               └───────────┘ └─────────┘ └────────┘
```

### Key Principles

1. **Landscape is the legal record** — Telemetry events are emitted AFTER successful Landscape recording
2. **EventBus as integration point** — Reuses existing pattern from CLI observability
3. **Exporters are pluggy plugins** — Same registration pattern as sources/transforms/sinks
4. **Full fidelity, configurable filtering** — Capture everything, let operators dial down
5. **Failure isolation** — Exporter failures don't crash pipeline

### Out of Scope for Framework

Plugin-internal telemetry (LLM tracing to Azure AI, Langfuse, etc.) — plugins handle this themselves as T1 code. The framework provides nothing for Tier 2.

---

## Telemetry Event Types

Events mirror what Landscape records, designed for streaming consumption.

### Event Hierarchy

```python
# Base event - all telemetry events inherit from this
@dataclass
class TelemetryEvent:
    timestamp: datetime
    run_id: str

# Lifecycle events (low volume)
@dataclass
class RunStarted(TelemetryEvent):
    config_hash: str
    source_plugin: str

@dataclass
class RunCompleted(TelemetryEvent):
    status: RunStatus
    row_count: int
    duration_ms: float

@dataclass
class PhaseChanged(TelemetryEvent):
    phase: PipelinePhase
    action: PhaseAction

# Row-level events (medium volume)
@dataclass
class RowCreated(TelemetryEvent):
    row_id: str
    token_id: str
    content_hash: str

@dataclass
class TransformCompleted(TelemetryEvent):
    row_id: str
    token_id: str
    node_id: str
    plugin_name: str
    status: NodeStateStatus
    duration_ms: float
    input_hash: str
    output_hash: str

@dataclass
class GateEvaluated(TelemetryEvent):
    row_id: str
    token_id: str
    node_id: str
    plugin_name: str
    routing_mode: RoutingMode
    destinations: tuple[str, ...]

@dataclass
class TokenOutcome(TelemetryEvent):
    row_id: str
    token_id: str
    outcome: TokenOutcome
    sink_name: str | None

# External call events (high volume when enabled)
@dataclass
class ExternalCallCompleted(TelemetryEvent):
    state_id: str
    call_type: CallType  # LLM, HTTP, etc.
    provider: str
    status: CallStatus
    latency_ms: float
    # Optional high-fidelity fields (configurable)
    request_hash: str | None = None
    response_hash: str | None = None
    token_usage: dict[str, int] | None = None  # For LLM calls
```

### Granularity Levels

| Level | Events Emitted | Typical Volume |
|-------|----------------|----------------|
| `lifecycle` | `RunStarted`, `RunCompleted`, `PhaseChanged` | ~10-20 per run |
| `rows` | Above + `RowCreated`, `TransformCompleted`, `GateEvaluated`, `TokenOutcome` | N × M (rows × transforms) |
| `full` | Above + `ExternalCallCompleted` with all details | High (includes all external calls) |

---

## Exporter Protocol & Plugin Registration

### Protocol Definition

```python
# src/elspeth/telemetry/protocols.py

from typing import Any, Protocol, runtime_checkable

@runtime_checkable
class ExporterProtocol(Protocol):
    """Protocol for telemetry exporters."""

    # Class attribute - exporter name for config reference
    name: str

    def configure(self, config: dict[str, Any]) -> None:
        """Configure exporter with deployment-specific settings.

        Called once at startup. Exporter should validate config
        and establish connections (but not fail on transient errors).
        """
        ...

    def export(self, event: TelemetryEvent) -> None:
        """Export a single event.

        Called synchronously from EventBus. Implementations should:
        - Buffer internally if needed for batching
        - Handle failures gracefully (log, don't crash pipeline)
        - Respect backpressure via internal queuing

        Note: Telemetry is operational, not audit. Dropped events
        are acceptable under load - Landscape has the legal record.
        """
        ...

    def flush(self) -> None:
        """Flush any buffered events.

        Called at run completion and shutdown.
        """
        ...

    def close(self) -> None:
        """Release resources.

        Called at shutdown. Close connections, stop background threads.
        """
        ...
```

### Hook Specification

```python
# src/elspeth/telemetry/hookspecs.py

from pluggy import HookspecMarker

hookspec = HookspecMarker("elspeth")

class ElspethTelemetrySpec:
    """Hook specifications for telemetry exporters."""

    @hookspec
    def elspeth_get_exporters(self) -> list[type[ExporterProtocol]]:
        """Return telemetry exporter classes."""
```

### Registration Pattern

```python
# src/elspeth/telemetry/exporters/otlp.py

from elspeth.telemetry.hookspecs import hookimpl

class OTLPExporter:
    name = "otlp"

    def configure(self, config: dict[str, Any]) -> None:
        self._endpoint = config["endpoint"]
        self._headers = config.get("headers", {})
        # Initialize OTLP client...

class OTLPExporterPlugin:
    @hookimpl
    def elspeth_get_exporters(self) -> list[type[ExporterProtocol]]:
        return [OTLPExporter]
```

---

## Configuration

### User-Facing Settings

```yaml
# settings.yaml
telemetry:
  enabled: true
  granularity: full  # lifecycle | rows | full
  exporters:
    - name: otlp
      endpoint: "http://localhost:4317"
      headers:
        Authorization: "Bearer ${OTEL_TOKEN}"
    - name: console
      format: json  # json | pretty
```

### Protocol (contracts/config/protocols.py)

```python
@runtime_checkable
class RuntimeTelemetryProtocol(Protocol):
    """What TelemetryManager requires for event streaming."""
    enabled: bool
    granularity: TelemetryGranularity
    exporter_configs: tuple[ExporterConfig, ...]
```

### Runtime Dataclass (contracts/config/runtime.py)

```python
class TelemetryGranularity(Enum):
    LIFECYCLE = 1
    ROWS = 2
    FULL = 3

@dataclass(frozen=True)
class ExporterConfig:
    """Configuration for a single exporter."""
    name: str
    options: dict[str, Any]

@dataclass(frozen=True, slots=True)
class RuntimeTelemetryConfig:
    """Runtime telemetry configuration.

    Implements RuntimeTelemetryProtocol for use by TelemetryManager.

    Field Mappings (Settings → Runtime):
        enabled ← enabled
        granularity ← granularity (parsed to enum)
        exporter_configs ← exporters (converted to ExporterConfig tuple)
    """
    enabled: bool
    granularity: TelemetryGranularity
    exporter_configs: tuple[ExporterConfig, ...]

    @classmethod
    def from_settings(cls, settings: "TelemetrySettings") -> "RuntimeTelemetryConfig":
        """Convert user-facing Settings to runtime config."""
        return cls(
            enabled=settings.enabled,
            granularity=TelemetryGranularity[settings.granularity.upper()],
            exporter_configs=tuple(
                ExporterConfig(name=e.name, options=e.options)
                for e in settings.exporters
            ),
        )

    @classmethod
    def disabled(cls) -> "RuntimeTelemetryConfig":
        """Configuration that disables telemetry."""
        return cls(
            enabled=False,
            granularity=TelemetryGranularity.LIFECYCLE,
            exporter_configs=(),
        )
```

### Granularity Filtering

```python
def should_emit(event: TelemetryEvent, granularity: TelemetryGranularity) -> bool:
    """Filter events based on configured granularity."""
    if isinstance(event, (RunStarted, RunCompleted, PhaseChanged)):
        return True  # Always emit lifecycle
    if isinstance(event, (RowCreated, TransformCompleted, GateEvaluated, TokenOutcome)):
        return granularity.value >= TelemetryGranularity.ROWS.value
    if isinstance(event, ExternalCallCompleted):
        return granularity == TelemetryGranularity.FULL
    return True  # Unknown events pass through
```

---

## Event Emission Points

### TelemetryManager

```python
# src/elspeth/telemetry/manager.py

class TelemetryManager:
    """Coordinates event emission to configured exporters.

    Subscribes to EventBus, filters by granularity, dispatches to exporters.
    Failures are logged, not propagated — telemetry is operational.
    """

    def __init__(
        self,
        config: RuntimeTelemetryProtocol,
        event_bus: EventBusProtocol,
        exporters: list[ExporterProtocol],
    ) -> None:
        self._config = config
        self._exporters = exporters
        self._disabled = False
        self._consecutive_failures = 0
        self._max_consecutive_failures = 10

        if config.enabled:
            for event_type in TELEMETRY_EVENT_TYPES:
                event_bus.subscribe(event_type, self._handle_event)

    def _handle_event(self, event: TelemetryEvent) -> None:
        """Filter and dispatch event to all exporters."""
        if self._disabled or not should_emit(event, self._config.granularity):
            return

        failures = 0
        for exporter in self._exporters:
            try:
                exporter.export(event)
            except Exception:
                failures += 1
                logger.warning(
                    "Exporter failed",
                    exporter=exporter.name,
                    event_type=type(event).__name__,
                    exc_info=True,
                )

        # Graceful degradation: disable after repeated total failures
        if failures == len(self._exporters):
            self._consecutive_failures += 1
            if self._consecutive_failures >= self._max_consecutive_failures:
                logger.error("All exporters failing, disabling telemetry")
                self._disabled = True
        else:
            self._consecutive_failures = 0

    def flush(self) -> None:
        """Flush all exporters."""
        for exporter in self._exporters:
            try:
                exporter.flush()
            except Exception:
                logger.warning("Exporter flush failed", exporter=exporter.name)

    def close(self) -> None:
        """Close all exporters."""
        for exporter in self._exporters:
            try:
                exporter.close()
            except Exception:
                logger.warning("Exporter close failed", exporter=exporter.name)
```

### Emission Points in Orchestrator

Events are emitted AFTER successful Landscape recording:

| Orchestrator Method | Landscape Call | Telemetry Event |
|---------------------|----------------|-----------------|
| `_begin_run()` | `recorder.begin_run()` | `RunStarted` |
| `_complete_run()` | `recorder.complete_run()` | `RunCompleted` |
| `_process_source_row()` | `recorder.record_row()` | `RowCreated` |
| `_execute_transform()` | `recorder.record_node_state()` | `TransformCompleted` |
| `_execute_gate()` | `recorder.record_routing_event()` | `GateEvaluated` |
| `_record_token_outcome()` | `recorder.record_token_outcome()` | `TokenOutcome` |

### Emission Points in AuditedLLMClient

```python
def chat_completion(self, ...) -> LLMResponse:
    start = time.perf_counter()
    try:
        response = self._client.chat.completions.create(...)
        latency_ms = (time.perf_counter() - start) * 1000

        # Record to Landscape FIRST (existing)
        self._record_call(request, response, CallStatus.SUCCESS, latency_ms)

        # Emit telemetry event AFTER (new)
        self._event_bus.emit(ExternalCallCompleted(
            timestamp=now(),
            run_id=self._run_id,
            state_id=self._state_id,
            call_type=CallType.LLM,
            provider=self._provider,
            status=CallStatus.SUCCESS,
            latency_ms=latency_ms,
            token_usage=response.usage.model_dump() if response.usage else None,
        ))

        return LLMResponse(...)
    except Exception as e:
        # Similar pattern for failures
        ...
```

---

## Default Exporters

### OTLP Exporter

```python
# src/elspeth/telemetry/exporters/otlp.py

class OTLPExporter:
    """Export telemetry events via OpenTelemetry Protocol.

    Converts ELSPETH TelemetryEvents to OTLP spans and ships
    to any OTLP-compatible backend (Jaeger, Tempo, Datadog, Honeycomb, etc.)
    """
    name = "otlp"

    def configure(self, config: dict[str, Any]) -> None:
        self._endpoint = config["endpoint"]
        self._headers = config.get("headers", {})
        self._batch_size = config.get("batch_size", 100)
        self._flush_interval_ms = config.get("flush_interval_ms", 5000)

        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        self._span_exporter = OTLPSpanExporter(
            endpoint=self._endpoint,
            headers=self._headers,
        )
        self._buffer: list[TelemetryEvent] = []

    def export(self, event: TelemetryEvent) -> None:
        self._buffer.append(event)
        if len(self._buffer) >= self._batch_size:
            self._flush_batch()

    def _flush_batch(self) -> None:
        if not self._buffer:
            return
        spans = [self._event_to_span(e) for e in self._buffer]
        self._span_exporter.export(spans)
        self._buffer.clear()

    def flush(self) -> None:
        self._flush_batch()

    def close(self) -> None:
        self.flush()
        self._span_exporter.shutdown()
```

### Azure Monitor Exporter

```python
# src/elspeth/telemetry/exporters/azure_monitor.py

class AzureMonitorExporter:
    """Export telemetry to Azure Monitor / Application Insights.

    Uses azure-monitor-opentelemetry-exporter for native integration.
    """
    name = "azure_monitor"

    def configure(self, config: dict[str, Any]) -> None:
        self._connection_string = config["connection_string"]

        from azure.monitor.opentelemetry.exporter import AzureMonitorTraceExporter
        self._exporter = AzureMonitorTraceExporter(
            connection_string=self._connection_string,
        )
        self._buffer: list[TelemetryEvent] = []
        self._batch_size = config.get("batch_size", 100)

    # ... similar pattern to OTLP
```

### Datadog Exporter

```python
# src/elspeth/telemetry/exporters/datadog.py

class DatadogExporter:
    """Export telemetry to Datadog via native API.

    Uses ddtrace for native Datadog integration with full APM features.
    """
    name = "datadog"

    def configure(self, config: dict[str, Any]) -> None:
        self._api_key = config["api_key"]
        self._service_name = config.get("service_name", "elspeth")
        self._env = config.get("env", "production")

        from ddtrace import tracer
        tracer.configure(
            hostname=config.get("agent_host", "localhost"),
            port=config.get("agent_port", 8126),
        )
        self._tracer = tracer
```

### Console Exporter

```python
# src/elspeth/telemetry/exporters/console.py

class ConsoleExporter:
    """Export telemetry events to stdout for testing/debugging."""
    name = "console"

    def configure(self, config: dict[str, Any]) -> None:
        self._format = config.get("format", "json")  # json | pretty
        self._output = config.get("output", "stdout")  # stdout | stderr

    def export(self, event: TelemetryEvent) -> None:
        if self._format == "json":
            line = json.dumps(asdict(event), default=str)
        else:
            line = f"[{event.timestamp}] {type(event).__name__}: {event.run_id}"

        stream = sys.stdout if self._output == "stdout" else sys.stderr
        print(line, file=stream)

    def flush(self) -> None:
        pass

    def close(self) -> None:
        pass
```

---

## Plugin-Specific Telemetry (Tier 2)

The framework provides **nothing** for plugin-internal tracing. Plugins are T1 code and handle their own integrations.

### What This Means

| Aspect | Framework Role | Plugin Role |
|--------|----------------|-------------|
| Configuration | None | Plugin defines its own telemetry config fields |
| Dependencies | None | Plugin brings its own SDK (Azure AI, Langfuse, etc.) |
| Initialization | None | Plugin initializes tracing in `__init__` or `on_start()` |
| Instrumentation | None | Plugin wraps its own calls with provider SDK |
| Lifecycle | None | Plugin cleans up in `close()` |

### Example: Azure LLM Plugin

```python
class AzureOpenAIConfig(LLMConfig):
    # Plugin-specific telemetry config (framework doesn't interpret this)
    azure_tracing: AzureTracingConfig | None = None

@dataclass
class AzureTracingConfig:
    enabled: bool = False
    connection_string: str | None = None

class AzureLLMTransform(BaseTransform, BatchTransformMixin):

    def on_start(self, ctx: PluginContext) -> None:
        super().on_start(ctx)

        if self._config.azure_tracing and self._config.azure_tracing.enabled:
            self._setup_azure_tracing()

    def _setup_azure_tracing(self) -> None:
        from azure.monitor.opentelemetry import configure_azure_monitor
        configure_azure_monitor(
            connection_string=self._config.azure_tracing.connection_string,
            enable_live_metrics=True,
        )
```

### Example Configuration

```yaml
transforms:
  - plugin: azure_llm
    options:
      deployment_name: gpt-4
      endpoint: ${AZURE_OPENAI_ENDPOINT}
      api_key: ${AZURE_OPENAI_KEY}

      # Plugin-specific telemetry (framework ignores this)
      azure_tracing:
        enabled: true
        connection_string: ${APPLICATIONINSIGHTS_CONNECTION_STRING}
```

---

## Error Handling & Failure Modes

### Principle

**Telemetry is best-effort, Landscape is guaranteed.**

### Failure Behavior

| Failure Mode | Behavior | Rationale |
|--------------|----------|-----------|
| Exporter throws exception | Log warning, continue pipeline | Telemetry is operational, not audit |
| Exporter slow (backpressure) | Buffer internally, drop oldest on overflow | Avoid blocking pipeline |
| All exporters fail repeatedly | Log error, disable telemetry for run | Don't retry endlessly |
| Invalid config | Fail fast at startup | Config errors should crash early |
| EventBus subscription fails | Crash at startup | Framework bug, not runtime issue |

### Buffer Overflow Policy

```python
class BoundedBuffer:
    """Ring buffer that drops oldest events on overflow."""

    def __init__(self, max_size: int = 10_000) -> None:
        self._buffer: deque[TelemetryEvent] = deque(maxlen=max_size)
        self._dropped_count: int = 0

    def append(self, event: TelemetryEvent) -> None:
        if len(self._buffer) == self._buffer.maxlen:
            self._dropped_count += 1
        self._buffer.append(event)
```

---

## Package Structure

```
src/elspeth/telemetry/
├── __init__.py           # Re-exports
├── events.py             # TelemetryEvent dataclasses
├── protocols.py          # ExporterProtocol
├── hookspecs.py          # elspeth_get_exporters hook
├── manager.py            # TelemetryManager (EventBus subscriber)
├── filtering.py          # Granularity filtering logic
└── exporters/
    ├── __init__.py       # Exporter plugin registration
    ├── otlp.py           # OTLP exporter
    ├── azure_monitor.py  # Azure Monitor exporter
    ├── datadog.py        # Datadog exporter
    └── console.py        # Console exporter (testing)
```

---

## Implementation Tasks

### Phase 1: Core Infrastructure

**Task 1.1: Create telemetry package structure**
- Create `src/elspeth/telemetry/` directory
- Create `__init__.py`, `events.py`, `protocols.py`, `hookspecs.py`
- Define `TelemetryEvent` base class and event dataclasses
- Define `ExporterProtocol`
- Define `elspeth_get_exporters` hook specification

**Task 1.2: Add configuration contracts**
- Add `TelemetryGranularity` enum to `contracts/enums.py`
- Add `RuntimeTelemetryProtocol` to `contracts/config/protocols.py`
- Add `RuntimeTelemetryConfig` to `contracts/config/runtime.py`
- Add `TelemetrySettings` to `core/config.py`
- Update `ElspethSettings` to include telemetry settings

**Task 1.3: Implement TelemetryManager**
- Create `manager.py` with `TelemetryManager` class
- Implement EventBus subscription
- Implement granularity filtering
- Implement failure handling and graceful degradation

**Task 1.4: Implement ConsoleExporter**
- Create `exporters/console.py`
- Implement JSON and pretty formats
- Register via pluggy hook
- **Tests:** Unit tests for output formatting

### Phase 2: Event Emission

**Task 2.1: Add telemetry events to Orchestrator**
- Inject `TelemetryManager` into `Orchestrator`
- Emit `RunStarted` after `recorder.begin_run()`
- Emit `RunCompleted` after `recorder.complete_run()`
- Emit `RowCreated` after `recorder.record_row()`
- **Tests:** Integration test verifying events emitted

**Task 2.2: Add telemetry events to RowProcessor**
- Emit `TransformCompleted` after transform execution
- Emit `GateEvaluated` after gate evaluation
- Emit `TokenOutcome` after token outcome recording
- **Tests:** Integration test for row-level events

**Task 2.3: Add telemetry events to AuditedLLMClient**
- Inject EventBus into `AuditedLLMClient`
- Emit `ExternalCallCompleted` after LLM calls
- Include token usage for LLM calls
- **Tests:** Integration test for external call events

### Phase 3: Production Exporters

**Task 3.1: Implement OTLP Exporter**
- Add `opentelemetry-exporter-otlp` to optional dependencies
- Create `exporters/otlp.py`
- Implement event-to-span conversion
- Implement batching and flush
- Register via pluggy hook
- **Tests:** Unit tests with mock OTLP endpoint

**Task 3.2: Implement Azure Monitor Exporter**
- Add `azure-monitor-opentelemetry-exporter` to optional dependencies
- Create `exporters/azure_monitor.py`
- Implement Azure-specific span attributes
- Register via pluggy hook
- **Tests:** Unit tests with mock Azure endpoint

**Task 3.3: Implement Datadog Exporter**
- Add `ddtrace` to optional dependencies
- Create `exporters/datadog.py`
- Implement Datadog-specific tagging
- Register via pluggy hook
- **Tests:** Unit tests with mock Datadog agent

### Phase 4: Testing & Documentation

**Task 4.1: Add integration tests**
- Test telemetry emitted alongside Landscape
- Test granularity filtering
- Test exporter failure isolation
- Test graceful degradation

**Task 4.2: Add contract tests**
- Test all exporters implement `ExporterProtocol`
- Test `RuntimeTelemetryConfig` implements protocol
- Test config alignment (no orphaned fields)

**Task 4.3: Update documentation**
- Add telemetry section to CLAUDE.md
- Create `docs/guides/telemetry.md` user guide
- Document exporter configuration options

---

## Testing Strategy

### Unit Tests

| Component | Test Focus |
|-----------|------------|
| `TelemetryEvent` dataclasses | Serialization, field completeness |
| `TelemetryManager` | Granularity filtering, exporter dispatch, failure handling |
| `ConsoleExporter` | Output format, stream selection |
| Granularity filtering | Event type → granularity level mapping |

### Integration Tests

```python
def test_telemetry_emitted_alongside_landscape():
    """Telemetry events mirror Landscape recording."""
    captured_events: list[TelemetryEvent] = []
    exporter = CapturingExporter(captured_events)

    run_pipeline_with_telemetry(exporter)

    assert any(isinstance(e, RunStarted) for e in captured_events)
    assert any(isinstance(e, RowCreated) for e in captured_events)
    assert any(isinstance(e, RunCompleted) for e in captured_events)


def test_telemetry_failure_does_not_crash_pipeline():
    """Exporter failures are logged but don't stop processing."""
    failing_exporter = AlwaysFailsExporter()

    result = run_pipeline_with_telemetry(failing_exporter)

    assert result.status == RunStatus.COMPLETED


def test_granularity_filtering():
    """Events are filtered based on configured granularity."""
    captured: list[TelemetryEvent] = []

    run_pipeline_with_granularity(TelemetryGranularity.LIFECYCLE, captured)

    assert any(isinstance(e, RunStarted) for e in captured)
    assert not any(isinstance(e, RowCreated) for e in captured)
```

### Contract Tests

```python
def test_exporter_protocol_compliance():
    """All shipped exporters implement ExporterProtocol."""
    for exporter_cls in [OTLPExporter, AzureMonitorExporter, DatadogExporter, ConsoleExporter]:
        instance = exporter_cls()
        assert hasattr(instance, 'name')
        assert hasattr(instance, 'configure')
        assert hasattr(instance, 'export')
        assert hasattr(instance, 'flush')
        assert hasattr(instance, 'close')
```

---

## Success Criteria

### Phase 1-2 Complete

- [ ] Telemetry events defined for all Landscape recording points
- [ ] `TelemetryManager` subscribes to EventBus and dispatches to exporters
- [ ] Granularity filtering works correctly
- [ ] `ConsoleExporter` works for local testing
- [ ] Exporter failures don't crash pipeline

### Phase 3-4 Complete

- [ ] OTLP, Azure Monitor, Datadog exporters ship
- [ ] All exporters implement `ExporterProtocol`
- [ ] Configuration follows contracts pattern
- [ ] Integration tests pass
- [ ] Documentation complete

---

## Dependencies

- **Requires:** Config contracts refactor (in progress) — for `RuntimeTelemetryConfig` pattern
- **Requires:** Existing EventBus infrastructure
- **Optional deps:** `opentelemetry-exporter-otlp`, `azure-monitor-opentelemetry-exporter`, `ddtrace`

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Telemetry overhead impacts pipeline performance | Low | Medium | Async buffering, granularity filtering |
| Exporter failures cause cascading issues | Low | Low | Failure isolation, graceful degradation |
| EventBus becomes bottleneck | Very Low | Medium | Synchronous dispatch is fast, can add async if needed |
| Optional deps not installed | Medium | Low | Graceful handling, clear error messages |

---

## References

- **EventBus implementation:** `src/elspeth/core/events.py`
- **Existing SpanFactory:** `src/elspeth/engine/spans.py`
- **Config contracts refactor:** `docs/plans/in-progress/2026-01-29-config-contracts-refactor.md`
- **Plugin hookspecs:** `src/elspeth/plugins/hookspecs.py`
- **AuditedLLMClient:** `src/elspeth/plugins/clients/llm.py`
