# Architecture Analysis: plugins/batching and plugins/pooling

**Date:** 2026-02-22
**Branch:** RC3.3-architectural-remediation
**Scope:** 8 files across two subsystems plus cross-cutting engine references

---

## File-by-File Analysis

### plugins/batching/mixin.py

**Purpose:** Provides `BatchTransformMixin`, a mixin class that adds within-row concurrent sub-task processing to any transform while guaranteeing FIFO output ordering to the orchestrator. Conceals all threading from the orchestrator: the orchestrator calls `accept()` and blocks only on backpressure; results flow out of an `OutputPort` in submission order.

**Key Classes/Functions:**
- `BatchTransformMixin` — the mixin. Declares abstract `accept()` and `connect_output()` that subclasses must implement. Core methods: `init_batch_processing()`, `accept_row()`, `_process_and_complete()`, `_release_loop()`, `flush_batch_processing()`, `evict_submission()`, `shutdown_batch_processing()`.
- `_release_loop()` — runs in a dedicated non-daemon thread. Blocks on `RowReorderBuffer.wait_for_next_release()` and calls `OutputPort.emit()` in strict FIFO order.
- `evict_submission()` — called by the executor on timeout. Removes the buffer entry for a timed-out attempt so that the retry can get a new sequence number and proceed without being blocked by the FIFO ordering of a stale entry.

**Dependencies:**
- `plugins/batching/ports.py` — `OutputPort` protocol
- `plugins/batching/row_reorder_buffer.py` — `RowReorderBuffer`, `RowTicket`, `ShutdownError`
- `contracts` — `TransformResult`, `ExceptionResult`, `TokenInfo`, `PluginContext`
- `concurrent.futures.ThreadPoolExecutor` (stdlib)
- `threading` (stdlib)

**Concurrency Model:** Pure threading. Three thread roles:
1. Orchestrator thread calls `accept_row()` — blocks only on backpressure (buffer full).
2. Worker threads (ThreadPoolExecutor) call `_process_and_complete()`.
3. Release thread calls `_release_loop()` — the sole consumer of the buffer, emits in FIFO order.

**Concerns:**
1. `flush_batch_processing()` uses a polling loop (`threading.Event().wait(0.1)`) instead of a condition variable to detect buffer drain. This creates a new `threading.Event` object on every 100ms poll iteration — functionally harmless but semantically odd. A `Condition` or the buffer's own `pending_count` via a condition-wait would be cleaner.
2. The release loop has a subtle dual-exception path in the outer `except Exception` handler (lines 320–347). If `token is None` (exception occurred before unpacking `entry.result`), it re-raises. If `token` was set, it tries to emit an `ExceptionResult`. If that secondary emit also fails, it logs critical and continues. This is the correct CLAUDE.md behavior (crash on invariant violation, propagate on row error), but the three-layer nested exception handling is complex and fragile to future changes.
3. Plugin-bug exceptions from worker threads are wrapped in `ExceptionResult` and propagated via the buffer and port to the waiter. This is correct but means an unhandled exception from a processor function takes a multi-hop path (worker thread → buffer → release thread → OutputPort.emit → SharedBatchAdapter → RowWaiter.wait → orchestrator thread) before crashing. A developer unfamiliar with the architecture could accidentally swallow it at any hop.
4. `_batch_submissions` dict grows unbounded if `evict_submission` is never called for a submission whose `state_id` is `None` (state_id is optional; the tracking is skipped in `accept_row()` but the eviction lookup would miss it). This is a minor memory leak risk in abnormal flows.

---

### plugins/batching/ports.py

**Purpose:** Defines the `OutputPort` protocol and two concrete test implementations (`NullOutputPort`, `CollectorOutputPort`). The protocol decouples batch transform emitters from their downstream consumers — a transform emits to an `OutputPort` without knowing whether the downstream is a sink, another transform, or a test collector.

**Key Classes/Functions:**
- `OutputPort` — `@runtime_checkable` Protocol with a single method: `emit(token, result, state_id)`.
- `NullOutputPort` — discards all results (for testing or deliberate drops).
- `CollectorOutputPort` — accumulates `(token, result, state_id)` tuples into a list (for test assertions).

**Dependencies:** `contracts` — `TransformResult`, `ExceptionResult`, `TokenInfo` (TYPE_CHECKING only). No runtime imports beyond stdlib.

**Concurrency Model:** The protocol itself is single-method and stateless. `CollectorOutputPort` is not thread-safe (the `results` list is mutated without a lock). In production the `SharedBatchAdapter` (in `engine/batch_adapter.py`) is the real `OutputPort` implementation and is thread-safe.

**Concerns:**
1. `CollectorOutputPort` is not thread-safe. If used as an output port in a concurrent test, the `results.append()` could race. The test-only implementations should either document thread-safety requirements or add a lock. This is low severity since these are only used in controlled test scenarios, but a note in the docstring would prevent future misuse.
2. `NullOutputPort` silently discards results. Callers in production code should ensure this is only used intentionally (currently it is — only in tests).

---

### plugins/batching/row_reorder_buffer.py

**Purpose:** Implements `RowReorderBuffer[T]`, a row-level reorder buffer. Rows are submitted in order (each gets a monotonically increasing sequence number), completed out of order by worker threads, and released in strict submission order by the release thread. Provides backpressure by blocking `submit()` when `max_pending` entries are in flight.

**Key Classes/Functions:**
- `ShutdownError` — sentinel exception raised on shutdown.
- `RowTicket` — frozen dataclass returned by `submit()`, carries sequence number, row_id, and submission timestamp.
- `RowBufferEntry[T]` — emitted by `wait_for_next_release()`, carries result + timing metadata.
- `_PendingEntry[T]` — internal mutable entry tracking in-flight state.
- `RowReorderBuffer[T]` — main class. Uses a single `Lock` with two `Condition` variables (one for backpressure, one for release readiness).
- `evict()` — removes an entry and advances `_next_release_seq` past any gaps. Critical for retry correctness.

**Dependencies:** `dataclasses`, `threading`, `time` (all stdlib). No elspeth imports.

**Concurrency Model:** Pure threading. Single `Lock` with two `Condition` instances sharing that lock. Submit blocks on `_submit_condition`. Release blocks on `_release_condition`. Worker threads call `complete()` and notify the release condition. Shutdown wakes all waiters via `notify_all()`.

**Concerns:**
1. The `evict()` advancement logic (lines 326–328) advances `_next_release_seq` by a `while` loop that skips over any gap in `_pending`. This is correct but means a sequence of evictions could leave `_next_release_seq` far ahead of the earliest actual pending entry. If the evicted sequence was not `_next_release_seq` but a later one, the loop does not advance at all (because `_next_release_seq` is still in `_pending`). This is correct — only need to advance when the head is evicted — but the loop condition is subtle and not commented inline.
2. `wait_for_next_release()` checks `is_complete` then accesses `entry.result` and `entry.completed_at` without the lock held between the check and the access. The result and completed_at are set under the lock in `complete()`. However the check and the field access in `wait_for_next_release()` happen inside the same `with self._release_condition:` block (which holds `self._lock`), so this is actually safe. This is non-obvious and worth a comment.
3. Metrics (`_total_submitted`, `_total_released`, `_max_observed_pending`, `_total_wait_time_ms`) are updated inside the same lock that guards the buffer, which is correct and avoids a separate stats lock. However `get_metrics()` also acquires `_lock` (now spelled as `self._lock` in `get_metrics`). The method uses `self._lock` directly on line 362, while `submit()` uses `self._submit_condition` (which is `Condition(self._lock)`). Since `Condition(self._lock)` acquires `self._lock` when entered, and `get_metrics()` uses `with self._lock:`, these are equivalent and correct. Again non-obvious.
4. There are no metrics for evictions. Given eviction is a key retry-correctness mechanism, an `_total_evicted` counter would be valuable for audit/debugging.

---

### plugins/pooling/config.py

**Purpose:** Defines `PoolConfig`, the Pydantic validation model for pool configuration. Converts to `ThrottleConfig` via `to_throttle_config()` for runtime use.

**Key Classes/Functions:**
- `PoolConfig` — Pydantic `BaseModel` with `extra="forbid"`. Fields: `pool_size`, `min_dispatch_delay_ms`, `max_dispatch_delay_ms`, `backoff_multiplier`, `recovery_step_ms`, `max_capacity_retry_seconds`. Has a `@model_validator(mode="after")` that checks delay ordering and ensures AIMD backoff is viable (prevents infinite-speed retry loops at zero delay).
- `to_throttle_config()` — converts to `ThrottleConfig` (frozen dataclass) for runtime.

**Dependencies:** `pydantic`, `plugins/pooling/throttle.py` (for `ThrottleConfig`).

**Concurrency Model:** None — this is a configuration dataclass instantiated at setup time and then read-only.

**Concerns:**
1. The `to_throttle_config()` method does not map `max_capacity_retry_seconds` to `ThrottleConfig`. This is correct because `ThrottleConfig` is the AIMD throttle state, which does not need the retry timeout (the timeout is used in `PooledExecutor._execute_single()`). However this asymmetry is not documented. A developer adding fields to `PoolConfig` could omit them from both `ThrottleConfig` and `PooledExecutor`, producing the same silent field-orphaning bug that the config contract system exists to prevent. This configuration pair is not covered by the `scripts.check_contracts` AST checker.
2. The model_validator checks `min_dispatch_delay_ms == 0 and recovery_step_ms == 0` together, but `recovery_step_ms` alone at 0 with `min_dispatch_delay_ms > 0` is also suspicious (AIMD would never recover). Not necessarily a bug since the floor prevents negative delays, but worth considering.

---

### plugins/pooling/errors.py

**Purpose:** Defines HTTP capacity error classification: the `CAPACITY_ERROR_CODES` frozenset (429, 503, 529), the `is_capacity_error()` predicate function, and the `CapacityError` exception class.

**Key Classes/Functions:**
- `CAPACITY_ERROR_CODES: frozenset[int]` — {429, 503, 529}.
- `is_capacity_error(status_code)` — predicate.
- `CapacityError` — exception carrying `status_code` and hardcoded `retryable=True`.

**Dependencies:** None (stdlib only).

**Concurrency Model:** None.

**Concerns:**
1. `CapacityError.__init__` hardcodes `self.retryable = True`. This is an instance attribute on an exception, not a class-level constant. It has no enforcement mechanism — anything could set `retryable = False` on an instance. Given that `PooledExecutor._execute_single()` checks `isinstance(e, LLMClientError) and not e.retryable` but NOT `CapacityError.retryable`, the field is currently unused for `CapacityError` specifically. This is a latent inconsistency: `CapacityError.retryable` exists but is never checked; `LLMClientError.retryable` is checked. The field on `CapacityError` is dead code that could mislead maintainers.
2. `is_capacity_error()` is defined but not used in `PooledExecutor` (which catches `CapacityError` directly by type). The function exists as a predicate utility for callers that have a raw status code rather than an exception. Its usage scope is not documented.

---

### plugins/pooling/executor.py

**Purpose:** `PooledExecutor` manages parallel API calls within a single row (the query-level concurrency layer). Dispatches rows from `execute_batch()` to a `ThreadPoolExecutor`, controls concurrency with a `Semaphore`, paces dispatches with `_wait_for_dispatch_gate()`, applies AIMD throttle on capacity errors, reorders results via `ReorderBuffer`, and returns all results in submission order.

**Key Classes/Functions:**
- `RowContext` — dataclass carrying `row: dict[str, Any]`, `state_id: str`, `row_index: int`.
- `PooledExecutor` — main class.
  - `execute_batch()` — serialized (via `_batch_lock`) entry point. Submits all contexts to thread pool, waits for futures, drains buffer, returns `list[BufferEntry[TransformResult]]` in submission order.
  - `_execute_single()` — worker function. Acquires semaphore, calls `_wait_for_dispatch_gate()`, calls `process_fn`, handles `CapacityError`/`LLMClientError` with AIMD retry loop, releases semaphore.
  - `_wait_for_dispatch_gate()` — enforces `min_dispatch_delay_ms` between all dispatches globally, using a shared `_last_dispatch_time` and `_dispatch_gate_lock`.

**Dependencies:**
- `contracts` — `TransformResult`, `TransformErrorReason`
- `plugins/clients/llm` — `LLMClientError`
- `plugins/pooling/config.py` — `PoolConfig`
- `plugins/pooling/errors.py` — `CapacityError`
- `plugins/pooling/reorder_buffer.py` — `BufferEntry`, `ReorderBuffer`
- `plugins/pooling/throttle.py` — `AIMDThrottle`
- `concurrent.futures` (stdlib)

**Concurrency Model:** ThreadPoolExecutor-based. Key design decisions:
- Semaphore is acquired INSIDE `_execute_single()` (the worker), not in `execute_batch()`. This prevents deadlock when capacity errors cause workers to release-then-reacquire the semaphore: if the main thread held permits for all queued tasks, workers blocked on re-acquire would create a deadlock.
- `_batch_lock` serializes `execute_batch()` calls because `ReorderBuffer` uses a sequential submit index that would be interleaved across concurrent batches.
- AIMD retry backoff sleeps happen OUTSIDE the semaphore hold to allow other workers to make progress.
- The dispatch gate (`_wait_for_dispatch_gate`) uses `min_dispatch_delay_ms` only (not the AIMD delay), deliberately avoiding double-penalization documented in the method comment.

**Concerns:**
1. The `_execute_single()` shutdown path on the retry loop (lines 479–487) checks `self._shutdown_event.is_set()` but only inside the `except (CapacityError, LLMClientError)` block. If the shutdown event is set during a successful call path (between the `try` and `return`), `_shutdown_event` is not checked. This means a shutdown that arrives during a successful API call does not terminate the worker early. This is probably acceptable (you want results to complete), but it is an inconsistency.
2. The shutdown handling in `execute_batch()` (lines 277–297) for thread pool `RuntimeError` has a non-trivial index manipulation: `contexts[contexts.index(ctx) + 1:]`. This uses `list.index()` which is O(n) and returns the first match — if `ctx` appears multiple times in `contexts` (duplicate row context), it would return the wrong index. This is unlikely in practice but is a latent bug.
3. `RowContext.row` is typed as `dict[str, Any]`. The pooling layer works with raw dicts (not `PipelineRow`). This crosses the Tier 2 data model — by the time rows reach transforms, they should be `PipelineRow` objects. The conversion to `dict` for the pooling layer is happening somewhere upstream, but the type annotation here does not enforce that this dict came from a validated `PipelineRow.to_dict()`. This is a minor contract clarity issue.
4. The `_batch_lock` prevents concurrent batch execution, but a single `PooledExecutor` instance is constructed once and shared across all rows for a given transform. If `execute_batch()` is ever called from two threads simultaneously (not the current usage pattern, but possible if the architecture changes), the lock ensures correctness but also serializes all batch processing through one executor instance, eliminating parallelism across rows at the pooling level.
5. Statistics reset (`_reset_batch_stats()`) resets per-batch counters at the start of each batch. The AIMD throttle's `current_delay_ms` is NOT reset (only the stat counters). This is correct — the delay should persist across batches to maintain adaptive rate limiting state. But `reset_stats()` in `AIMDThrottle` does reset `_peak_delay_ms` to `current_delay_ms`, which means the "peak" reported for a batch is only the peak within that batch, not the historical peak. This could confuse audit consumers comparing throttle peaks across runs.

---

### plugins/pooling/reorder_buffer.py

**Purpose:** `ReorderBuffer[T]` — a polling-based reorder buffer used by `PooledExecutor`. Items are submitted (get a sequential index), completed out of order by workers, and emitted in submission order by `get_ready_results()` (a polling call, not blocking). Captures timing metadata for audit trail.

**Key Classes/Functions:**
- `_Sentinel` / `_UNFILLED` — sentinel class to distinguish "not yet completed" from a legitimate `None` result.
- `BufferEntry[T]` — emitted dataclass with submit/complete indices, result, and timestamps.
- `_InternalEntry[T]` — internal mutable entry.
- `ReorderBuffer[T]` — main class. Methods: `submit()`, `complete()`, `get_ready_results()`.

**Dependencies:** `dataclasses`, `threading`, `time` (stdlib). No elspeth imports.

**Concurrency Model:** Pure threading. Single `Lock` guards all state. All three methods (`submit`, `complete`, `get_ready_results`) acquire the lock. `get_ready_results()` is a polling method — it returns immediately with whatever is ready.

**Concerns:**
1. `_InternalEntry.result` uses `Any` type annotation with `_UNFILLED` as the default sentinel. The sentinel class is correctly designed (dedicated class, `__slots__`, cannot be confused with valid results). However the `result: Any = field(default=_UNFILLED)` means mypy cannot track that `result` is `T` at emission time — it requires the manual `entry.result` is set check in `get_ready_results()`. This is an acceptable pattern but is the fundamental weakness of sentinel-based typing.
2. `get_ready_results()` returns all consecutively-ready entries in one call (not just the next one). This is correct and efficient for the `PooledExecutor` polling pattern. However unlike `RowReorderBuffer.wait_for_next_release()`, there is no blocking — callers must poll. The `executor.py` final drain loop (lines 316–319) correctly handles this with a `while pending_count > 0` loop.
3. `complete_timestamp is None` and `complete_index is None` are guarded with crash-on-invariant-violation (lines 165–172), consistent with CLAUDE.md Tier 1 behavior. This is correct.

---

### plugins/pooling/throttle.py

**Purpose:** `AIMDThrottle` — a thread-safe AIMD (Additive Increase, Multiplicative Decrease) state machine for API rate limiting. On capacity error: multiply current delay by `backoff_multiplier`. On success: subtract `recovery_step_ms`, floored at `min_dispatch_delay_ms`. Maintains statistics for audit trail.

**Key Classes/Functions:**
- `ThrottleConfig` — frozen dataclass (runtime config, not Pydantic, because it is derived from validated `PoolConfig`).
- `AIMDThrottle` — main class. Methods: `on_capacity_error()`, `on_success()`, `record_throttle_wait()`, `get_stats()`, `reset_stats()`.

**Dependencies:** `dataclasses`, `threading` (stdlib). No elspeth imports.

**Concurrency Model:** Pure threading. Single `Lock` guards all state. All mutating methods and stats methods acquire the lock.

**Concerns:**
1. `on_success()` can drive `_current_delay_ms` negative if `recovery_step_ms > current_delay_ms`. The floor check `if self._current_delay_ms < self._config.min_dispatch_delay_ms` then clamps it. If `min_dispatch_delay_ms == 0`, the delay could briefly be negative before the floor is applied in the same lock hold. This is not a bug (the floor check is within the same lock acquisition), but the subtraction-then-floor pattern is less clear than floor(current - step, min).
2. `reset_stats()` sets `_peak_delay_ms = self._current_delay_ms`, not 0. This means after a reset, the "peak" starts at wherever the delay currently is. This is intentional (to track peak within the batch period) but means `get_stats()["peak_delay_ms"]` can be lower than the throttle's historical peak, which could be misleading in audit records.
3. `AIMDThrottle` is instantiated once per `PooledExecutor` and shared across all batches processed by that executor. The delay state persists across batch resets. This is the intended design (adaptive rate limiting should "remember" the API's health), but it is not documented. A developer might expect `_reset_batch_stats()` to also reset the delay.

---

## Overall Architecture Analysis

### 1. Batching Architecture

The batching subsystem implements **within-row concurrent sub-task processing** (used by LLM transforms that make multiple API calls per row or process rows in a streaming fashion). The architecture is:

```
Orchestrator thread
  └─ TransformExecutor.execute_transform()
       ├─ Detects isinstance(transform, BatchTransformMixin)
       ├─ Gets/creates SharedBatchAdapter (engine/batch_adapter.py)
       ├─ Calls adapter.register(token_id, state_id) → RowWaiter
       ├─ Calls transform.accept(row, ctx)
       │    └─ accept_row() → buffer.submit() [blocks on backpressure]
       │         └─ executor.submit(_process_and_complete)
       │              └─ Worker thread: calls processor(), calls buffer.complete()
       └─ waiter.wait(timeout) [blocks until result delivered]
            └─ SharedBatchAdapter.emit() → routes by (token_id, state_id) → signals event

Release thread (per transform):
  └─ _release_loop()
       └─ buffer.wait_for_next_release() [FIFO]
            └─ OutputPort.emit() → SharedBatchAdapter.emit()
```

The mixin pattern is the correct abstraction: the transform implements the batch pattern once, and the orchestrator treats mixin transforms and standard transforms uniformly after the `isinstance` check in `TransformExecutor`. The concurrency (within-row) is completely hidden inside the plugin.

The FIFO guarantee is provided at two levels:
- `RowReorderBuffer` ensures results are emitted in submission order.
- `SharedBatchAdapter` routes to the correct waiter by `(token_id, state_id)`, preventing stale results from being delivered to retried attempts.

### 2. Pooling Architecture

The pooling subsystem implements **within-row query-level concurrency** — specifically for transforms that make N API calls per row (e.g., multi-query LLM transforms). Architecture:

```
Transform._process_row(row, ctx)
  └─ PooledExecutor.execute_batch(contexts, process_fn)
       ├─ [_batch_lock held — serializes concurrent execute_batch calls]
       ├─ For each context: ReorderBuffer.submit() → ThreadPoolExecutor.submit(_execute_single)
       └─ _execute_single(buffer_idx, row, state_id, process_fn):
            ├─ Semaphore.acquire() [limits concurrency]
            ├─ _wait_for_dispatch_gate() [global pacing]
            ├─ process_fn(row, state_id)
            │    ├─ Success: throttle.on_success(), return result
            │    └─ CapacityError/LLMClientError:
            │         ├─ Semaphore.release() [free slot for others]
            │         ├─ throttle.on_capacity_error()
            │         ├─ time.sleep(current_delay_ms)
            │         └─ Semaphore.acquire(), retry
            └─ BufferEntry with timing metadata → collected by execute_batch
```

The pooling layer is used by multi-query LLM transforms and is completely synchronous from the caller's perspective — `execute_batch()` blocks until all N queries complete and returns them in submission order.

### 3. Reorder Buffer Pattern — Two Implementations

There are two reorder buffer implementations with fundamentally different access patterns:

| Aspect | `plugins/pooling/reorder_buffer.py` | `plugins/batching/row_reorder_buffer.py` |
|--------|-------------------------------------|------------------------------------------|
| Scope | Query-level (within a single row) | Row-level (across rows in a pipeline) |
| Consumer | `PooledExecutor` (single-threaded polling) | Release thread (blocking wait) |
| API | `get_ready_results()` — polling, returns batch | `wait_for_next_release()` — blocking, one at a time |
| Backpressure | None (caller controls submission rate) | `submit()` blocks when `max_pending` reached |
| Eviction | None | `evict()` for retry timeout handling |
| Shutdown | No explicit shutdown | `shutdown()` raises `ShutdownError` |
| Timing metadata | `submit_index`, `complete_index`, timestamps | `submitted_at`, `completed_at`, `buffer_wait_ms` |

The two implementations exist for good reasons: the polling pattern fits `PooledExecutor`'s synchronous batch processing, while the blocking wait pattern fits the long-lived release thread in `BatchTransformMixin`. Merging them would require a single buffer to support both polling and blocking access, complicating the design.

However the duplication carries real maintenance risk: bug fixes and timing improvements need to be applied in two places, and subtle differences in the eviction/shutdown semantics are easy to get wrong.

**Recommendation:** Extract a minimal shared base or a common `_ordered_buffer_core` that handles the sequence tracking and entry management, letting the two implementations specialize only their consumer access pattern. Alternatively, document the intentional divergence explicitly in both files with a cross-reference.

### 4. Throttle Mechanism

`AIMDThrottle` implements TCP-style congestion control adapted for API rate limiting:

- **State:** `_current_delay_ms` (float), bounded by `[min_dispatch_delay_ms, max_dispatch_delay_ms]`.
- **On capacity error (429/503/529):** Multiplicative increase (`current * backoff_multiplier`), capped at max. If current is 0, bootstraps to `max(recovery_step_ms, min_dispatch_delay_ms)`.
- **On success:** Additive decrease (`current - recovery_step_ms`), floored at min.
- **Dispatch gate:** Separate from AIMD — enforces a fixed minimum inter-dispatch delay globally, preventing burst hammering when many workers are simultaneously ready.

The separation of AIMD state (per-retry backoff) from the dispatch gate (global pacing) is architecturally sound. The rationale is documented in `_wait_for_dispatch_gate()`: feeding AIMD into the gate would double-penalize workers and serialize retries through a single bottleneck.

**Concern:** The throttle is shared across all `execute_batch()` calls for a given `PooledExecutor` instance, and its delay state persists across batch resets. This is correct adaptive behavior, but the interaction with `reset_stats()` (which does NOT reset delay) is a footgun — a caller that calls `reset_stats()` expecting a clean throttle state will be surprised.

### 5. Error Propagation

Error propagation paths differ between the two subsystems:

**Batching (row-level):**
- Row processing errors (expected failures): processor returns `TransformResult.error()`. Worker wraps it in the buffer tuple, release thread emits it via `OutputPort`, `SharedBatchAdapter.emit()` delivers it to `RowWaiter.wait()`, which returns it as a normal `TransformResult`.
- Plugin bugs (unexpected exceptions): worker catches the exception, wraps it in `ExceptionResult(exception, traceback)`, completes the buffer with it. Release thread emits it via `OutputPort`. `RowWaiter.wait()` detects `isinstance(entry.result, ExceptionResult)` and re-raises the original exception in the orchestrator thread. This correctly makes plugin bugs crash the pipeline.
- Timeout: `RowWaiter.wait()` raises `TimeoutError`. The executor calls `evict_submission()` to free the buffer entry. The original worker may still complete (late), but `contextlib.suppress(KeyError)` in `_process_and_complete` discards the late result.

**Pooling (query-level):**
- Capacity errors: caught in `_execute_single`, trigger AIMD throttle, retry loop. After `max_capacity_retry_seconds`, converted to `TransformResult.error(reason="retry_timeout")`.
- Permanent errors (non-retryable `LLMClientError`): immediately converted to `TransformResult.error(reason="permanent_error")`.
- Unexpected exceptions: NOT caught in `_execute_single` (only `CapacityError` and `LLMClientError` are caught). Any other exception propagates through the `Future` and is re-raised in `execute_batch()` at `future.result()`. This correctly crashes the transform and propagates up to the orchestrator.

The distinction between the two error propagation models is important: pooling errors are row-data-level failures (API is overloaded — a recoverable condition) and are converted to `TransformResult.error`. Batching propagates both row-level errors and plugin bugs, using `ExceptionResult` to distinguish them.

### 6. Cross-Cutting Dependencies

The two layers form a two-level concurrency stack:

```
BatchTransformMixin (row-level, pipeline-wide concurrency)
  └─ PooledExecutor (query-level, within-row concurrency)
       └─ AIMDThrottle (throttle state)
       └─ ReorderBuffer (query ordering)
  └─ RowReorderBuffer (row ordering)
  └─ OutputPort → SharedBatchAdapter (engine)
```

Concrete LLM transforms that use both layers:
- `AzureLLMTransform` (`plugins/llm/azure.py`) — `BatchTransformMixin` only (single API call per row, but multiple rows in flight)
- `BaseMultiQueryTransform` (`plugins/llm/base_multi_query.py`) — `BatchTransformMixin` + `PooledExecutor` (multiple API calls per row AND multiple rows in flight)
- `OpenRouterLLMTransform` (`plugins/llm/openrouter.py`) — `BatchTransformMixin` only
- `OpenRouterBatchTransform` (`plugins/llm/openrouter_batch.py`) — `PooledExecutor` (batch API, different pattern)

The engine-level coupling:
- `TransformExecutor` (`engine/executors/transform.py`) detects `BatchTransformMixin` via `isinstance`, owns the `SharedBatchAdapter` dict, and calls `connect_output()` on first use. This is the only engine file that needs to know about the batching subsystem.
- `SharedBatchAdapter` (`engine/batch_adapter.py`) implements `OutputPort` and is the bridge between the batching subsystem and the engine.

---

## Concerns and Recommendations

### Concern 1: connect_output() Two-Phase Init is a Footgun (Medium Severity)

`BatchTransformMixin` has two-phase initialization: `__init__` and then `connect_output()`. Calling `accept()` before `connect_output()` raises a `RuntimeError` ("connect_output() must be called before accept()"). This pattern is enforced by the concrete transforms with a manual check, not by the type system. Nothing prevents a subclass from forgetting to guard.

**Recommendation:** Enforce initialization order structurally. Consider making `init_batch_processing()` a required call in `connect_output()` (the mixin owns both), so the two-phase init is encapsulated and not left to subclasses to implement correctly.

### Concern 2: _batch_submissions Tracking Gap (Low Severity)

In `accept_row()`, the `state_id` tracking for eviction is skipped when `state_id is None` (`if state_id is not None`). This means if `evict_submission()` is called for a row submitted with `state_id=None`, it won't find the ticket and will return `False` without evicting. The buffer entry remains and will block FIFO ordering until the worker completes or the entire buffer shuts down.

In current usage `state_id` is always set by `begin_node_state()` before `accept()` is called, so this is not reachable in production. But it is a silent correctness dependency on external ordering that is not enforced or documented at the mixin level.

**Recommendation:** Assert `state_id is not None` in `accept_row()`, or remove the conditional tracking and always track by always requiring `state_id`.

### Concern 3: Duplicate ReorderBuffer Implementations (Medium Severity)

Two reorder buffers with overlapping logic but different access patterns. See Section 3 above.

**Recommendation:** Add cross-reference comments in both files explicitly stating why two implementations exist. If any bug is found in sequence tracking logic, both must be patched. A shared internal helper for sequence/entry tracking would eliminate this risk.

### Concern 4: PooledExecutor._batch_lock Kills Row-Level Parallelism for Multi-Query Transforms (Medium Severity)

For multi-query transforms that use both `BatchTransformMixin` (row-level concurrency) and `PooledExecutor` (query-level concurrency), the `_batch_lock` in `PooledExecutor` means that while row N's queries are executing, row N+1 cannot start its query batch. The row-level concurrency (`BatchTransformMixin`) puts rows in flight simultaneously, but they each call into `execute_batch()` and serialize at `_batch_lock`.

The lock exists to prevent `ReorderBuffer` index interleaving across concurrent batches. If `ReorderBuffer` were per-batch (created fresh in `execute_batch()`) rather than shared on the executor, the lock would not be needed.

**Recommendation:** Move `ReorderBuffer` instantiation inside `_execute_batch_locked()` (create a fresh buffer per batch). This eliminates the shared state requiring serialization and allows truly parallel row processing when both concurrency layers are active. The lock can then be removed.

### Concern 5: CapacityError.retryable is Dead Code (Low Severity)

`CapacityError` has a `retryable` instance attribute set to `True` in `__init__`, but `PooledExecutor._execute_single()` never checks it (it only checks `LLMClientError.retryable`). The attribute is unused dead code that could mislead maintainers.

**Recommendation:** Remove `self.retryable = True` from `CapacityError.__init__`. If future code needs to make some capacity errors non-retryable, that is the time to add it.

### Concern 6: flush_batch_processing() Polling Loop (Low Severity)

`flush_batch_processing()` spawns a thread and polls `buffer.pending_count` every 100ms. This creates unnecessary thread churn and CPU usage during shutdown.

**Recommendation:** Add a `wait_until_empty(timeout)` method to `RowReorderBuffer` that uses `_submit_condition.wait_for(lambda: len(self._pending) == 0, timeout=...)`. This eliminates the polling thread entirely.

### Concern 7: Missing Audit Metadata for Evictions (Low Severity)

`RowReorderBuffer.evict()` has no metrics counter. Given that evictions are a signal of timeout behavior (a meaningful operational event), they should be counted.

**Recommendation:** Add `_total_evicted: int = 0` to `RowReorderBuffer` and increment in `evict()`. Include in `get_metrics()`.

---

## Confidence Assessment

**High Confidence:**
- The two-layer concurrency model (row-level via `BatchTransformMixin`, query-level via `PooledExecutor`) and how they compose.
- The FIFO ordering guarantees at both levels and their correctness.
- The retry safety design via `(token_id, state_id)` keying in `SharedBatchAdapter`.
- The error propagation paths (TransformResult vs ExceptionResult vs raised exception).
- The AIMD throttle mechanics and the deliberate separation of dispatch gate from AIMD.
- The semaphore placement rationale in `_execute_single()` (documented to prevent deadlock).

**Medium Confidence:**
- The exact failure modes of the `_release_loop()` exception handler (requires dynamic testing to validate all three branches behave as intended under concurrent failures).
- The eviction advancement logic in `RowReorderBuffer.evict()` for non-head evictions.
- Whether the `_batch_lock` serialization in `PooledExecutor` meaningfully limits throughput in multi-query transforms (depends on relative timing of query batches vs row processing).

**Low Confidence:**
- Performance characteristics at high concurrency (no profiling data available; relying on code analysis only).
- Whether `flush_batch_processing()` is actually called in production cleanup paths (cross-reference to orchestrator shutdown not fully traced).
