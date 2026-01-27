# ELSPETH Engine Subsystem Analysis

**Analysis Date:** 2026-01-27
**Analyst:** System Archaeologist Agent
**Files Analyzed:** orchestrator.py, processor.py, executors.py, coalesce_executor.py, tokens.py, retry.py, batch_adapter.py, expression_parser.py, triggers.py, artifacts.py, spans.py

---

## Executive Summary

The Engine subsystem is the execution core of ELSPETH - responsible for DAG traversal, plugin execution, audit recording, and row lifecycle management. While architecturally sound with good separation of concerns, several non-obvious issues would prevent this from being world-class:

1. **State synchronization gaps** between components that should be atomic
2. **Missing timeout/cancellation propagation** through the async boundary
3. **Unbounded memory growth** in several accumulating data structures
4. **Audit gaps** in edge cases around retry and coalesce interactions
5. **Testability issues** from hidden dependencies and tight coupling

---

## 1. orchestrator.py - Design Issues

### 1.1 Massive Constructor with 20+ Parameters

**Location:** orchestrator.py:55-180 (Orchestrator.__init__)

The Orchestrator class has grown to accept an enormous parameter list, creating coupling to every subsystem. This is a symptom of the class doing too much.

```python
def __init__(
    self,
    landscape: LandscapeDB,
    recorder: LandscapeRecorder,
    source: SourceProtocol,
    transforms: list[TransformPlugin],
    sinks: dict[SinkName, SinkProtocol],
    # ... 15+ more parameters
)
```

**Impact:** Testing requires building complex fixtures with many mock objects. Adding new features requires modifying the constructor signature.

**Recommendation:** Extract initialization into a builder or factory pattern. Group related parameters into configuration objects.

### 1.2 Run State Machine Not Explicit

**Location:** orchestrator.py (throughout)

The run lifecycle (PENDING -> RUNNING -> COMPLETING -> COMPLETED/FAILED) is managed through ad-hoc status updates rather than an explicit state machine. This leads to:

- Hard to verify all state transitions are valid
- Easy to miss edge cases (e.g., can we go from COMPLETING back to RUNNING?)
- Status updates scattered throughout the code

**Evidence:**
- Line 650: `_complete_run()` sets status
- Line 580: Exception handling sets status
- No single place defines valid transitions

### 1.3 Mixed Abstraction Levels in _process_rows()

**Location:** orchestrator.py:450-550

The `_process_rows()` method mixes:
- High-level iteration logic
- Low-level sink writing
- Checkpoint management
- Progress reporting

This makes the core processing loop harder to reason about and test.

---

## 2. processor.py - Functionality Gaps

### 2.1 MAX_WORK_QUEUE_ITERATIONS is a Magic Number

**Location:** processor.py:40

```python
MAX_WORK_QUEUE_ITERATIONS = 10_000
```

This limit is arbitrary and not configurable. For pipelines with many forks or deaggregation, 10,000 may be:
- Too low: Large batch deaggregation could exceed this legitimately
- Too high: An infinite loop bug runs 10,000 iterations before detection

**Recommendation:** Make configurable per-pipeline, or use a smarter detection (e.g., track unique tokens processed rather than iterations).

### 2.2 Coalesce Step Calculation is Fragile

**Location:** processor.py:845-856

The coalesce logic relies on `step_completed` matching `coalesce_at_step` exactly:

```python
if step_completed < coalesce_at_step:
    return False, None
```

This assumes steps are contiguous integers and that gate execution counts correctly. If step counting is off by one, coalesces silently fail to trigger.

**Evidence of Fragility:**
- Line 860: `step = start_step + step_offset + 1  # 1-indexed for audit`
- Multiple places calculate step differently

### 2.3 No Visibility into Held Coalesce Tokens

**Location:** processor.py:769-789

When tokens are held waiting for coalesce, the caller receives `(None, child_items)`. There's no way to query:
- How many tokens are waiting at each coalesce point
- How long they've been waiting
- Which row_ids are blocked

This makes debugging stuck pipelines difficult.

---

## 3. executors.py - Wiring Problems

### 3.1 TransformExecutor._get_batch_adapter Creates Hidden State

**Location:** executors.py:132-157

```python
def _get_batch_adapter(self, transform: TransformProtocol) -> "SharedBatchAdapter":
    if not hasattr(transform, "_executor_batch_adapter"):
        adapter = SharedBatchAdapter()
        transform._executor_batch_adapter = adapter  # Monkey-patching!
        transform.connect_output(output=adapter, max_pending=max_pending)
```

This stores state on the transform object itself using attribute assignment. Problems:
- Hidden coupling between executor and transform
- Transform objects become stateful in non-obvious ways
- No cleanup path if adapter needs to be reset

### 3.2 AggregationExecutor Has Parallel State Tracking

**Location:** executors.py:870-888

The AggregationExecutor maintains multiple parallel dictionaries that must stay synchronized:

```python
self._buffers: dict[NodeID, list[dict[str, Any]]] = {}
self._buffer_tokens: dict[NodeID, list[TokenInfo]] = {}
self._batch_ids: dict[NodeID, str | None] = {}
self._member_counts: dict[str, int] = {}  # Note: keyed by batch_id, not node_id!
self._trigger_evaluators: dict[NodeID, TriggerEvaluator] = {}
```

Line 1021-1027 has defensive validation for this:
```python
if len(buffered_rows) != len(buffered_tokens):
    raise RuntimeError("Internal state corruption...")
```

But this only catches one type of desync. If `_batch_ids` and `_buffers` get out of sync, no crash occurs.

### 3.3 SinkExecutor.write() Creates N Node States

**Location:** executors.py:1563-1572

For bulk writes, every token gets its own node_state:

```python
for token in tokens:
    state = self._recorder.begin_node_state(
        token_id=token.token_id,
        node_id=sink_node_id,
        ...
    )
    states.append((token, state))
```

For a sink write of 10,000 rows, this creates 10,000 database records before the write even starts. The comment at line 1577 acknowledges this:

```python
# Use first token's state_id since sink operations are typically bulk operations
ctx.state_id = states[0][1].state_id
```

This is O(N) database operations per sink write, which will be a performance bottleneck.

---

## 4. coalesce_executor.py - Error Handling Gaps

### 4.1 Late Arrival Detection Doesn't Handle All Cases

**Location:** coalesce_executor.py:172-199

When a token arrives after its siblings have already merged, it's marked as `late_arrival_after_merge`. But:

```python
self._completed_keys.add(key)  # Track completion to reject late arrivals
```

The `_completed_keys` set grows unboundedly. For long-running pipelines with many rows, this becomes a memory leak.

Line 595-599 attempts to fix this:
```python
# Clear completed keys to prevent unbounded memory growth
self._completed_keys.clear()
```

But this only happens in `flush_pending()`, not after each normal merge.

### 4.2 Timeout Check is Not Integrated with Processing

**Location:** coalesce_executor.py:371-440

`check_timeouts()` is a polling method that must be called externally. There's no evidence it's being called regularly:

```python
def check_timeouts(
    self,
    coalesce_name: str,
    step_in_pipeline: int,
) -> list[CoalesceOutcome]:
```

Searching processor.py shows no calls to `check_timeouts()`. This means coalesce timeouts may never fire during normal processing - only during `flush_pending()` at end-of-source.

### 4.3 Merge Strategy "select" Has Silent Fallback

**Location:** coalesce_executor.py:365-369

```python
if settings.select_branch in arrived:
    return arrived[settings.select_branch].row_data.copy()
# Fallback to first arrived if select branch not present
return next(iter(arrived.values())).row_data.copy()
```

If the selected branch didn't arrive (due to quorum policy), the code silently uses a different branch. This could produce unexpected results without any indication in the audit trail.

---

## 5. batch_adapter.py - Concurrency Issues

### 5.1 Race Between emit() and Waiter Timeout

**Location:** batch_adapter.py:106-125

The code correctly identifies the race condition in comments:

```python
# Race condition: emit() can execute between event.wait() timeout and
# this lock acquisition, storing a result that no one will retrieve
```

However, the fix (cleaning up `_results` in timeout path) means that if emit() stores a valid result during the race window, that result is silently discarded. This could lead to:
- Unnecessary retries
- Duplicate processing
- Audit trail showing timeout when result was actually available

### 5.2 No Mechanism to Cancel In-Flight Work

**Location:** batch_adapter.py (throughout)

When a timeout occurs and retry is about to happen, the original work continues in the worker pool. There's no cancellation mechanism:

```python
# After timeout:
# - Old worker still running (using resources)
# - Retry starts new work (doubling resource usage)
# - No way to signal old worker to abort
```

For LLM calls that take 30+ seconds, this could lead to significant resource waste and rate limit consumption.

---

## 6. retry.py - Missing Features

### 6.1 No Circuit Breaker

**Location:** retry.py (entire file)

The retry system has exponential backoff but no circuit breaker. If a downstream service is down:
- Each row will attempt max_attempts retries
- Each retry waits exponentially
- Total pipeline time = rows * max_attempts * max_delay

For 10,000 rows with max_attempts=3 and max_delay=60s:
- Worst case: 10,000 * 3 * 60s = 500+ hours

A circuit breaker would fail fast after detecting repeated failures.

### 6.2 on_retry Callback Only Called for Retryable Errors

**Location:** retry.py:168-172

```python
# Only call on_retry for retryable errors that will be retried
if is_retryable(e) and on_retry:
    on_retry(attempt, e)
```

The first attempt that succeeds doesn't call any callback. If you want to audit all attempts (including success), there's no hook.

---

## 7. expression_parser.py - Security Considerations

### 7.1 Subscription Attack Vector

**Location:** expression_parser.py:253-257

```python
def visit_Subscript(self, node: ast.Subscript) -> Any:
    value = self.visit(node.value)
    key = self.visit(node.slice)
    return value[key]  # Unconstrained subscript access
```

While `row` is the only allowed name, the subscript key can be any evaluated expression. This could be used to:
- Access nested objects in row data deeply
- Trigger `__getitem__` on custom objects if row data contains them

The validation at line 85-88 allows subscripts but doesn't constrain what's being subscripted.

### 7.2 Division by Zero Not Handled

**Location:** expression_parser.py:301-306

```python
def visit_BinOp(self, node: ast.BinOp) -> Any:
    left = self.visit(node.left)
    right = self.visit(node.right)
    op_func = _BINARY_OPS[type(node.op)]
    return op_func(left, right)  # No protection against division by zero
```

An expression like `row['count'] / row['divisor']` where divisor=0 will crash the gate evaluation. Per CLAUDE.md, this is row data causing operation failure, which should return an error result, not crash.

---

## 8. triggers.py - Testability Issues

### 8.1 Time Dependency Makes Testing Brittle

**Location:** triggers.py:68-72, 93-94

```python
@property
def batch_age_seconds(self) -> float:
    if self._first_accept_time is None:
        return 0.0
    return time.monotonic() - self._first_accept_time
```

The evaluator uses `time.monotonic()` directly, making timeout tests require either:
- Real delays (slow tests)
- Monkey-patching time module
- Injected clock (not currently supported)

### 8.2 Condition Parser Created at Construction

**Location:** triggers.py:58-60

```python
if config.condition is not None:
    self._condition_parser = ExpressionParser(config.condition)
```

If the condition expression is invalid, it fails at TriggerEvaluator construction time, not at configuration validation time. This means invalid trigger conditions won't be detected until the pipeline starts.

---

## 9. spans.py - Missing Observability

### 9.1 No Error State Recording

**Location:** spans.py (throughout)

The span factory creates spans but doesn't record error states:

```python
@contextmanager
def transform_span(self, transform_name: str, ...) -> Iterator["Span | NoOpSpan"]:
    with self._tracer.start_as_current_span(...) as span:
        span.set_attribute("plugin.name", transform_name)
        yield span  # No exception handling!
```

If the code within the span raises an exception, the span doesn't get `span.record_exception(e)` or `span.set_status(ERROR)`. The caller is responsible for this, but most call sites don't do it.

### 9.2 No Correlation IDs for Cross-Span Linking

**Location:** spans.py:116-137

Row span doesn't capture parent run_id or establish correlation:

```python
with self._tracer.start_as_current_span(f"row:{row_id}") as span:
    span.set_attribute("row.id", row_id)
    span.set_attribute("token.id", token_id)
    # Missing: parent_run_id, correlation_id for distributed tracing
```

For pipelines that call external services, there's no way to correlate ELSPETH spans with those service spans.

---

## 10. tokens.py - Data Integrity Concerns

### 10.1 Deep Copy May Not Handle All Types

**Location:** tokens.py:151-163

```python
return [
    TokenInfo(
        row_id=parent_token.row_id,
        token_id=child.token_id,
        row_data=copy.deepcopy(data),  # Deep copy
        ...
    )
    for child in children
]
```

`copy.deepcopy()` will fail or behave unexpectedly for:
- Row data containing file handles
- Row data containing database connections
- Row data containing numpy arrays (works but expensive)
- Row data containing pandas DataFrames (works but very expensive)

No validation or warning about non-serializable row data.

### 10.2 No Validation That Parents Share Same row_id in coalesce_tokens

**Location:** tokens.py:184-185

```python
# Use first parent's row_id (they should all be the same)
row_id = parents[0].row_id
```

The comment says "they should all be the same" but there's no assertion. If called with mismatched row_ids (a bug), the coalesced token has incorrect lineage.

---

## 11. Cross-Cutting Concerns

### 11.1 No Graceful Shutdown

**Evidence:** Searching all files for "shutdown", "stop", "cancel", "interrupt" shows no graceful shutdown mechanism.

If the process is interrupted:
- In-flight batch transforms continue running
- Partial checkpoint states may exist
- Coalesced tokens waiting in memory are lost
- No flush of pending aggregations

### 11.2 Inconsistent Error Representation

Different components represent errors differently:

| Component | Error Format |
|-----------|--------------|
| TransformExecutor | `ExecutionError = {"exception": str, "type": str}` |
| GateExecutor | Same `ExecutionError` |
| CoalesceExecutor | `{"failure_reason": str}` |
| AggregationExecutor | `ExecutionError` |
| MaxRetriesExceeded | Custom exception with `.attempts` and `.last_error` |

No common error type means error handling logic is duplicated and inconsistent.

### 11.3 Memory Accumulation Points

Several structures grow without bounds:

1. `CoalesceExecutor._completed_keys` - cleared only at flush_pending()
2. `AggregationExecutor._buffers` - cleared only at flush
3. `SharedBatchAdapter._results` - cleared on successful wait, but race conditions can leak

---

## Confidence Assessment

**Confidence:** High

**Evidence Trail:**
- Read 100% of all 11 engine files (no file exceeds 2000 lines)
- Cross-referenced patterns between components
- Validated observations against CLAUDE.md requirements
- Verified each claim with specific file:line references

**Information Gaps:**
- Did not analyze integration tests to see which edge cases are covered
- Did not trace full call path from CLI entry to understand configuration flow
- Did not analyze the LandscapeRecorder implementation to verify audit assumptions

---

## Risk Assessment

| Issue | Severity | Likelihood | Impact |
|-------|----------|------------|--------|
| Coalesce timeout never fires | High | Medium | Data stuck in pipeline |
| Memory leak in _completed_keys | Medium | High | OOM in long runs |
| No graceful shutdown | High | Medium | Data loss on interrupt |
| Circuit breaker missing | Medium | Medium | Extended outages |
| SinkExecutor O(N) states | Medium | High | Performance degradation |
| Race condition result discard | Low | Low | Unnecessary retries |

---

## Recommendations Priority

1. **P0 (Critical):** Add coalesce timeout polling to processor main loop
2. **P0 (Critical):** Implement graceful shutdown with pending flush
3. **P1 (High):** Bound _completed_keys with LRU eviction
4. **P1 (High):** Add circuit breaker to RetryManager
5. **P2 (Medium):** Extract state machine for run lifecycle
6. **P2 (Medium):** Optimize SinkExecutor for bulk node_state creation
7. **P3 (Low):** Inject clock dependency for testability
8. **P3 (Low):** Standardize error representation
