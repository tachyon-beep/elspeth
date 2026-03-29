## Summary

`SpanFactory` claims child span names are static, but it actually embeds config-driven plugin/node names into the OpenTelemetry span name, creating unbounded operation-name cardinality in tracing backends.

## Severity

- Severity: minor
- Priority: P2

## Location

- File: `/home/john/elspeth/src/elspeth/engine/spans.py`
- Line(s): 106, 169, 207, 248, 287
- Function/Method: `source_span`, `transform_span`, `gate_span`, `aggregation_span`, `sink_span`

## Evidence

`spans.py` documents a static-name contract:

```python
# /home/john/elspeth/src/elspeth/engine/spans.py:6-12
Span Hierarchy (span names are static; IDs are set as attributes):
    run                          [run.id=<run_id>]
    ├── source:<source_name>
    ├── row                      [row.id=<row_id>, token.id=<token_id>]
    │   ├── transform:<name>
    │   └── sink:<name>
    └── aggregation:<name>
```

But the implementation puts config-controlled identifiers directly into the span name:

```python
# /home/john/elspeth/src/elspeth/engine/spans.py:106-109
with self._tracer.start_as_current_span(f"source:{source_name}") as span:

# /home/john/elspeth/src/elspeth/engine/spans.py:169-181
with self._tracer.start_as_current_span(f"transform:{transform_name}") as span:
    span.set_attribute("plugin.name", transform_name)
    span.set_attribute("plugin.type", "transform")
    if node_id is not None:
        span.set_attribute("node.id", node_id)

# /home/john/elspeth/src/elspeth/engine/spans.py:207-216
with self._tracer.start_as_current_span(f"gate:{gate_name}") as span:

# /home/john/elspeth/src/elspeth/engine/spans.py:248-259
with self._tracer.start_as_current_span(f"aggregation:{aggregation_name}") as span:

# /home/john/elspeth/src/elspeth/engine/spans.py:287-293
with self._tracer.start_as_current_span(f"sink:{sink_name}") as span:
```

Those names are not engine-static. They come from user/config wiring:

```python
# /home/john/elspeth/src/elspeth/core/config.py:405
name: str = Field(description="Aggregation identifier (unique within pipeline)")

# /home/john/elspeth/src/elspeth/core/config.py:489
name: str = Field(description="Gate identifier (unique within pipeline)")

# /home/john/elspeth/src/elspeth/core/config.py:857
name: str = Field(description="Unique identifier for this transform (drives node IDs and audit records)")
```

Sink names are also user-defined identifiers validated from config keys:

```python
# /home/john/elspeth/src/elspeth/core/config.py:1417-1437
def validate_sink_names_lowercase(cls, v: dict[str, SinkSettings]) -> dict[str, SinkSettings]:
    for sink_name in v:
        _validate_max_length(sink_name, ...)
        _validate_connection_name_chars(sink_name, ...)
```

So every distinct pipeline label produces a distinct span operation name even though the same information is already captured in attributes like `plugin.name` and `node.id`.

## Root Cause Hypothesis

The span factory mixed two different concerns: human-readable operation labels and low-cardinality tracing identity. The file’s design comment says dynamic identifiers belong in attributes, but the implementation used f-strings for child span names anyway. Existing tests only enforce stability for `run` and `row`, so the dynamic-name regression on child spans was never caught.

## Suggested Fix

Use static span names for child operations and keep all variable identity in attributes that are already present.

Example:

```python
with self._tracer.start_as_current_span("transform") as span:
    span.set_attribute("plugin.name", transform_name)
    span.set_attribute("plugin.type", "transform")
    if node_id is not None:
        span.set_attribute("node.id", node_id)
```

Apply the same pattern to `source`, `gate`, `aggregation`, and `sink`. Update `tests/unit/engine/test_spans.py` to assert static span names plus the dynamic attributes, rather than asserting names like `transform:foo`.

## Impact

Tracing backends will see a separate operation name for every configured transform/gate/aggregation/sink label, which fragments dashboards, breaks stable aggregation/alerting, and makes cross-run comparison harder than necessary. The audit trail remains intact, but Tier 1 observability becomes noisier and less queryable precisely where `spans.py` is supposed to provide structured, reusable span semantics.
