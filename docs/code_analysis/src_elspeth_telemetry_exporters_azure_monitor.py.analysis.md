# Analysis: src/elspeth/telemetry/exporters/azure_monitor.py

**Lines:** 396
**Role:** Azure Monitor exporter -- converts ELSPETH TelemetryEvents to OpenTelemetry spans and ships them to Azure Application Insights via the `azure-monitor-opentelemetry-exporter` package. Reuses `_derive_trace_id`, `_derive_span_id`, and `_SyntheticReadableSpan` from the OTLP exporter.
**Key dependencies:** Imports `_derive_span_id`, `_derive_trace_id`, `_SyntheticReadableSpan` from `elspeth.telemetry.exporters.otlp`. Imports `TelemetryExporterError` from `elspeth.telemetry.errors`. Conditionally imports `AzureMonitorTraceExporter` from `azure.monitor.opentelemetry.exporter` and OpenTelemetry SDK types (`Resource`, `TracerProvider`). Used by `TelemetryManager` via `ExporterProtocol`.
**Analysis depth:** FULL

## Summary

The Azure Monitor exporter is the most defensively coded of the four exporters, with thorough type validation for every config parameter. The code is well-structured and addresses a known SDK issue (ProxyTracerProvider). The primary concerns are a **connection string potentially appearing in error tracebacks** and the **duplicated serialization logic** shared with the OTLP exporter. No critical bugs found.

## Warnings

### [113-119] Connection string stored in plain text with no redaction

**What:** The Azure Application Insights connection string is stored as `self._connection_string` and passed directly to `AzureMonitorTraceExporter`. This string typically contains the `InstrumentationKey` which, while not a full secret, can be used to inject fake telemetry data into the Application Insights instance.

**Why it matters:** If an exception traceback from the Azure Monitor SDK is logged (e.g., during `export()` or `shutdown()`), the connection string could appear in logs. The CLAUDE.md specifies that secrets should use HMAC fingerprints for audit. While the InstrumentationKey is not a credential in the traditional sense, injecting telemetry to a monitoring system could be used to mask real incidents or trigger false alerts.

**Evidence:**
```python
self._connection_string = connection_string
# ...
self._azure_exporter = AzureMonitorTraceExporter(
    connection_string=self._connection_string,
    tracer_provider=tracer_provider,
)
```
No fingerprinting or redaction is performed. The `logger.debug` call on line 199 does NOT log the connection string, which is good, but the raw value persists in memory on the instance.

### [186-189] tracer_provider parameter may not be supported by all SDK versions

**What:** The `AzureMonitorTraceExporter` constructor is called with a `tracer_provider` keyword argument. The docstring explains this fixes a ProxyTracerProvider issue. However, not all versions of the `azure-monitor-opentelemetry-exporter` package may accept `tracer_provider` as a constructor argument.

**Why it matters:** If a user has an older or newer version of the Azure Monitor SDK installed, this could fail with an unexpected `TypeError`. The error would be caught by the `ImportError` handler on line 190, but `TypeError` is not `ImportError`, so it would propagate as an unhandled exception during `configure()`. This is actually correct behavior per the ExporterProtocol contract (configure may raise), but the error message would be confusing (a `TypeError` rather than a clear SDK version mismatch message).

**Evidence:**
```python
self._azure_exporter = AzureMonitorTraceExporter(
    connection_string=self._connection_string,
    tracer_provider=tracer_provider,
)
```
The `except ImportError` on line 190 only catches import failures, not constructor argument mismatches.

### [321-360] Duplicated serialization logic from OTLP exporter

**What:** The `_serialize_event_attributes` method is a near-identical copy of `OTLPExporter._serialize_event_attributes` (lines 293-327 in `otlp.py`). Both methods perform the same type conversions: `datetime -> ISO 8601`, `Enum -> value`, `dict -> JSON string`, `tuple -> list`, skip `None`.

**Why it matters:** This is a maintenance burden. If a new event field type is added (e.g., `Decimal`, `bytes`, `set`), both methods must be updated independently. A bug fix in one could be missed in the other. The Azure Monitor exporter already imports three utilities from the OTLP module -- the serialization method should be extracted too.

**Evidence:** The Azure Monitor exporter imports `_derive_span_id`, `_derive_trace_id`, and `_SyntheticReadableSpan` from `otlp.py` but re-implements `_serialize_event_attributes` locally with identical logic.

### [336-339] Local imports inside method body

**What:** `_serialize_event_attributes` imports `json`, `asdict`, `datetime`, and `Enum` inside the method body rather than at the module level. This is inconsistent with the OTLP exporter which imports these at the module level.

**Why it matters:** This is a minor performance concern (import lookup on every call) and a style inconsistency. The imports are in the standard library so the cost is negligible (cached by Python), but it creates unnecessary divergence between the two exporter implementations.

**Evidence:**
```python
def _serialize_event_attributes(self, event: TelemetryEvent) -> dict[str, Any]:
    import json
    from dataclasses import asdict
    from datetime import datetime
    from enum import Enum
```

## Observations

### [169-188] Good: TracerProvider creation with Resource attributes

The code correctly creates a `TracerProvider` with proper `Resource` attributes to avoid the ProxyTracerProvider issue. This is well-documented with clear comments explaining the "why." The test coverage in `test_azure_monitor.py` verifies the resource attributes are passed through correctly.

### [106-160] Thorough config validation

This exporter validates every config parameter's type and value range. This is the gold standard among the four exporters -- the OTLP and Datadog exporters should match this rigor. Each invalid config produces a clear `TelemetryExporterError` with the field name, expected type, and actual type.

### [268-319] Span creation is clean and correct

The `_event_to_span` method correctly reuses shared utilities from the OTLP exporter and adds Azure-specific attributes (`cloud.provider`, `elspeth.exporter`). The resource is passed to `_SyntheticReadableSpan` for proper service identification in Application Insights.

### Test coverage is good

The test file `test_azure_monitor.py` covers configuration validation, buffering behavior, span conversion with Azure-specific attributes, lifecycle operations, and error handling. The fixture pattern with `mock_azure_exporter` is clean.

### [237-266] Buffer/flush pattern identical to OTLP exporter

The buffering and flushing logic is copied from the OTLP exporter. This is another candidate for extraction into a shared base class or mixin.

## Verdict

**Status:** SOUND
**Recommended action:** (1) Extract `_serialize_event_attributes` into a shared utility module (alongside the already-shared `_derive_trace_id`, `_derive_span_id`, and `_SyntheticReadableSpan`). (2) Move local imports in `_serialize_event_attributes` to module level. (3) Consider adding a `try/except TypeError` around the `AzureMonitorTraceExporter` constructor to provide a clearer error message about SDK version compatibility.
**Confidence:** HIGH -- Full analysis with complete context from OTLP exporter (shared utilities), protocol, manager, factory, and test files.
