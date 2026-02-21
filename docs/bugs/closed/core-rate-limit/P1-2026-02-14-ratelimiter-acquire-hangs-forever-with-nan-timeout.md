## Summary

`RateLimiter.acquire()` can hang forever when called with `timeout=float("nan")` instead of timing out or failing fast.

## Severity

- Severity: minor
- Priority: P2 (downgraded from P1 — no production caller passes timeout; parameter is unused in current codebase; defense-in-depth gap on unused API)

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/core/rate_limit/limiter.py`
- Line(s): 202-214
- Function/Method: `RateLimiter.acquire`

## Evidence

`acquire()` computes `deadline = time.monotonic() + timeout` and later checks:

```python
remaining = deadline - time.monotonic()
if remaining <= 0:
    raise TimeoutError(...)
time.sleep(min(0.01, remaining))
```

For `timeout = NaN`, `deadline` and `remaining` are `NaN`, and `remaining <= 0` is always `False`, so the loop never exits.

- Source: `/home/john/elspeth-rapid/src/elspeth/core/rate_limit/limiter.py:202-217`
- Integration path using this method: `/home/john/elspeth-rapid/src/elspeth/plugins/clients/base.py:105-106`

Runtime confirmation (local repro):
- Exhausted limiter once, then called `acquire(timeout=float("nan"))` in a thread.
- After 200ms, the thread was still alive and had not raised (`thread_alive_after_200ms True`).

Test coverage gap:
- Timeout tests only cover normal finite positive values; no non-finite timeout cases.
- `/home/john/elspeth-rapid/tests/unit/core/rate_limit/test_limiter.py:596-630`
- `/home/john/elspeth-rapid/tests/property/core/test_rate_limiter_properties.py:156-186`

## Root Cause Hypothesis

Input validation for `timeout` is incomplete. The code accepts any float-like value, but uses comparison/arithmetic logic that is not safe for non-finite values (`NaN`, `inf`), leading to non-terminating behavior instead of explicit failure.

## Suggested Fix

Validate timeout before computing deadline:

- If `timeout is None`: keep current behavior.
- Else require finite, non-negative numeric timeout.
- Raise `ValueError` for invalid values.

Example direction in `acquire()`:
- `if timeout is not None and (not math.isfinite(timeout) or timeout < 0): raise ValueError(...)`

Also add unit/property tests for `timeout=float("nan")`, `timeout=float("inf")`, and negative timeout.

## Impact

A bad timeout value can stall worker threads indefinitely on the rate-limiter path, blocking external calls and potentially hanging pipeline progress. In practice this can leave runs stuck without reaching expected terminal outcomes, degrading operational reliability and audit completeness.
