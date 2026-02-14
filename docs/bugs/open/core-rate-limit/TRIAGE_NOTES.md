# Core Rate-Limit Triage Notes

**Triaged:** 2026-02-14
**Scope:** `docs/bugs/open/core-rate-limit/` (1 finding)

## Summary

| # | File | Original | Triaged | Verdict |
|---|------|----------|---------|---------|
| 1 | `P1-...-ratelimiter-acquire-hangs-forever-with-nan-timeout.md` | P1 | **P2 downgrade** | Real but unreachable via production callers |

## Detailed Assessment

### Finding 1: `acquire()` hangs forever with NaN timeout — DOWNGRADED to P2

**Verdict: Real bug, but downgraded from P1 to P2.**

The static analysis is technically correct — `timeout=float("nan")` does create an infinite loop at
`limiter.py:202-217` because `NaN <= 0` is always `False` (IEEE 754 semantics).

**However, the integration path cited in the bug report does not pass a timeout:**

```python
# plugins/clients/base.py:105-106
if self._limiter is not None:
    self._limiter.acquire()  # No timeout argument — uses default None (wait forever)
```

No production caller passes a `timeout` argument to `acquire()`. The `timeout` parameter exists
for API flexibility but is unused in the current codebase. For NaN to reach this function, it would
need to come from:
1. A config NaN flowing through Pydantic (the known P0 NaN-in-float-validation issue)
2. An arithmetic error producing NaN somewhere upstream
3. A future caller explicitly passing NaN

This is a defense-in-depth gap on a currently-unused parameter. The fix is trivial (one-line
`math.isfinite()` guard) and worthwhile, but P2 is the appropriate severity given no production path.

**Relationship to known P0:** The root cause (NaN accepted by Pydantic float validation) is already
tracked as a known P0 issue. Fixing the upstream boundary would prevent NaN from reaching any
downstream function.
