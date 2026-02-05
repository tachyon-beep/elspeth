# Analysis: src/elspeth/telemetry/exporters/datadog.py

**Lines:** 333
**Role:** Datadog exporter -- sends telemetry events to Datadog via the `ddtrace` library. Unlike the OTLP and Azure Monitor exporters which batch events into synthetic spans, this exporter creates native Datadog spans using `ddtrace.tracer.start_span()` and finishes them immediately.
**Key dependencies:** Imports `structlog`, `dataclasses.asdict`, `datetime`, `enum`. Imports `TelemetryExporterError` from `elspeth.telemetry.errors`. Conditionally imports `ddtrace.tracer`. Does NOT import shared utilities from `otlp.py` -- completely independent implementation. Used by `TelemetryManager` via `ExporterProtocol`.
**Analysis depth:** FULL

## Summary

This exporter has two significant issues. First, it **mutates global process environment variables** (`DD_AGENT_HOST`, `DD_TRACE_AGENT_PORT`) during `configure()`, which creates a **global side effect** that affects all other `ddtrace` users in the same process and is not idempotent. Second, the `ddtrace.tracer` is a **process-global singleton**, and calling `shutdown()` on `close()` **terminates tracing for the entire process**, which would break any other code using `ddtrace`. There are also concerns about recursive dict flattening depth and missing `api_key` handling.

## Critical Findings

### [147-148] Global environment variable mutation during configure()

**What:** The `configure` method sets `os.environ["DD_AGENT_HOST"]` and `os.environ["DD_TRACE_AGENT_PORT"]` as a side effect of configuration. These are global process-level mutations that persist after the exporter is closed.

**Why it matters:** This creates several problems:
1. **Non-idempotent configuration:** If two Datadog exporters are created with different agent configurations (unlikely but possible in tests), the second one silently overwrites the first's environment.
2. **Global side effect leakage:** After the exporter is closed, the environment variables remain set. Other code in the same process that reads these variables will get values set by a now-closed exporter.
3. **Test pollution:** The test file uses `patch.dict("os.environ", {}, clear=False)` to contain this, but the production code has no such protection.
4. **Race condition:** If `configure()` is called from one thread while another thread is reading these environment variables, the behavior is undefined.

**Evidence:**
```python
os.environ["DD_AGENT_HOST"] = agent_host
os.environ["DD_TRACE_AGENT_PORT"] = str(agent_port)
```
The comment says "These must be set before the tracer sends any spans" but does not acknowledge the global mutation.

### [150] ddtrace.tracer is a process-global singleton

**What:** The exporter stores `self._tracer = tracer` where `tracer` is the global `ddtrace.tracer` singleton. On `close()`, it calls `self._tracer.shutdown()` which shuts down the global tracer for the entire process.

**Why it matters:** If any other code in the process uses `ddtrace` (e.g., web framework instrumentation, other monitoring integrations), calling `shutdown()` on the global tracer disables all tracing for the entire process, not just the ELSPETH exporter. This is a destructive operation with blast radius beyond the exporter.

**Evidence:**
```python
# configure():
from ddtrace import tracer
self._tracer = tracer

# close():
self._tracer.shutdown()
self._tracer = None
```
Setting `self._tracer = None` only removes the local reference; the global `ddtrace.tracer` singleton is already shut down at that point.

## Warnings

### [283-286] Unbounded recursive dict flattening

**What:** `_set_tag_value` recursively flattens dicts to dotted keys. If a telemetry event contains deeply nested dicts (e.g., `ExternalCallCompleted.request_payload` with nested JSON from an LLM response), this could create very long tag keys and potentially hit Datadog's tag key length limits (200 characters).

**Why it matters:** Datadog silently truncates tag keys longer than 200 characters, which could produce tags that look identical but map to different nested paths. There is also no recursion depth limit, so a maliciously crafted or accidentally circular dict (not possible with frozen dataclasses, but possible with `request_payload: dict[str, Any]`) could cause a `RecursionError`.

**Evidence:**
```python
elif isinstance(value, dict):
    for sub_key, sub_value in value.items():
        self._set_tag_value(span, f"{key}.{sub_key}", sub_value)
```
With `ExternalCallCompleted.request_payload` containing nested LLM request data like `{"messages": [{"role": "user", "content": "..."}]}`, the recursion hits lists, which fall through to the `else` branch and get set as the raw list value. But nested dicts within dicts would continue recursing.

### [80-81] api_key config parameter accepted but never used

**What:** The docstring lists `api_key` as a configuration option ("optional if using local agent"), but the `configure()` method never reads `config.get("api_key")`. The parameter is silently ignored.

**Why it matters:** Users who configure `api_key` expecting it to be passed to the Datadog agent will get no error and no indication their key is being ignored. This is the same class of bug as the P2-2026-01-21 `exponential_base` issue documented in CLAUDE.md -- a config field that is validated (or in this case, documented) but never wired to runtime behavior.

**Evidence:**
```python
# Docstring says:
#     api_key: Datadog API key (optional if using local agent)

# But configure() never reads it:
# No config.get("api_key") anywhere in the method
```

### [218] Event timestamp not timezone-aware -- no UTC normalization

**What:** Unlike the OTLP and Azure Monitor exporters which check `event.timestamp.tzinfo is None` and add UTC if missing, the Datadog exporter calls `event.timestamp.timestamp()` directly without checking timezone awareness.

**Why it matters:** If a naive datetime (no timezone) is passed, `datetime.timestamp()` assumes local time, which could produce incorrect span timing if the system timezone is not UTC. The OTLP and Azure Monitor exporters explicitly handle this case by assuming UTC for naive timestamps.

**Evidence:**
```python
# Datadog (no timezone check):
event_unix_seconds = event.timestamp.timestamp()

# OTLP (handles naive timestamps):
if event.timestamp.tzinfo is None:
    ts = event.timestamp.replace(tzinfo=UTC)
else:
    ts = event.timestamp
```
The `TelemetryEvent` docstring says timestamps should be UTC, but there is no enforcement at the dataclass level.

### [232-247] Span leak if set_tag raises before finish

**What:** The span is created with `start_span()`, and `finish()` is called in a `finally` block (line 247). However, if `start_span()` itself partially fails or returns a span object that is in an invalid state, the `finally` block will still attempt to call `finish()` on it, which could raise a secondary exception.

**Why it matters:** The `try/finally` pattern is correct in the common case. The concern is narrow: if `self._tracer.start_span()` returns a partially initialized span object (rather than raising), subsequent `set_tag` and `finish` calls could produce confusing double-errors. In practice, `ddtrace` spans are robust, so this is low risk.

**Evidence:**
```python
span = self._tracer.start_span(...)
span.start_ns = event_ns
try:
    span.set_tag("env", self._env)
    # ...
finally:
    span.finish(finish_time=event_unix_seconds)
```

## Observations

### No buffering -- different architecture from OTLP/Azure Monitor

The Datadog exporter does not implement its own event buffer. Instead, it creates spans immediately and relies on `ddtrace`'s internal batching and flushing. This is architecturally different from the OTLP and Azure Monitor exporters. The consequence is that `export()` does I/O work inline (creating a span object, setting tags), while the other exporters defer I/O to the `_flush_batch()` method.

### Good: Thorough config type validation

Like the Azure Monitor exporter, the Datadog exporter validates types for `service_name`, `env`, `version`, `agent_host`, and `agent_port`. Port range validation (1-65535) is correct.

### Test coverage is comprehensive

The test file covers configuration validation, span creation with correct timestamps, tag serialization for all types, lifecycle operations, and error handling. The mock pattern with `create_mock_ddtrace_module()` is appropriate for an optional dependency.

### [268] Tag namespace consistency

All event fields are prefixed with `elspeth.` (e.g., `elspeth.run_id`, `elspeth.timestamp`). Standard tags (`env`, `version`) are set without prefix. This is correct Datadog convention.

## Verdict

**Status:** NEEDS_REFACTOR
**Recommended action:** (1) The global environment variable mutation must be addressed -- either save and restore the original values on close, or use a ddtrace API that accepts agent configuration directly rather than via environment variables. (2) The `shutdown()` call on the global tracer singleton needs careful consideration -- the exporter should either create its own tracer instance or skip the shutdown call (just flush). (3) Add timezone normalization for naive timestamps to match the OTLP/Azure Monitor behavior. (4) Either implement `api_key` handling or remove it from the docstring. (5) Add recursion depth limit to dict flattening.
**Confidence:** HIGH -- Full analysis with complete context from protocol, manager, factory, events, test files, and comparison with sibling exporters.
