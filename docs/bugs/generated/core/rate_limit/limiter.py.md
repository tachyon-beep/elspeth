## Summary

`RateLimiter` does not validate `weight`, so invalid values either bypass throttling silently (`0`, `True`) or leak third-party assertions (`-1`) instead of failing fast in ELSPETH-owned code.

## Severity

- Severity: major
- Priority: P2

## Location

- File: `/home/john/elspeth/src/elspeth/core/rate_limit/limiter.py`
- Line(s): 190-249
- Function/Method: `RateLimiter.acquire`, `RateLimiter.try_acquire`

## Evidence

[`/home/john/elspeth/src/elspeth/core/rate_limit/limiter.py#L190`]( /home/john/elspeth/src/elspeth/core/rate_limit/limiter.py#L190 ) accepts `weight` and immediately forwards it into `try_acquire()`:

```python
def acquire(self, weight: int = 1, timeout: float | None = None) -> None:
    ...
    while True:
        if self.try_acquire(weight):
            return
```

[`/home/john/elspeth/src/elspeth/core/rate_limit/limiter.py#L230`]( /home/john/elspeth/src/elspeth/core/rate_limit/limiter.py#L230 ) never validates `weight` before calling the library:

```python
def try_acquire(self, weight: int = 1) -> bool:
    with self._lock:
        ...
        self._limiter.try_acquire(self.name, weight=weight)
```

Because there is no guard in our wrapper:

- `weight=0` is accepted and returns success without consuming quota.
- `weight=True` is accepted because `bool` is an `int`, so the limiter silently treats it as `1`.
- `weight=-1` escapes as `AssertionError` from `pyrate-limiter`, not a deliberate ELSPETH exception.

I verified those behaviors directly against this wrapper:
- `RateLimiter(...).try_acquire(weight=0)` returned `True`
- `RateLimiter(...).acquire(weight=0, timeout=0.01)` returned successfully
- `RateLimiter(...).try_acquire(weight=-1)` raised `AssertionError: item's weight must be >= 0`
- `RateLimiter(...).try_acquire(weight=True)` returned `True`

The existing tests only cover positive weights such as [`/home/john/elspeth/tests/unit/core/rate_limit/test_limiter.py#L151`]( /home/john/elspeth/tests/unit/core/rate_limit/test_limiter.py#L151 ) and [`/home/john/elspeth/tests/property/core/test_rate_limiter_properties.py#L122`]( /home/john/elspeth/tests/property/core/test_rate_limiter_properties.py#L122 ), so this gap is currently untested.

## Root Cause Hypothesis

The wrapper validates `name`, `requests_per_minute`, and `timeout`, but omitted equivalent offensive validation for `weight`. That lets dependency-specific behavior define the contract for invalid inputs, which violates ELSPETH’s “crash informatively in our code” rule and creates a silent zero-weight bypass.

## Suggested Fix

Validate `weight` in ELSPETH code before any library call:

```python
def _validate_weight(weight: int) -> None:
    if type(weight) is not int:
        raise TypeError(
            f"weight must be int, got {type(weight).__name__}: {weight!r} — this is a bug in the calling code"
        )
    if weight <= 0:
        raise ValueError(f"weight must be positive, got {weight!r}")
```

Call that helper from both `acquire()` and `try_acquire()`, and add tests for `0`, negative values, and `bool`.

## Impact

Callers can accidentally skip rate limiting entirely by passing `0`, and malformed callers get inconsistent failure modes from a third-party assertion instead of a stable ELSPETH contract. In practice, that can produce bursty external API traffic that the caller believes was throttled, or confusing crashes that point at `pyrate-limiter` rather than the bad call site.
---
## Summary

`RateLimiter.close()` releases the SQLite connection but never invalidates the limiter, so an in-memory limiter remains usable after close and a persistent limiter can be called after teardown against already-closed resources.

## Severity

- Severity: minor
- Priority: P2

## Location

- File: `/home/john/elspeth/src/elspeth/core/rate_limit/limiter.py`
- Line(s): 239-249, 251-309
- Function/Method: `RateLimiter.try_acquire`, `RateLimiter.close`, `RateLimiter.__exit__`

## Evidence

[`/home/john/elspeth/src/elspeth/core/rate_limit/limiter.py#L251`]( /home/john/elspeth/src/elspeth/core/rate_limit/limiter.py#L251 ) performs cleanup, but it does not set any closed flag:

```python
def close(self) -> None:
    ...
    if self._conn is not None:
        self._conn.close()
        self._conn = None
```

[`/home/john/elspeth/src/elspeth/core/rate_limit/limiter.py#L230`]( /home/john/elspeth/src/elspeth/core/rate_limit/limiter.py#L230 ) and [`/home/john/elspeth/src/elspeth/core/rate_limit/limiter.py#L190`]( /home/john/elspeth/src/elspeth/core/rate_limit/limiter.py#L190 ) never check whether the object has already been closed before continuing to use `_limiter` and `_bucket`.

That matters because limiter references are retained by clients and transforms, for example:
- [`/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/base.py#L95`]( /home/john/elspeth/src/elspeth/plugins/infrastructure/clients/base.py#L95 )
- [`/home/john/elspeth/src/elspeth/src/elspeth/plugins/transforms/azure/base.py#L127`]( /home/john/elspeth/src/elspeth/plugins/transforms/azure/base.py#L127 )

I verified the current behavior directly:
- After `close()` on an in-memory limiter, `try_acquire()` still returned `True`
- After that same close, `acquire(timeout=0.01)` kept operating until timeout rather than failing as “closed”
- `close()` is effectively idempotent, but use-after-close is not prevented

The resource-management tests only assert that close does not raise, e.g. [`/home/john/elspeth/tests/property/core/test_rate_limiter_state_machine.py#L393`]( /home/john/elspeth/tests/property/core/test_rate_limiter_state_machine.py#L393 ); they never assert that the limiter becomes unusable afterward.

## Root Cause Hypothesis

`close()` was implemented as best-effort cleanup around the library’s leaker thread, but lifecycle state was never modeled in the wrapper itself. As a result, the object still presents a live API after teardown, even though part of its underlying resource graph has been dismantled.

## Suggested Fix

Add `_closed: bool = False`, set it in `close()`, and reject any later `acquire()` or `try_acquire()` with a clear `RuntimeError`. Guard `close()` itself so repeated calls remain harmless.

Example shape:

```python
if self._closed:
    raise RuntimeError(f"RateLimiter {self.name!r} has been closed")
```

Also add explicit post-close tests for both in-memory and persistent limiters.

## Impact

This is a lifecycle/resource-management bug: callers can keep using a limiter after teardown, getting silently wrong behavior for in-memory buckets and undefined behavior for persistent ones. That undermines the wrapper’s cleanup contract and makes shutdown-related failures harder to diagnose because the misuse is not surfaced at the ELSPETH boundary.
