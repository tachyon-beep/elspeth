# Analysis: src/elspeth/engine/processor.py

**Lines:** 2,004
**Role:** The RowProcessor -- DAG traversal engine with work queue. Takes rows from the source, pushes them through transforms/gates in topological order, handles fork/join semantics, manages token identity via TokenManager, and delivers results to sinks. This is the inner loop of pipeline execution.
**Key dependencies:**
- **Imports from:** `elspeth.contracts` (RowOutcome, RowResult, SourceRow, TokenInfo, TransformResult, PipelineRow, RoutingKind, OutputMode, TriggerType, OrchestrationInvariantError, TransformErrorReason, FailureInfo), `elspeth.core.config` (AggregationSettings, GateSettings), `elspeth.core.landscape` (LandscapeRecorder), `elspeth.engine.executors` (AggregationExecutor, GateExecutor, TransformExecutor), `elspeth.engine.retry` (MaxRetriesExceeded, RetryManager), `elspeth.engine.tokens` (TokenManager), `elspeth.engine.coalesce_executor` (CoalesceExecutor), `elspeth.engine.spans` (SpanFactory), `elspeth.plugins.clients.llm` (LLMClientError), `elspeth.plugins.protocols` (BatchTransformProtocol, GateProtocol, TransformProtocol)
- **Imported by:** `elspeth.engine.orchestrator.core`, `elspeth.engine.orchestrator.aggregation` (the orchestrator instantiates and calls RowProcessor methods)
**Analysis depth:** FULL

## Summary

The RowProcessor is a well-structured but very complex file that manages the inner loop of DAG execution. Its work queue approach to fork/join semantics is sound with a proper iteration guard (10,000 max). The most concerning patterns are: (1) a step-indexing convention that mixes 0-indexed and 1-indexed values across multiple code paths, creating high risk of off-by-one errors when modifying any of these paths; (2) significant code duplication between `_process_batch_aggregation_node` and `handle_timeout_flush` that could diverge; (3) direct access to `transform._on_error` private attributes, coupling the processor to internal implementation details of plugins. The audit trail integrity discipline is strong -- outcomes are recorded at the correct points, and the telemetry/Landscape ordering invariants are well-documented. No critical data integrity issues were found, but several latent risk patterns warrant attention.

## Critical Findings

### [1227, 1256] Direct access to `transform._on_error` private attribute in retry-fallback path

**What:** When `retry_manager` is None and a retryable exception is caught, the code accesses `transform._on_error` directly (lines 1227 and 1256). This is a private attribute of the transform plugin that is not part of `TransformProtocol`.

**Why it matters:** This couples the processor to an implementation detail. If a transform plugin implementation changes how `_on_error` is stored (e.g., renaming it, making it a property, etc.), this code will crash at runtime -- and only on the specific path where retry_manager is None AND a retryable exception occurs. This path is unlikely to be well-tested because it requires a very specific combination of conditions. Additionally, `TransformProtocol` does not declare `_on_error` as a protocol attribute (confirmed in protocols.py), so mypy cannot verify this access.

**Evidence:**
```python
# Line 1227
on_error = transform._on_error
if on_error is None:
    raise RuntimeError(...)

# Line 1256
on_error = transform._on_error
if on_error is None:
    raise RuntimeError(...)
```

The `TransformExecutor.execute_transform()` in executors.py accesses the same attribute (around line 460+), so the coupling is at least consistent, but the private attribute access is fragile in both places. If the team ever standardizes this to a protocol attribute (e.g., `on_error_destination`), missing this file would create a runtime failure only on the no-retry+retryable-exception path.

### [659, 985, 1110] Work item `start_step` calculation inconsistency between flush paths

**What:** The `start_step` value set in `_WorkItem` has different conventions depending on which code path creates the work item:

- In `handle_timeout_flush` (line 659, 743): `start_step=step` where `step` is the 0-indexed current aggregation position.
- In `_process_batch_aggregation_node` (line 985, 1110): `continuation_start = coalesce_at_step if coalesce_at_step is not None else step` where `step` is 1-indexed (audit step).
- The orchestrator (aggregation.py line 212) then does `continuation_start = work_item.start_step + 1` for the non-coalesce path.

**Why it matters:** The two code paths (`handle_timeout_flush` and `_process_batch_aggregation_node`) use different step indexing conventions for the same `_WorkItem.start_step` field. The orchestrator compensates by adding +1, but this creates a fragile implicit contract between processor and orchestrator about what `start_step` means. A developer modifying either side without understanding both conventions could introduce off-by-one errors that cause tokens to skip a transform or re-execute one. The comments in the code acknowledge this complexity (lines 654-655, 981-983, 1106-1108) but the dual convention is inherently error-prone.

**Evidence:**
```python
# handle_timeout_flush line 659: 0-indexed
child_items.append(
    _WorkItem(
        token=updated_token,
        start_step=step,  # 0-indexed current position
    )
)

# _process_batch_aggregation_node line 985: 1-indexed
continuation_start = coalesce_at_step if coalesce_at_step is not None else step
# Where step = start_step + step_offset + 1 (1-indexed for audit)
```

The comment at line 981-983 explains: "step is 1-indexed (for audit) but happens to equal the 0-indexed position of the NEXT transform." This "happens to equal" coincidence is relied upon as a correctness invariant.

## Warnings

### [764-1179] Massive code duplication between `_process_batch_aggregation_node` and `handle_timeout_flush`

**What:** These two methods implement nearly identical logic for handling aggregation flush outcomes (passthrough mode, transform mode, error handling, telemetry emission, contract validation, coalesce routing). `_process_batch_aggregation_node` is ~415 lines, `handle_timeout_flush` is ~260 lines, with substantial overlap.

**Why it matters:** Any fix applied to one path that is not applied to the other creates a divergence bug. The telemetry bug P2-2026-02-01 is documented as being fixed in both paths, suggesting this has already been a source of bugs. Future modifications to aggregation output handling will need to be made in parallel in both methods.

**Evidence:** Compare the passthrough mode handling:
- `handle_timeout_flush` lines 616-672
- `_process_batch_aggregation_node` lines 939-1014

Both do the same sequence: validate `is_multi_row`, validate `rows is not None`, validate row count matches, validate contract, create PipelineRow objects, determine `more_transforms`, derive coalesce metadata, queue work items or return COMPLETED. The transform mode blocks are similarly duplicated.

### [1618] `total_steps` calculation includes config gates but fork/coalesce step math may not account for them

**What:** Line 1618 computes `total_steps = len(transforms) + len(self._config_gates)`. This is used in `_maybe_coalesce_token` to determine whether a coalesce point has been reached (via `step_completed >= coalesce_at_step`). However, `coalesce_at_step` and `coalesce_step_map` values are populated from DAG construction which may or may not include config gates in the step numbering.

**Why it matters:** If `coalesce_step_map` uses a different step space than the processor's `total_steps`, a coalesce point intended after the last transform but before config gates could either never trigger or trigger prematurely. This is difficult to verify without reading the DAG construction code, but the heterogeneous step numbering is a latent risk.

**Evidence:**
```python
# Line 1618
total_steps = len(transforms) + len(self._config_gates)

# Line 1982 - final coalesce check uses total_steps + 1
final_step = total_steps + 1 if coalesce_at_step is not None else total_steps
```

### [1632] Transform iteration uses `list[Any]` type annotation

**What:** The `transforms` parameter throughout the processor is typed as `list[Any]` (lines 384, 1312, 1392, 1463, 1593). The iteration then uses `isinstance` checks against `GateProtocol` and `TransformProtocol` to determine behavior.

**Why it matters:** The `Any` type eliminates static type checking for the most critical data flow in the system. A caller could pass non-plugin objects in the transforms list and the error would only be caught at the `else: raise TypeError(...)` branch at line 1884, deep inside processing. This reduces the value of mypy for catching integration bugs.

**Evidence:**
```python
# Line 1312
def process_row(
    self,
    row_index: int,
    source_row: SourceRow,
    transforms: list[Any],  # <-- Any
    ctx: PluginContext,
    ...
```

### [381-437, 1309-1387, 1389-1459, 1461-1511] Four near-identical work queue loops

**What:** The methods `process_token_from_step`, `process_row`, `process_existing_row`, and `process_token` all contain essentially the same work queue loop: initialize deque, iterate with guard, call `_process_single_token`, collect results, extend queue. The only differences are how the initial token/work item is created.

**Why it matters:** A fix to the work queue logic (e.g., changing the iteration guard, adding error handling, or modifying result collection) needs to be applied to all four loops. This is the same class of duplication risk as the aggregation flush paths.

**Evidence:** Each method has:
```python
work_queue: deque[_WorkItem] = deque([_WorkItem(...)])
results: list[RowResult] = []
iterations = 0
with self._spans.row_span(token.row_id, token.token_id):
    while work_queue:
        iterations += 1
        if iterations > MAX_WORK_QUEUE_ITERATIONS:
            raise RuntimeError(...)
        item = work_queue.popleft()
        result, child_items = self._process_single_token(...)
        if result is not None:
            if isinstance(result, list):
                results.extend(result)
            else:
                results.append(result)
        work_queue.extend(child_items)
return results
```

### [1676] Fork child `next_step` calculation for plugin gates

**What:** Line 1676 computes `next_step = start_step + step_offset + 1` for fork children. When fork children have no coalesce point, they start at `next_step` which is the step after the gate. However, if the fork gate is the last transform in the list and there are config gates after it, the children skip directly to the config gate loop at line 1887. This appears correct but the transition from transform iteration to config gate iteration is implicit -- it relies on the `for step_offset, transform in enumerate(transforms[start_step:])` loop naturally exhausting.

**Why it matters:** Fork children that should continue through config gates after the last transform will do so because the transform loop ends and the config gate loop runs. But if `next_step` happens to equal `len(transforms)`, the loop `transforms[next_step:]` yields zero iterations and falls through to config gates -- this works but is fragile because it depends on list slicing behavior for out-of-range indices.

**Evidence:**
```python
# Line 1676
next_step = start_step + step_offset + 1
for child_token in outcome.child_tokens:
    # ...
    child_items.append(
        _WorkItem(
            token=child_token,
            start_step=child_coalesce_step if child_coalesce_step is not None else next_step,
        )
    )
```

### [1936] Config gate fork step calculation

**What:** Line 1936 sets `next_config_step = gate_idx + 1` but then line 1951 computes `start_step = len(transforms) + next_config_step` for non-coalesce children. This uses the raw `gate_idx` from the enumerated loop (line 1895: `enumerate(self._config_gates[config_gate_start_idx:], start=config_gate_start_idx)`). When `config_gate_start_idx > 0`, the `gate_idx` correctly starts from the adjusted index, so the step calculation should be correct.

**Why it matters:** The interplay between `config_gate_start_idx` offset and `gate_idx` numbering is non-obvious. If the `start=config_gate_start_idx` parameter were accidentally removed from the `enumerate` call, all config gate fork step calculations would be wrong. The step arithmetic here spans three different references (transforms count, gate index, config gate start index) with no centralized step calculator.

**Evidence:**
```python
# Line 1894-1895
config_gate_start_idx = max(0, start_step - len(transforms))
for gate_idx, gate_config in enumerate(self._config_gates[config_gate_start_idx:], start=config_gate_start_idx):
    step = config_gate_start_step + gate_idx

# Line 1936, 1951
next_config_step = gate_idx + 1
# ...
start_step=cfg_coalesce_step if cfg_coalesce_step is not None else len(transforms) + next_config_step,
```

### [51-61] `_extract_dict` accesses `row._data` directly

**What:** The module-level `_extract_dict` function accesses the `_data` attribute of PipelineRow directly (line 60: `dict(row._data)`). PipelineRow has a `to_dict()` method which is the documented public API.

**Why it matters:** If PipelineRow's internal storage changes from `_data` to something else, this function will break. The same pattern exists in `results.py` (`_extract_dict_from_row`), so it's at least consistent, but it bypasses the public interface. This is a minor concern since PipelineRow is system-owned code, but the inconsistency with the documented preference for `to_dict()` from CLAUDE.md is notable.

**Evidence:**
```python
def _extract_dict(row: dict[str, Any] | PipelineRow) -> dict[str, Any]:
    if isinstance(row, PipelineRow):
        return dict(row._data)  # Direct private attribute access
    return row
```

## Observations

### [197] Telemetry emission silently drops events when manager is None

**What:** Line 197-198: `if self._telemetry_manager is not None: self._telemetry_manager.handle_event(event)`. When telemetry_manager is None, events are silently dropped.

**Why it matters:** CLAUDE.md's telemetry section says: "Any time an object is polled or has an opportunity to emit telemetry, it MUST either: 1. Send what it has, OR 2. Explicitly acknowledge 'I have nothing'." The `_emit_telemetry` method does neither when the manager is None -- it silently drops. However, the telemetry manager being None is a configuration choice (telemetry disabled), not a runtime failure, so the "log once at startup" provision likely covers this. The concern is minor.

### [226] Assert used for runtime invariant checking

**What:** Line 226: `assert transform.node_id is not None, "node_id must be assigned..."`. Asserts can be disabled with `python -O`. This is used throughout the telemetry emission methods (lines 226, 1650).

**Why it matters:** If the pipeline is ever run with `-O` flag (assertions disabled), missing node_ids would cause `AttributeError` or `None` to flow into telemetry/audit records instead of crashing early with a clear message. For a system that emphasizes "crash on our bugs," using `if ... is None: raise` would be more robust than `assert`.

### [236] `duration_ms or 0.0` in TransformCompleted event creation

**What:** Line 236: `duration_ms=transform_result.duration_ms or 0.0`. If `duration_ms` is exactly 0.0 (a valid measurement for very fast transforms), this would use the default `0.0` anyway, so the behavior is correct. But if the intent is to handle `None`, using `if ... is not None` would be clearer.

**Why it matters:** Minor correctness: `0.0 or 0.0` evaluates to `0.0` because `0.0` is falsy, which then takes the right operand `0.0`. So the result is the same. But the intent is ambiguous -- is `0.0` a sentinel for "no measurement" or a real measurement?

### [1280] Mutable dict used as attempt tracker in closure

**What:** Line 1280: `attempt_tracker = {"current": 0}` is used as a mutable closure variable to track attempts across retries. This is a Python pattern for working around closure capture semantics (closures capture by reference, but rebinding a local doesn't affect the outer scope).

**Why it matters:** This is a correct but slightly unusual pattern. A `nonlocal` statement or a simple list `[0]` would also work. The dict approach is fine but adds cognitive overhead for readers who might wonder why a dict is used instead of a simple integer.

### [571-573] TokenCompleted emitted even when CoalesceExecutor already recorded outcomes

**What:** Line 1572-1573: When `coalesce_outcome.failure_reason` is present, TokenCompleted telemetry is always emitted, even when `coalesce_outcome.outcomes_recorded` is True. The Landscape recording (line 1565-1571) is correctly gated on `not outcomes_recorded`, but telemetry emission is not.

**Why it matters:** This could cause duplicate TokenCompleted telemetry events -- once from CoalesceExecutor's internal handling and once from the processor's `_emit_token_completed` call. Telemetry is ephemeral (not the legal record), so this is not a data integrity issue, but it could cause incorrect counts in observability dashboards.

**Evidence:**
```python
# Line 1565-1571: Landscape recording is gated
if not coalesce_outcome.outcomes_recorded:
    self._recorder.record_token_outcome(...)

# Line 1572-1573: Telemetry is NOT gated
self._emit_token_completed(current_token, RowOutcome.FAILED)
```

### [1838] PipelineRow private attribute access in expand path

**What:** Line 1838: `dict(r._data) if isinstance(r, PipelineRow) else r`. Same private attribute access pattern as `_extract_dict`.

### [884] Catch-all else branch for unknown transform types

**What:** Line 1884: `raise TypeError(f"Unknown transform type: {type(transform).__name__}...")`. This is a good safety net, but the error message references "BaseTransform or BaseGate" which are class names that may not exist anymore (the code uses protocol-based detection, not class inheritance).

**Why it matters:** Misleading error messages slow down debugging. If this error ever fires, the developer would look for `BaseTransform`/`BaseGate` classes that don't exist.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** Three priorities:
1. **Extract common work queue loop** into a single method called by all four public entry points (`process_row`, `process_existing_row`, `process_token`, `process_token_from_step`). This eliminates the quad-duplication risk.
2. **Unify aggregation flush handling** -- extract the shared logic between `_process_batch_aggregation_node` and `handle_timeout_flush` into shared helper methods (at minimum: the passthrough output handling, transform-mode output handling, and error handling). The current duplication has already caused at least one bug (P2-2026-02-01) to need fixing in two places.
3. **Standardize step indexing** -- document the step convention in a single place and consider making `_WorkItem.start_step` always use one convention (0-indexed or 1-indexed, not both depending on context). The current "happens to equal" coincidence between 1-indexed audit step and 0-indexed next-transform position is a trap for future maintainers.

The `_on_error` private attribute access (Warning item) should also be addressed by adding it to `TransformProtocol` or creating a proper accessor.

**Confidence:** HIGH -- Full read of the file and all key dependencies (TokenManager, CoalesceExecutor, TransformExecutor, RetryManager, protocols). Step indexing analysis was cross-referenced with orchestrator aggregation code.
