# Analysis: src/elspeth/engine/spans.py

**Lines:** 298
**Role:** Telemetry span management for pipeline execution tracing. Provides a `SpanFactory` that creates OpenTelemetry-compatible spans for each pipeline operation (run, source, row, transform, gate, aggregation, sink). Falls back to a singleton `NoOpSpan` when no tracer is configured.
**Key dependencies:** Imports `Tracer` and `Span` from OpenTelemetry (TYPE_CHECKING only). Used by `processor.py`, `executors.py`, `coalesce_executor.py`, and `orchestrator/core.py`.
**Analysis depth:** FULL

## Summary

This is a cleanly designed module that follows the null object pattern well. The `NoOpSpan` provides a zero-overhead fallback when tracing is disabled. The span methods have consistent structure and semantics. Two concerns: (1) an inconsistency in truthiness checks between `if node_id:` and `if token_id is not None:` that could suppress spans for empty-string IDs, and (2) the `NoOpSpan` class does not implement the full OpenTelemetry `Span` interface, which would cause `AttributeError` if any consumer calls an unimplemented method. Neither concern is currently triggered in the codebase.

## Warnings

### [176, 214, 255, 294] Inconsistent truthiness checks: `if node_id:` vs `if token_id is not None:`

**What:** The span methods use `if node_id:` (truthiness check) for the `node_id` parameter, but `if token_id is not None:` (identity check) for the `token_id` parameter. The truthiness check would suppress the attribute if `node_id` is an empty string `""`, while the identity check would still set the attribute for an empty string.

**Why it matters:** If a node_id is ever an empty string (due to a bug in ID generation or a default value), the span would silently omit the `node.id` attribute, making it impossible to correlate the span with the Landscape audit trail. The same inconsistency exists for `input_hash` and `batch_id`. While `NodeID` is unlikely to be empty string in practice (it is a `NewType(str)` that wraps UUIDs), this inconsistency signals an unintentional discrepancy.

**Evidence:**
```python
# transform_span (line 176-184):
if node_id:                     # Truthiness - suppresses ""
    span.set_attribute("node.id", node_id)
if input_hash:                  # Truthiness - suppresses ""
    span.set_attribute("input.hash", input_hash)
if token_ids is not None:       # Identity - allows empty list
    span.set_attribute("token.ids", tuple(token_ids))
elif token_id is not None:      # Identity - allows ""
    span.set_attribute("token.id", token_id)
```

The `token_id` checks use `is not None` consistently (correct), while `node_id`, `input_hash`, and `batch_id` checks use truthiness (inconsistent).

### [27-44] NoOpSpan does not implement full OpenTelemetry Span interface

**What:** `NoOpSpan` implements `set_attribute`, `set_status`, `record_exception`, and `is_recording`, but the OpenTelemetry `Span` interface also includes `add_event`, `update_name`, `end`, `get_span_context`, `add_link`, and context manager methods (`__enter__`/`__exit__`). If any consumer code (or future code) calls these methods on a `NoOpSpan` instance, it will raise `AttributeError`.

**Why it matters:** Currently, the consumers only use `set_attribute` on the yielded spans (confirmed via grep), so the missing methods are not exercised. However, the type hint `Iterator["Span | NoOpSpan"]` advertises `Span` compatibility. If a developer writes code that calls `span.add_event(...)` based on the type hint, it would fail at runtime with no tracer configured but work fine with a real tracer -- a subtle environment-dependent bug.

**Evidence:**
```python
class NoOpSpan:
    """No-op span for when tracing is disabled."""
    def set_attribute(self, key: str, value: Any) -> None: ...
    def set_status(self, status: Any) -> None: ...
    def record_exception(self, exception: Exception) -> None: ...
    def is_recording(self) -> bool: ...
    # Missing: add_event, update_name, end, get_span_context, add_link, __enter__, __exit__
```

## Observations

### [62-63] Singleton NoOpSpan avoids allocation overhead

The class-level `_NOOP_SPAN = NoOpSpan()` is a good optimization. Since `NoOpSpan` is stateless, a single instance is sufficient. All span methods yield this same instance when tracing is disabled, avoiding repeated allocations in the hot path (every row, every transform).

### [78-94] run_span provides clean context management

The `@contextmanager` decorator with the early-return pattern (`if self._tracer is None: yield self._NOOP_SPAN; return`) is clean and avoids nesting. The pattern is consistently applied across all span methods.

### [139-185] transform_span has the richest attribute set

The transform span correctly supports both single-token (`token_id`) and batch-token (`token_ids`) modes, with `token_ids` taking precedence. The docstring clearly documents the mutual exclusivity and use cases. The `node_id` parameter enables correlation with Landscape node_states.

### [265-298] sink_span correctly uses token_ids (plural)

Sinks batch-write multiple tokens, so using `token_ids` rather than `token_id` is correct. The conversion to `tuple()` ensures OpenTelemetry compatibility (OTEL requires sequence attributes to be tuples).

### No exception handling in span creation

The span methods do not catch exceptions from `self._tracer.start_as_current_span()`. If the OpenTelemetry tracer raises an exception during span creation, it would propagate to the caller and potentially crash the pipeline. This is acceptable per CLAUDE.md (the tracer is our code/configuration), but some teams prefer isolation between tracing and business logic. The OpenTelemetry SDK is generally designed to not throw, so this is low risk.

### Span attribute naming follows conventions

The attribute names follow OpenTelemetry semantic conventions: `run.id`, `row.id`, `token.id`, `plugin.name`, `plugin.type`, `node.id`, `input.hash`, `batch.id`, `token.ids`. This enables consistent querying in tracing backends (Jaeger, Tempo, etc.).

## Verdict

**Status:** SOUND
**Recommended action:** (1) Standardize truthiness checks to use `is not None` consistently for all optional string parameters, matching the `token_id` pattern. This is a low-effort change that improves consistency. (2) Consider adding stub methods to `NoOpSpan` for `add_event` and other commonly used `Span` methods to improve interface compatibility, or document that `NoOpSpan` only supports the subset of methods used by ELSPETH.
**Confidence:** HIGH -- The module is simple, well-structured, and the concerns are minor. No data integrity or security risks.
