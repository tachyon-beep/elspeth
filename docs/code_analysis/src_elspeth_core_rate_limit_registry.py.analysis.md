# Analysis: src/elspeth/core/rate_limit/registry.py

**Lines:** 127
**Role:** Registry that manages rate limiter instances per service name. Creates limiters on demand based on `RuntimeRateLimitConfig`, reuses instances for the same service, and provides a `NoOpLimiter` for when rate limiting is disabled. Thread-safe for concurrent access.
**Key dependencies:** `elspeth.core.rate_limit.limiter.RateLimiter`, `threading`; TYPE_CHECKING import of `RuntimeRateLimitConfig`; imported by `cli.py`, `engine/orchestrator/core.py`, `plugins/context.py`, test files
**Analysis depth:** FULL

## Summary

This is a clean, minimal module. The registry pattern is straightforward, thread safety is correctly implemented with a lock, and the `NoOpLimiter` provides a clean null-object pattern. There are no critical findings. The warnings relate to the `NoOpLimiter` not implementing a formal protocol/ABC (relying on duck typing), and the registry's `close()` method not being idempotent-safe against concurrent calls.

## Warnings

### [15-48] NoOpLimiter relies on duck typing, not protocol conformance

**What:** `NoOpLimiter` mirrors the `RateLimiter` interface (same method names and signatures) but does not inherit from a common base class or implement a shared Protocol. The `get_limiter()` return type on line 84 is `RateLimiter | NoOpLimiter`, which means callers must handle the union type.

**Why it matters:** If `RateLimiter` gains a new method (e.g., `get_remaining_tokens()`), `NoOpLimiter` will not be updated and callers relying on the full `RateLimiter` interface will break. There is no compile-time enforcement that `NoOpLimiter` stays in sync with `RateLimiter`.

**Evidence:**
```python
class NoOpLimiter:
    """No-op limiter when rate limiting is disabled."""

    def acquire(self, weight: int = 1, timeout: float | None = None) -> None: ...
    def try_acquire(self, weight: int = 1) -> bool: ...
    def close(self) -> None: ...
```

No Protocol or ABC enforces this contract. The `plugins/clients/base.py` imports both `NoOpLimiter` and `RateLimiter` in TYPE_CHECKING, suggesting callers do handle the union.

### [119-127] close() and reset_all() have identical implementations

**What:** `close()` (lines 119-127) and `reset_all()` (lines 109-117) are identical: both close all limiters and clear the dict under the lock.

**Why it matters:** Code duplication. If close behavior changes (e.g., logging, metrics), both methods need updating. `close()` could delegate to `reset_all()`, or vice versa. The semantic difference (reset = continue using, close = done forever) is not enforced -- after `close()`, the registry could still have `get_limiter()` called on it, which would create new limiters.

**Evidence:**
```python
def reset_all(self) -> None:
    with self._lock:
        for limiter in self._limiters.values():
            limiter.close()
        self._limiters.clear()

def close(self) -> None:
    with self._lock:
        for limiter in self._limiters.values():
            limiter.close()
        self._limiters.clear()
```

### [99-107] get_limiter creates limiter under lock but limiter constructor does I/O

**What:** `RateLimiter.__init__()` (from limiter.py) creates SQLite connections and tables when `persistence_path` is set. This I/O happens while holding `self._lock`, which means all other `get_limiter()` calls block until the SQLite setup completes.

**Why it matters:** For the first call to `get_limiter()` per service, all other threads requesting any limiter (even for different services) are blocked while SQLite schema creation runs. This is unlikely to be a meaningful bottleneck (SQLite CREATE TABLE is fast), but it violates the principle of minimizing lock hold time.

**Evidence:**
```python
with self._lock:
    if service_name not in self._limiters:
        service_config = self._config.get_service_config(service_name)
        self._limiters[service_name] = RateLimiter(  # I/O under lock
            name=service_name,
            requests_per_minute=service_config.requests_per_minute,
            persistence_path=self._config.persistence_path,
        )
    return self._limiters[service_name]
```

## Observations

### [73-81] Constructor is clean

**What:** The registry stores config, initializes an empty dict with a lock, and pre-creates a single `NoOpLimiter`. No I/O or resource allocation in the constructor.

### [95-96] Disabled check is outside the lock

**What:** The `if not self._config.enabled` check on line 95 is outside the lock. Since `self._config` is a frozen dataclass (from `RuntimeRateLimitConfig`), this is safe -- the `enabled` field never changes after construction.

### [84] Return type annotation is explicit union

**What:** `get_limiter() -> RateLimiter | NoOpLimiter` correctly documents the two possible return types, enabling type checkers to verify callers handle both.

### No __enter__/__exit__ on RateLimitRegistry

**What:** The registry does not implement the context manager protocol. Callers must explicitly call `close()`. This is acceptable since the registry's lifetime is typically the entire pipeline run, managed by the orchestrator.

### Thread safety is correct

**What:** All mutations to `self._limiters` are under `self._lock`. The `NoOpLimiter` is shared across all disabled calls but is stateless, so sharing is safe.

## Verdict

**Status:** SOUND
**Recommended action:** Minor improvements: (1) Extract the close-and-clear logic to avoid duplication between `close()` and `reset_all()`. (2) Consider adding a Protocol for the limiter interface to prevent `NoOpLimiter` from drifting out of sync with `RateLimiter`. (3) Consider a `_closed` flag to prevent use-after-close. None of these are blocking.
**Confidence:** HIGH -- The module is small and straightforward. Thread safety is correct. The concerns are maintainability, not correctness.
