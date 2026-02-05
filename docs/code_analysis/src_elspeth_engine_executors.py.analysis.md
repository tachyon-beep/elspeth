# Analysis: src/elspeth/engine/executors.py

**Lines:** 2,235
**Role:** The execution layer between the DAG processor and plugin code. Contains TransformExecutor, GateExecutor, AggregationExecutor, and SinkExecutor. Each executor wraps plugin calls (transforms, gates, sinks, batch transforms) with audit recording via the LandscapeRecorder, error handling with state tracking, span emission for telemetry, and token/lineage management. This is the enforcement point for the Three-Tier Trust Model -- Tier 2 pipeline data flows through here, and every decision is recorded to the audit trail.
**Key dependencies:**
- Imports from: `LandscapeRecorder`, `SpanFactory`, `ExpressionParser`, `TriggerEvaluator`, `PluginContext`, `TokenManager`, `stable_hash`, `PipelineRow`, `SchemaContract`, `TokenInfo`, `RoutingAction`, `TransformResult`, `GateResult`, `BatchTransformProtocol`, `GateProtocol`, `SinkProtocol`, `TransformProtocol`, `track_operation`, `SharedBatchAdapter`, `Clock`, `AggregationSettings`, `GateSettings`
- Imported by: `engine/processor.py` (TransformExecutor, GateExecutor, AggregationExecutor), `engine/orchestrator/core.py` (SinkExecutor, AggregationExecutor), `engine/orchestrator/aggregation.py` (AggregationExecutor)
- Delegates to: `batch_adapter.py` (SharedBatchAdapter for async batch transforms), `contract_propagation.py` (schema evolution), `transform_contract.py` (output contract creation)
**Analysis depth:** FULL

## Summary

The file is well-structured with disciplined audit recording. Every executor follows a consistent pattern: validate preconditions, begin node_state, execute plugin, populate audit fields, complete node_state. Error paths consistently close node_states before re-raising (preventing orphaned OPEN states). The code shows evidence of many bug fixes and is heavily commented. There are no critical data-integrity bugs that would silently corrupt the audit trail. However, there are several warnings around: (1) defensive `hasattr`/`getattr` usage that contradicts the project's stated anti-defensive-programming policy, (2) a shared mutable duration_ms used for all sink token states regardless of per-token timing, (3) duplicated `_to_dict` inner functions accessing private `_data` rather than using the public `to_dict()` API, and (4) AggregationExecutor state management that could be fragile under concurrent or re-entrant access patterns.

## Critical Findings

None identified. The audit recording is consistent and correct. Node states are always completed (either COMPLETED or FAILED) before control returns to the caller or an exception propagates. The deferred-outcome pattern in SinkExecutor (record outcomes only after flush durability) is correctly implemented.

## Warnings

### [168, 175, 258, 306] Defensive hasattr/getattr patterns violate CLAUDE.md anti-defensive-programming policy

**What:** Four instances of `hasattr()` and `getattr()` with defaults are used for batch transform detection and configuration:

- Line 168: `hasattr(transform, "_executor_batch_adapter")` -- storing adapter as an ad-hoc attribute on the transform object
- Line 175: `getattr(transform, "_pool_size", 30)` -- reading pool size with fallback default
- Line 258: `hasattr(transform, "accept") and callable(getattr(transform, "accept", None))` -- duck-typing batch detection
- Line 306: `getattr(transform, "_batch_wait_timeout", 3600.0)` -- reading timeout with fallback default

**Why it matters:** The project's CLAUDE.md explicitly states: "Do not use `.get()`, `getattr()`, `hasattr()`, `isinstance()`, or silent exception handling to suppress errors from nonexistent attributes." While each of these has a pragmatic justification (batch transforms are detected via duck typing rather than explicit protocol checks), this creates a fragile implicit contract. If a batch transform fails to set `_pool_size` or `_batch_wait_timeout`, the fallback default silently masks a configuration error. More seriously, the `has_accept` detection on line 258 means there is no compile-time or startup-time check that a transform claiming to be batch-aware actually implements the batch interface -- the check happens per-row at runtime.

**Evidence:**
```python
# Line 258: Duck-typing batch detection at runtime
has_accept = hasattr(transform, "accept") and callable(getattr(transform, "accept", None))

# Line 175: Silent default for pool size
max_pending = getattr(transform, "_pool_size", 30)

# Line 306: Silent default for timeout
wait_timeout = getattr(transform, "_batch_wait_timeout", 3600.0)
```

The `is_batch_aware` flag exists on the TransformProtocol (line 189 of protocols.py) and could be used instead of duck-typing. The `_pool_size` and `_batch_wait_timeout` could be formalized as protocol attributes with required values.

### [2165-2178] Shared duration_ms for all sink token node_states is inaccurate

**What:** In `SinkExecutor.write()`, after `sink.write()` and `sink.flush()` succeed, ALL token node_states are completed with the same `duration_ms` value (calculated from `sink.write()` only, not including the flush duration). The duration also represents the total batch write time, not the per-token processing time.

**Why it matters:** For audit trail accuracy, each token's node_state claims to have taken `duration_ms` to process. In reality, a single `sink.write()` call processed all tokens at once -- individual token processing time is unknowable. For a write of 1000 tokens taking 5000ms total, each token's state says "5000ms" which is misleading. Additionally, the `duration_ms` is set before `sink.flush()` (line 2117), so the flush latency (which can be significant for fsync/commit operations) is not captured in the token states.

**Evidence:**
```python
# Line 2117: duration measured at write completion (BEFORE flush)
duration_ms = (time.perf_counter() - start) * 1000

# Lines 2165-2178: All tokens get the same duration
for token, state in states:
    output_dict = token.row_data.to_dict()
    sink_output = { ... }
    self._recorder.complete_node_state(
        state_id=state.state_id,
        status=NodeStateStatus.COMPLETED,
        output_data=sink_output,
        duration_ms=duration_ms,  # Same for ALL tokens, excludes flush
    )
```

The flush duration IS captured indirectly through the operation's `track_operation` context manager (which measures the entire `with` block), but individual token node_states exclude it.

### [168-181] Storing batch adapter as ad-hoc attribute on transform instance

**What:** `_get_batch_adapter()` dynamically adds `_executor_batch_adapter` and `_batch_initialized` as instance attributes on the transform object via monkey-patching: `transform._executor_batch_adapter = adapter` and `transform._batch_initialized = True`.

**Why it matters:** This creates hidden coupling between the executor and the transform object's runtime state. The transform's class definition has no knowledge of these attributes, so:
1. Type checkers cannot verify correctness (hence the `# type: ignore` comments)
2. If the executor is instantiated multiple times for the same transform (e.g., during testing or reconfiguration), the stale adapter from the first executor persists
3. The attribute persists beyond the executor's lifetime, potentially causing issues if the transform is reused across runs

**Evidence:**
```python
# Lines 169-181
if not hasattr(transform, "_executor_batch_adapter"):
    adapter = SharedBatchAdapter()
    transform._executor_batch_adapter = adapter  # type: ignore[attr-defined]
    # ...
    transform._batch_initialized = True  # type: ignore[attr-defined]

return transform._executor_batch_adapter  # type: ignore[attr-defined, return-value, no-any-return]
```

The four `type: ignore` annotations are a signal that this pattern fights the type system rather than working with it. A cleaner approach would be an executor-owned `dict[TransformProtocol, SharedBatchAdapter]` mapping.

### [389-390, 1433-1434] Duplicated _to_dict inner functions accessing private _data attribute

**What:** Two identical inner functions `_to_dict()` and `_to_dict_agg()` are defined inside `execute_transform()` (line 389) and `execute_flush()` (line 1433) respectively. Both access `r._data` directly instead of calling `r.to_dict()`.

**Why it matters:**
1. **Code duplication**: Two copies of the same logic that must be kept in sync. If `PipelineRow.to_dict()` behavior changes (e.g., to filter fields or apply transforms), these raw `_data` accesses would diverge.
2. **Private attribute access**: `_data` is a private attribute of PipelineRow. While the access is functionally equivalent to `to_dict()`, it bypasses the public API and creates coupling to the internal representation (MappingProxyType). The CLAUDE.md explicitly recommends `row.to_dict()` over `dict(row)` for explicitness -- these do neither.
3. **Inconsistency**: Other places in the same file (lines 232, 592, 811, 1133, etc.) correctly use `to_dict()`. The inner functions are the exception.

**Evidence:**
```python
# Line 389-390 (execute_transform)
def _to_dict(r: dict[str, Any] | PipelineRow) -> dict[str, Any]:
    return dict(r._data) if isinstance(r, PipelineRow) else r

# Line 1433-1434 (execute_flush) -- identical logic, different name
def _to_dict_agg(r: dict[str, Any] | PipelineRow) -> dict[str, Any]:
    return dict(r._data) if isinstance(r, PipelineRow) else r
```

Both could be replaced with:
```python
r.to_dict() if isinstance(r, PipelineRow) else r
```

### [1392-1394] Batch state reset on exception in execute_flush may cause data loss on retry

**What:** When `transform.process()` raises an exception during `execute_flush()`, the batch state is reset (line 1393: `self._reset_batch_state(node_id)`), but the buffer is NOT cleared (lines 1483-1484 only execute on the success path). However, the batch in the database has been transitioned to FAILED status.

**Why it matters:** After this exception, the aggregation node has:
- No batch_id in memory (`_batch_ids[node_id]` deleted by `_reset_batch_state`)
- Buffers still contain the original rows
- Database batch is FAILED

If the caller retries by calling `buffer_row()` for the same node, a NEW batch will be created (line 1121) and the NEW rows will be buffered alongside the OLD rows still in the buffer. The old rows would then be processed twice -- once in the failed batch and once in the new batch -- creating duplicate batch_members in the audit trail.

However, after re-reading the code more carefully, lines 1483-1484 are reached in ALL cases (success and error both call `_reset_batch_state` and then continue to line 1483), because lines 1392-1394 re-raise the exception. The buffer clearing at 1483-1484 is NOT reached in the exception case. This means the buffer persists after a failed flush.

Whether this is a bug depends on the orchestrator's retry strategy. If the orchestrator re-calls `execute_flush()` without first re-buffering, the stale buffers would be re-processed. If it discards the AggregationExecutor entirely on failure, this is harmless. The current processor code would need verification.

**Evidence:**
```python
# Lines 1369-1394: Exception handler resets batch but NOT buffers
except Exception as e:
    # ...record failure...
    self._recorder.complete_batch(
        batch_id=batch_id,
        status=BatchStatus.FAILED,
        trigger_type=trigger_type,
        state_id=state.state_id,
    )
    # Reset for next batch
    self._reset_batch_state(node_id)  # Deletes batch_id and member_count
    raise  # Buffers still contain the data!

# Lines 1481-1484: Only reached on SUCCESS path
self._reset_batch_state(node_id)
self._buffers[node_id] = []          # Buffer cleared
self._buffer_tokens[node_id] = []    # Token buffer cleared
```

### [703-704] Potential None contract in fork path PipelineRow construction

**What:** When creating a `PipelineRow` for fork operations (line 710), the contract fallback logic on line 703 uses a falsy check (`if result.contract else token.row_data.contract`) rather than an explicit `is not None` check. An empty SchemaContract could be evaluated as falsy depending on its `__bool__` implementation.

**Why it matters:** If `result.contract` is a valid but "empty" SchemaContract (e.g., with zero fields in FLEXIBLE mode), the falsy check would skip it and use the input contract instead. The explicit `is not None` check at line 746 handles the same pattern correctly for the post-fork token update. While SchemaContract does not currently implement `__bool__`, this inconsistency between line 703 and line 746 suggests different intent.

**Evidence:**
```python
# Line 703: Uses truthiness check (inconsistent)
fork_contract: SchemaContract | None = result.contract if result.contract else token.row_data.contract

# Line 746: Uses truthiness check (same pattern but subtle)
output_contract: SchemaContract | None = result.contract if result.contract else token.row_data.contract
```

Both should use `is not None` for consistency and correctness:
```python
fork_contract = result.contract if result.contract is not None else token.row_data.contract
```

## Observations

### [66-75] Re-exports in __all__ create import confusion

**What:** `__all__` re-exports `TokenInfo` and `TriggerType` from their origin modules for "convenience." This means consumers can import these types from either `elspeth.contracts` or `elspeth.engine.executors`.

**Why it matters:** Dual import paths make it harder to trace where types come from and can cause confusion about module boundaries. It is minor but violates the principle that contracts are the canonical source for shared types.

### [77-78] Dual logging setup (stdlib + structlog)

**What:** Both `logging.getLogger(__name__)` and `structlog.get_logger(__name__)` are initialized at module scope. Some code uses `logger` (stdlib) and other code uses `slog` (structlog).

**Why it matters:** Inconsistent logging backends mean log aggregation must handle two different formats. The stdlib logger is used for operational warnings (line 2224: checkpoint failure), while structlog is used for structured debug events (line 450: pipeline_row_created). This is a minor consistency issue but can cause gaps in log monitoring if only one backend is configured.

### [1559-1563] Shadow re-import of logging module and logger variable

**What:** Inside `get_checkpoint_state()`, `import logging` is called again (line 1559) and `logger = logging.getLogger(__name__)` shadows the module-level `logger` (line 1563). Both reference the same object at runtime but it is confusing and could cause issues if the module-level logger is reconfigured.

**Evidence:**
```python
# Line 77: Module-level
logger = logging.getLogger(__name__)

# Line 1559-1563: Inside get_checkpoint_state() -- redundant shadow
import logging
logger = logging.getLogger(__name__)
```

### [1285] Re-import of PipelineRow inside execute_flush()

**What:** `from elspeth.contracts.schema_contract import PipelineRow` is imported inside `execute_flush()` at line 1285, even though `PipelineRow` is already available from the module-level import at line 30 (via `from elspeth.contracts import ... PipelineRow`).

**Why it matters:** This is dead code -- the local import shadows the already-available module-level import. It adds confusion about where `PipelineRow` comes from.

### [863-864] Coercion of non-string/non-bool expression results

**What:** In `execute_config_gate()`, if the expression evaluator returns a value that is neither `bool` nor `str`, it is coerced to string via `str(eval_result)` (line 864). This is a silent coercion of unexpected types.

**Why it matters:** If the expression parser returns an integer, float, list, or other type, the silent `str()` coercion produces a route label that probably won't match any configured route, leading to a `ValueError` on line 879. The error message would say the label (e.g., `"42"` or `"[1, 2, 3]"`) was not found in routes, which is uninformative. A better approach would be to raise immediately on unexpected types.

### [2216-2233] Checkpoint failure after durable sink write logs error but continues

**What:** If `on_token_written()` (the checkpoint callback) fails after a successful and durable sink write, the exception is caught, logged, and swallowed (line 2219-2233). The comment acknowledges this creates potential for duplicate writes on resume.

**Why it matters:** This is the documented trade-off for RC-1 (Bug #10). It is correctly implemented -- the sink write is durable and cannot be rolled back, so continuing is the only option. The logging is thorough with token_id and error details. This is noted for completeness; no action is needed.

### [1071-1086] AggregationExecutor manages significant mutable state

**What:** The AggregationExecutor maintains five dictionaries of mutable state: `_member_counts`, `_batch_ids`, `_aggregation_settings`, `_trigger_evaluators`, `_buffers`, `_buffer_tokens`, and `_restored_states` (seven total). All are keyed by `NodeID`.

**Why it matters:** This amount of correlated mutable state is a maintenance burden. The invariant "if `_batch_ids[node_id]` exists, then `_buffers[node_id]`, `_buffer_tokens[node_id]`, and `_member_counts[batch_id]` must also exist" is enforced implicitly through code ordering rather than through a combined data structure. The code handles this correctly through careful validation (e.g., line 1256-1262 wraps buffer access in try/except), but future modifications to any one dictionary's lifecycle must update the others consistently or risk silent state corruption.

### [410-426] Schema evolution recording only for single-row results

**What:** The schema evolution check on line 409 (`if result.row is not None and transform.transforms_adds_fields`) only records evolved contracts for single-row transform results. Multi-row results (where `result.rows is not None`) skip evolution recording entirely.

**Why it matters:** If a transform both `transforms_adds_fields=True` AND returns multi-row results via `success_multi()`, the evolved contract is not recorded to the audit trail. This is likely intentional (multi-row expansion is a deaggregation pattern where schema is typically unchanged), but the implicit skip is undocumented.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** Address the warnings in priority order:
1. **Buffer cleanup on failed flush** (line 1392-1394): Verify with orchestrator code that stale buffers after failed flush are handled correctly. If not, clear buffers in the exception handler.
2. **hasattr/getattr patterns** (lines 168, 175, 258, 306): Formalize batch transform detection using the existing `is_batch_aware` protocol flag. Add `_pool_size` and `_batch_wait_timeout` to the `BatchTransformProtocol` or a mixin protocol.
3. **Monkey-patched adapter storage** (line 170): Move to executor-owned mapping.
4. **Deduplicate _to_dict** (lines 389, 1433): Extract to module-level utility or use `to_dict()`.
5. **Truthiness vs None check** (line 703, 746): Use `is not None` consistently.

**Confidence:** HIGH -- The file was read in its entirety, all key dependencies were examined (contracts, protocols, results, identity, routing, operations, batch_adapter, processor), and every finding was verified against the actual code and its documented contracts. The analysis accounts for the Three-Tier Trust Model, the CLAUDE.md anti-defensive-programming policy, and the audit integrity requirements.
