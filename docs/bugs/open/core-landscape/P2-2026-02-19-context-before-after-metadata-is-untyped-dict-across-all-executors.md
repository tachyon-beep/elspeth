## Summary

Every node state in the Landscape records optional `context_before` and `context_after` metadata as `dict[str, Any] | None`. Different executor types (transform, gate, coalesce, aggregation) populate these with completely different shapes, but the type system treats them identically. This makes it impossible to know what structure to expect when reading audit data back.

## Severity

- Severity: moderate
- Priority: P2

## Location

- File: `src/elspeth/core/landscape/_node_state_recording.py` — Lines 59, 129, 142, 154, 166
- Producers: `engine/executors/transform.py`, `engine/executors/gate.py`, `engine/coalesce_executor.py`, `engine/executors/aggregation.py`

## Evidence

The same `dict[str, Any] | None` type carries fundamentally different shapes:

```python
# _node_state_recording.py — all use the same untyped parameter
def begin_node_state(self, ..., context_before: dict[str, Any] | None = None): ...
def complete_node_state(self, ..., context_after: dict[str, Any] | None = None): ...

# Gate executor passes: {"expression": ..., "result": ..., "routing_action": ...}
# Coalesce executor passes: {"policy": ..., "merge_strategy": ..., "field_collisions": ...}
# Aggregation executor passes: {"trigger_type": ..., "batch_id": ..., "row_count": ...}
# Transform executor passes: {"pool_stats": ..., "ordering": ...}
```

This is Tier 1 audit data — once recorded it is immutable and must be interpretable by downstream consumers (exporters, MCP analysis server, TUI explain screens).

## Proposed Fix

Define a union type or protocol for context metadata:

```python
ContextMetadata = (
    GateContextMetadata
    | CoalesceContextMetadata
    | AggregationContextMetadata
    | TransformContextMetadata
)
```

Each variant is a frozen dataclass with the appropriate fields. The `_node_state_recording` methods accept the union type. Serialization uses `to_dict()` for Landscape storage.

## Affected Subsystems

- `core/landscape/_node_state_recording.py` — parameter types
- `engine/executors/` — all executor types (construction)
- `core/landscape/exporter.py` — deserialization (reading back)
- `mcp/` — analysis server (reading back)
