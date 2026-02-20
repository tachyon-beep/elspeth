## Summary

Node state context metadata (`context_before` and `context_after`) flows through the Landscape recording layer as `dict[str, Any] | None`. Two production sites construct `context_after` dicts with well-defined but untyped shapes that become permanent Tier 1 audit data. Additionally, `context_before` is declared as a parameter on `begin_node_state()` but is never called by any executor — it is dead code.

## Severity

- Severity: moderate
- Priority: P2

## Location

### Recording boundary (serialization to Landscape)

- File: `src/elspeth/core/landscape/_node_state_recording.py`
  - Line 59: `begin_node_state(..., context_before: dict[str, Any] | None = None)` — **never called with a value**
  - Lines 129, 142, 154, 166: `complete_node_state(..., context_after: dict[str, Any] | None = None)` — overloads

### Producers (construction sites)

- File: `src/elspeth/plugins/llm/base_multi_query.py`
  - Lines 438-442: `pool_context` dict construction — **untyped**
  - Lines 358, 383: Passed to `TransformResult.error()` / `TransformResult.success()`
- File: `src/elspeth/engine/coalesce_executor.py`
  - Line 625: `context_after={"coalesce_context": coalesce_metadata.to_dict()}` — inner value is typed (`CoalesceMetadata`), but wrapper dict is `dict[str, Any]`

### Transit layer

- File: `src/elspeth/contracts/results.py`
  - Line 124: `context_after: dict[str, Any] | None` field on `TransformResult`
- File: `src/elspeth/engine/executors/transform.py`
  - Lines 409, 434: Passes `result.context_after` to guard
- File: `src/elspeth/engine/executors/state_guard.py`
  - Line 159: Forwards via `**kwargs` (untyped pass-through)

### Storage

- File: `src/elspeth/core/landscape/schema.py`
  - Lines 215-216: `context_before_json TEXT`, `context_after_json TEXT`

### Contract types

- File: `src/elspeth/contracts/audit.py`
  - `NodeStateOpen.context_before_json: str | None`
  - `NodeStatePending.context_before_json + context_after_json: str | None`
  - `NodeStateCompleted.context_before_json + context_after_json: str | None`
  - `NodeStateFailed.context_before_json + context_after_json: str | None`

## Evidence

### Issue 1: Pool execution context is fully untyped

`base_multi_query.py` constructs a `pool_context` dict from `PooledExecutor.get_stats()` and per-query ordering data, then passes it through `TransformResult.context_after`:

```python
# base_multi_query.py:438-442 — construction
pool_context = {
    "pool_config": pool_stats["pool_config"],     # from PooledExecutor.get_stats()
    "pool_stats": pool_stats["pool_stats"],       # from PooledExecutor.get_stats()
    "query_ordering": query_ordering,              # list of per-query dicts
}

# base_multi_query.py:383 — flows to TransformResult
return TransformResult.success(
    PipelineRow(output, observed),
    success_reason={"action": "enriched", "fields_added": all_fields_added},
    context_after=pool_context,  # dict[str, Any]
)
```

The shape of `pool_context` is well-defined:

```python
{
    "pool_config": {
        "pool_size": int,
        "max_capacity_retry_seconds": float,
        "dispatch_delay_at_completion_ms": float,
    },
    "pool_stats": {
        "capacity_retries": int,
        "successes": int,
        "peak_delay_ms": float,
        "current_delay_ms": float,
        "total_throttle_time_ms": float,
        "max_concurrent_reached": int,
    },
    "query_ordering": [
        {
            "submit_index": int,
            "complete_index": int,
            "buffer_wait_ms": float,
        },
    ],
}
```

This shape is stable — defined by `PooledExecutor.get_stats()` (executor.py:183-197) and the ordering comprehension (base_multi_query.py:430-436). Both are system code with no runtime variability.

### Issue 2: Coalesce context wrapper is untyped

The coalesce executor wraps the already-typed `CoalesceMetadata` in a bare dict:

```python
# coalesce_executor.py:625
context_after={"coalesce_context": coalesce_metadata.to_dict()}
```

`CoalesceMetadata` is a proper frozen dataclass (introduced in commit `4f7e43be`), but the wrapping `{"coalesce_context": ...}` is a `dict[str, Any]`. The wrapping layer is unnecessary — the coalesce executor could pass the metadata directly.

### Issue 3: `context_before` is dead code

`begin_node_state()` declares a `context_before: dict[str, Any] | None = None` parameter, but **no caller in the entire codebase passes it**:

- `NodeStateGuard.__enter__()` (state_guard.py:85-92): does not pass `context_before`
- `CoalesceExecutor.accept()` (coalesce_executor.py:241, 300): does not pass `context_before`
- `RowProcessor._load_source()` (processor.py:1149, 1213): does not pass `context_before`
- `GateExecutor._execute_gate()` (gate.py:222): does not pass `context_before`
- `SinkExecutor._write_to_sink()` (sink.py:154): does not pass `context_before`
- `Orchestrator._process_quarantine()` (core.py:1411): does not pass `context_before`

The parameter was introduced when `_node_state_recording.py` was extracted from the monolithic `LandscapeRecorder` (commit `85f94895`) and has never been used.

### Issue 4: `state_guard.py` erases type information

`NodeStateGuard.complete()` uses `**kwargs: Any` to forward arguments:

```python
# state_guard.py:151
def complete(self, status: NodeStateStatus, **kwargs: Any) -> None:
    self._recorder.complete_node_state(
        state_id=self.state_id,
        status=status,
        **kwargs,
    )
```

Even if `context_after` were typed upstream, the `**kwargs` pass-through loses all type information. The `# type: ignore[call-overload]` comment on line 159 confirms this is a known type-safety gap.

## Root Cause

The `context_after` mechanism was introduced in commit `f9efc942` (2026-02-02) specifically for pool metadata in LLM multi-query transforms. It was designed as a generic `dict[str, Any]` "operational metadata" extension point. The coalesce executor later adopted it (commit `4f7e43be`) after `CoalesceMetadata` was typed, but the wrapping layer remained untyped. The original generic design was reasonable for a single use case, but now that both producers have stable, well-defined shapes, the generic dict is an unnecessary loss of type safety at a Tier 1 boundary.

## Downstream Consumer Analysis

| Consumer | References context fields? | Interpretation |
|----------|---------------------------|----------------|
| Landscape exporter | Yes (exporter.py:410-474) | **Pass-through** — copies JSON text as-is |
| MCP analysis server | No | Never references context_before/after |
| TUI explain screens | No | Never references context_before/after |
| Tests | Yes (10 files) | Assert shapes in unit/integration tests |

No consumer currently parses the JSON back into structured types. This reduces the immediate impact but means the type boundary violation exists purely at the write path.

## Suggested Fix

### 1. Create `PoolExecutionContext` frozen dataclass in `contracts/`

```python
@dataclass(frozen=True, slots=True)
class QueryOrderEntry:
    submit_index: int
    complete_index: int
    buffer_wait_ms: float

@dataclass(frozen=True, slots=True)
class PoolConfig:
    pool_size: int
    max_capacity_retry_seconds: float
    dispatch_delay_at_completion_ms: float

@dataclass(frozen=True, slots=True)
class PoolStats:
    capacity_retries: int
    successes: int
    peak_delay_ms: float
    current_delay_ms: float
    total_throttle_time_ms: float
    max_concurrent_reached: int

@dataclass(frozen=True, slots=True)
class PoolExecutionContext:
    pool_config: PoolConfig
    pool_stats: PoolStats
    query_ordering: tuple[QueryOrderEntry, ...]

    def to_dict(self) -> dict[str, Any]: ...
```

### 2. Type `TransformResult.context_after`

Change from `dict[str, Any] | None` to a union:

```python
NodeStateContext = PoolExecutionContext | CoalesceMetadata
# TransformResult.context_after: NodeStateContext | None
```

The coalesce executor doesn't go through `TransformResult`, so its path is separate — it can pass `CoalesceMetadata.to_dict()` directly to `complete_node_state()`.

### 3. Update recording boundary

Change `_node_state_recording.py` to accept typed context:

```python
def complete_node_state(self, ..., context_after: NodeStateContext | dict[str, Any] | None = None):
    # Accept both typed and dict for backwards compatibility during migration
    if hasattr(context_after, 'to_dict'):
        context_dict = context_after.to_dict()
    else:
        context_dict = context_after
    context_json = canonical_json(context_dict) if context_dict is not None else None
```

### 4. Remove dead `context_before` parameter

Remove `context_before` from `begin_node_state()` since no caller uses it. If it's needed in the future, it can be re-added with a proper type.

### 5. Type `PooledExecutor.get_stats()` return

Change `PooledExecutor.get_stats()` from `dict[str, Any]` to return `PoolExecutionContext` (or its component types), eliminating the untyped dict at the source.

## Impact

- **Audit integrity**: Untyped dicts at the Tier 1 boundary means the recording layer cannot structurally validate what it stores. Any misspelled key or wrong value type would be silently serialized as canonical JSON and become permanent audit data.
- **Dead code**: The unused `context_before` parameter adds confusion about what the API supports vs. what is actually used. New executors might try to use it without realizing it has no established pattern.
- **Type erasure**: The `state_guard.py` `**kwargs` pattern loses all type information at the transit layer, preventing mypy from catching shape mismatches.

## Related Commits

| Commit | Date | Description |
|--------|------|-------------|
| `f9efc942` | 2026-02-02 | Feature: introduced `context_after` for pool metadata |
| `58f4cbdc` | 2026-02-02 | Fix: context_after wasn't flowing to failed node states |
| `4f7e43be` | 2026-02-19 | Fix: `CoalesceMetadata` frozen dataclass replacing loose dicts |
| `85f94895` | Earlier | Refactor: decomposed LandscapeRecorder into mixins (introduced `_node_state_recording.py`) |

## Affected Subsystems

- `contracts/results.py` — `TransformResult.context_after` field type
- `contracts/` — new `PoolExecutionContext` dataclass module
- `plugins/llm/base_multi_query.py` — pool context construction (lines 438-442)
- `plugins/pooling/executor.py` — `get_stats()` return type (line 170)
- `plugins/pooling/throttle.py` — `get_stats()` return type (line 130)
- `engine/coalesce_executor.py` — wrapper dict removal (line 625)
- `engine/executors/state_guard.py` — `**kwargs` type narrowing (line 151)
- `engine/executors/transform.py` — pass-through typing (lines 409, 434)
- `core/landscape/_node_state_recording.py` — parameter types, dead code removal
- `tests/` — 10 files with context_after assertions
