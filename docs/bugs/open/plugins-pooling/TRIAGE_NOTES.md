# Plugins-Pooling Bug Triage Notes (2026-02-14)

## Summary Table

| # | Bug | File | Original | Triaged | Verdict |
|---|-----|------|----------|---------|---------|
| 1 | AIMDThrottle zero-delay retry storm when both recovery and min_delay are zero | throttle.py | P1 | -- | Closed (duplicate of #2) |
| 2 | PoolConfig accepts combinations that disable AIMD backoff entirely | config.py | P1 | P1 | Confirmed |
| 3 | PooledExecutor shutdown race leaves reserved buffer slots stranded | executor.py | P1 | P2 | Downgraded |
| 4 | ReorderBuffer.get_ready_results rejects valid None payloads | reorder_buffer.py | P2 | P3 | Downgraded |

**Result:** 1 confirmed (P1), 1 closed (duplicate), 2 downgraded.

## Detailed Assessments

### Bug 1: AIMDThrottle zero-delay retry storm (CLOSED -- duplicate of Bug 2)

This bug and Bug 2 describe the exact same root cause from different angles: `min_dispatch_delay_ms=0` and `recovery_step_ms=0` producing zero bootstrap delay. Bug 1 frames it from the throttle side (line 92 of `throttle.py`), Bug 2 frames it from the config validation side (lines 28-41 of `config.py`). The correct fix location is `PoolConfig._validate_delay_invariants()` (Bug 2), which prevents the invalid state from reaching the throttle. Fixing Bug 2 makes Bug 1 unreachable. Closed as duplicate.

### Bug 2: PoolConfig accepts zero-delay AIMD combinations (P1 confirmed)

Genuine P1. Verified in source: `PoolConfig` allows `min_dispatch_delay_ms=0` and `recovery_step_ms=0` (both use `ge=0` validators at lines 28-31). The `_validate_delay_invariants` method only checks `min <= max` ordering. When both values are zero, `AIMDThrottle.on_capacity_error()` bootstraps to `max(0, 0) = 0.0`, and `PooledExecutor._execute_single` skips sleep when `retry_delay_ms == 0` (line 477). The bug report's repro of 500K+ retries per second is plausible and confirmed by the code path. This is a real operational hazard: capacity errors against external APIs would trigger a tight retry storm with no backoff, amplifying the overload condition. The fix belongs in `PoolConfig._validate_delay_invariants()`.

### Bug 3: PooledExecutor shutdown race with buffer slots (P1 -> P2)

The race condition is real: `_execute_batch_locked` reserves a buffer slot (line 261) then submits to the thread pool (line 269). If `shutdown()` closes the pool between these two operations, `submit()` raises `RuntimeError` and the reserved slot leaks. However, examining the actual usage pattern, `shutdown()` is called at cleanup time (end of pipeline or on error), not concurrently with active batch processing. The `_batch_lock` serializes batch execution, and `shutdown(wait=True)` is the default, which waits for pending work to complete. The `wait=False` case is only used in test cleanup and graceful-abort paths where leaked buffer state is acceptable (the executor is being discarded). The race requires precise timing of `shutdown(wait=False)` during active row submission, which is structurally unlikely in production flows. Still a real defensive gap worth fixing, but downgraded because the blast radius is limited to shutdown/cleanup scenarios where the executor is about to be discarded.

### Bug 4: ReorderBuffer rejects valid None payloads (P2 -> P3)

The analysis is technically correct: `assert entry.result is not None` at line 149 would reject `complete(idx, None)`, and `T` being `T | None` is type-theoretically valid. However, in practice, `ReorderBuffer` is only instantiated as `ReorderBuffer[TransformResult]` in the codebase (in `PooledExecutor`), and `TransformResult` is never `None` -- it is always a dataclass instance. No caller ever passes `None` as a result to `complete()`. The `-O` flag behavioral difference is a theoretical concern, but ELSPETH does not run with `-O` and the assert is functioning as intended (type narrowing for `_InternalEntry.result` from `T | None` to `T`). The sentinel-replacement suggestion is architecturally cleaner but has no production impact. Downgraded to P3 as a minor code hygiene improvement.

## Cross-Cutting Observations

### 1. Config validation must enforce behavioral invariants, not just syntactic bounds

Bug 2 shows that per-field `ge=0` validators and ordering checks (`min <= max`) are insufficient. The AIMD algorithm has a behavioral invariant: the bootstrap seed must be positive for backoff to function. Config validation should enforce these algorithm-level invariants, not just numeric ranges. This pattern may affect other config classes that parameterize algorithms with interdependent fields.

### 2. Bugs 1 and 2 are the same root cause -- analysis tool generated duplicates

The static analysis tool reported the same zero-delay-bootstrap issue twice: once from the throttle perspective and once from the config perspective. Future triage should deduplicate findings that share the same root cause before filing separate bug reports.
