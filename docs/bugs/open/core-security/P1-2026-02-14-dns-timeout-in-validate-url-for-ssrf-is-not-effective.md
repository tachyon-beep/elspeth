## Summary

Configured DNS timeout in `validate_url_for_ssrf()` is not an effective timeout; the function can still block until DNS resolution finishes.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth-rapid/src/elspeth/core/security/web.py
- Line(s): 226-231
- Function/Method: validate_url_for_ssrf

## Evidence

`validate_url_for_ssrf()` wraps DNS resolution in a `with ThreadPoolExecutor(...)` block and calls `future.result(timeout=timeout)`:

```python
with ThreadPoolExecutor(max_workers=1, thread_name_prefix="dns_resolve") as executor:
    future = executor.submit(_resolve)
    try:
        ip_list = future.result(timeout=timeout)
    except FuturesTimeoutError as e:
        raise NetworkError(...)
```

`ThreadPoolExecutor.__exit__` performs `shutdown(wait=True)`, so after timeout is raised, exiting the `with` block still waits for the resolver thread to finish. This defeats the intended timeout bound.

Observed reproduction in this environment (same Python concurrency semantics): a `0.1s` `future.result(timeout=...)` inside a `with ThreadPoolExecutor` still took ~`2.0s` wall time when worker slept 2s.

Test coverage misses this behavior because the fake executor in `tests/unit/core/security/test_web_ssrf_network_failures.py:22-36` has an `__exit__` that does not emulate real `shutdown(wait=True)` semantics.

## Root Cause Hypothesis

Timeout handling assumes `future.result(timeout=...)` alone bounds total call time, but the context manager teardown waits for the blocking DNS call anyway.

## Suggested Fix

In `validate_url_for_ssrf()`, avoid context-manager teardown waiting on timeout path. Use explicit executor lifecycle and non-blocking shutdown in `finally`, e.g. `shutdown(wait=False, cancel_futures=True)`, and normalize timeout handling there. If strict timeout guarantees are required, move DNS resolution to a process-based boundary (threads cannot forcibly stop `getaddrinfo`).

## Impact

A malicious or unhealthy resolver can stall row processing far beyond configured timeout, reducing throughput and causing retry/latency behavior to diverge from configured policy.
