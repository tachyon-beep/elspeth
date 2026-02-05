# Analysis: src/elspeth/core/rate_limit/limiter.py

**Lines:** 270
**Role:** Rate limiter wrapper around `pyrate-limiter` for external API call budgets. Provides blocking and non-blocking acquire, optional SQLite persistence for cross-process rate limiting, and cleanup handling for pyrate-limiter's known race conditions during shutdown.
**Key dependencies:** `pyrate_limiter` (InMemoryBucket, SQLiteBucket, Limiter, Rate, Duration, BucketFullException, SQLiteQueries), `sqlite3`, `threading`; imported by `registry.py`, `plugins/clients/base.py`, test files
**Analysis depth:** FULL

## Summary

This module is the most complex of the five assigned files due to its management of threading, global state (custom excepthook), and interaction with pyrate-limiter internals. The core rate limiting logic is correct. However, there are concerns about global state mutation at import time, accessing private attributes of pyrate-limiter, and the `try_acquire()` method's non-thread-safe mutation of `max_delay`. There are no data integrity risks (this module does not interact with the audit trail), but resource management and concurrency correctness are the primary concerns.

## Critical Findings

### [209-219] try_acquire mutates shared Limiter state under a lock, but acquire() calls try_acquire() in a spin loop

**What:** `try_acquire()` on line 200 acquires `self._lock`, then mutates `self._limiter.max_delay` to `None` (line 212), calls `self._limiter.try_acquire()` (line 214), and restores the original value (line 219). This is wrapped in a `try/finally` to ensure restoration.

The issue: `acquire()` (line 170) calls `try_acquire()` in a `while True` loop. Each iteration acquires the lock, mutates `max_delay`, calls the library, and restores it. If the library's `try_acquire()` internally spawns or interacts with threads that read `max_delay`, the temporary `None` value could cause unexpected behavior in those threads.

More concretely: the `Limiter` object is shared. If two `RateLimiter` instances share the same underlying `Limiter` (they don't in current code -- each `RateLimiter` creates its own), this would be a race. In the current implementation, each `RateLimiter` creates its own `Limiter`, so this is safe. But the pattern of mutating and restoring a shared object's state is fragile.

**Why it matters:** The current code is safe because each `RateLimiter` has its own `Limiter` instance. But the pattern is a maintenance hazard. If pyrate-limiter's `Limiter` is ever shared (e.g., for multi-bucket rate limiting), this becomes a race condition. The `self._lock` protects against concurrent `try_acquire()` calls on the same `RateLimiter`, but does not protect the `Limiter` object from its own internal threads.

**Severity assessment:** Not a current bug, but a latent hazard. Downgrading from Critical to Warning on reflection -- the current isolation (one Limiter per RateLimiter) makes this safe today.

## Warnings

### [74-75] Global excepthook replacement at import time

**What:** Line 75 (`threading.excepthook = _custom_excepthook`) replaces the global thread exception hook when this module is imported. This affects ALL threads in the process, not just rate limiter threads.

**Why it matters:**
1. **Side effect on import:** Simply importing `elspeth.core.rate_limit.limiter` changes global process behavior. Any test or tool that imports this module gets the custom excepthook.
2. **Non-composable:** If another library also replaces `threading.excepthook`, whichever imports last wins. The `_original_excepthook` (line 28) captures the hook at import time -- if another library replaces it before us, we capture their hook; if after us, they overwrite ours.
3. **Suppression scope:** The hook suppresses `AssertionError` for registered thread idents (line 59). If a rate limiter's leaker thread ident is reused by a new thread (thread ident recycling is allowed by Python), the wrong thread's `AssertionError` could be suppressed.

**Evidence:**
```python
_original_excepthook = threading.excepthook  # Line 28 - captured at import
threading.excepthook = _custom_excepthook     # Line 75 - replaced at import
```

**Mitigating factors:** The suppression requires both (a) the thread ident being registered in `_suppressed_thread_idents` and (b) the exception being `AssertionError`. The `close()` method cleans up after itself (lines 252-253). Thread ident reuse between `close()` adding the ident and the cleanup removing it would require extremely tight timing.

### [226] Accessing private attribute of pyrate-limiter

**What:** `self._limiter.bucket_factory._leaker` accesses a private attribute of pyrate-limiter's internals. This is brittle and will break if pyrate-limiter changes its internal structure.

**Why it matters:** pyrate-limiter upgrades could silently break the cleanup logic. The `_leaker` attribute name suggests it is not part of the public API. A pyrate-limiter minor version bump could rename or remove this attribute, causing `AttributeError` in `close()`.

**Evidence:**
```python
leaker = self._limiter.bucket_factory._leaker  # Private attribute access
```

### [155] SQLite connection with check_same_thread=False

**What:** `sqlite3.connect(persistence_path, check_same_thread=False)` disables SQLite's thread safety check. This allows multiple threads to use the same connection, but SQLite connections are not thread-safe by default.

**Why it matters:** The `self._lock` in `try_acquire()` serializes access to the limiter, which indirectly serializes SQLite access through the bucket. But `acquire()` calls `try_acquire()` in a loop with `time.sleep()` between iterations -- the lock is released during sleep, allowing other threads to access the connection. This is safe because each `try_acquire()` call acquires the lock before touching the bucket. However, if any code path accesses `self._bucket` outside the lock, the SQLite connection could be used concurrently.

**Evidence:** All bucket access goes through `self._limiter.try_acquire()` which is called under `self._lock`. The `close()` method accesses `self._limiter.dispose()` and `self._conn.close()` without holding `self._lock`, but `close()` is a terminal operation expected to be called when no other threads are using the limiter.

### [185-198] acquire() spin loop with 10ms sleep is CPU-inefficient for long waits

**What:** The `acquire()` method polls `try_acquire()` every 10ms. For a rate limiter configured at, say, 1 request per minute, a thread waiting for the next window would spin for up to 60 seconds, making ~6000 lock acquisitions and `try_acquire()` calls.

**Why it matters:** In a pipeline processing many rows with aggressive rate limiting, multiple threads could be spin-waiting simultaneously. Each spin iteration acquires `self._lock`, mutates `max_delay`, calls the library, and restores `max_delay`. This is wasteful compared to using pyrate-limiter's built-in delay mechanism (which `max_delay` is designed for).

**Evidence:**
```python
while True:
    if self.try_acquire(weight):
        return
    if deadline is not None:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(...)
        time.sleep(min(0.01, remaining))  # 10ms polling
    else:
        time.sleep(0.01)  # 10ms polling
```

The irony is that `max_delay` on the Limiter (line 168) is set to `self._window_ms`, which would make the library wait internally -- but `try_acquire()` sets it to `None` to get an immediate response. The polling loop reimplements what pyrate-limiter would do natively with `max_delay`.

### [33] Module-level mutable global state

**What:** `_suppressed_thread_idents: set[int] = set()` is a module-level mutable set. It is correctly protected by `_suppressed_lock`, but its existence as global state means:
1. It persists across tests if the module is not reloaded
2. It accumulates idents if `close()` fails to clean up (e.g., if an exception occurs between add and discard)

**Why it matters:** In test environments, thread idents from previous test runs could remain in the set. The `discard()` calls in `close()` and the excepthook handle cleanup, but if `close()` is never called (test crashes, fixture teardown failure), the set grows unboundedly. This is a minor memory leak (ints are small), not a correctness issue.

## Observations

### [103-168] Constructor validation is thorough

**What:** Name validation (regex), rate limit positivity check, and window positivity check are all performed before any resources are allocated. The name regex (`^[a-zA-Z][a-zA-Z0-9_]*$`) prevents SQL injection in the SQLite table name.

### [259-270] Context manager support is correct

**What:** `__enter__` returns self, `__exit__` calls `close()`. This enables `with RateLimiter(...) as limiter:` usage.

### [221-257] close() cleanup sequence is well-ordered

**What:** The close method (1) captures leaker reference, (2) registers for exception suppression, (3) disposes bucket, (4) waits for leaker thread, (5) cleans up suppression set, (6) closes SQLite connection. The ordering is deliberate and documented.

### [37-71] Custom excepthook is narrowly scoped

**What:** The excepthook only suppresses AssertionError for registered thread idents. All other exceptions are passed to the original hook. This is the correct approach for handling a known library issue without affecting unrelated code.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** The global excepthook replacement at import time is the primary concern. Consider deferring the hook installation until the first `RateLimiter` is created (lazy installation), and restoring the original hook when all limiters are closed. The private attribute access (`bucket_factory._leaker`) should be documented as a pinned dependency risk -- pyrate-limiter version upgrades should be tested for compatibility. The spin-loop in `acquire()` could use pyrate-limiter's native delay mechanism instead of reimplementing it.
**Confidence:** HIGH -- The code is well-documented and the known pyrate-limiter issues are explicitly handled. The concerns are architectural (global state, private API access) rather than correctness bugs.
