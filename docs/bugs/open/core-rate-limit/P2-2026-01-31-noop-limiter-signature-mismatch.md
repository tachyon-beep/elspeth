# Bug Report: NoOpLimiter.acquire() signature does not match RateLimiter.acquire()

## Summary

- `NoOpLimiter.acquire()` lacks `timeout` parameter that `RateLimiter.acquire()` has, causing TypeError when rate limiting is disabled and caller passes timeout.

## Severity

- Severity: moderate
- Priority: P2

## Reporter

- Name or handle: Codex (triaged by Claude)
- Date: 2026-01-31

## Evidence

- `src/elspeth/core/rate_limit/registry.py:22-27` - `NoOpLimiter.acquire(self, weight: int = 1)` lacks timeout.
- `src/elspeth/core/rate_limit/limiter.py:170-193` - `RateLimiter.acquire(self, weight: int = 1, timeout: float | None = None)` accepts timeout.

## Impact

- User-facing impact: TypeError when switching between rate-limited and non-rate-limited configs
- Data integrity: None

## Proposed Fix

- Add `timeout: float | None = None` parameter to `NoOpLimiter.acquire()`

## Acceptance Criteria

- NoOpLimiter and RateLimiter have matching signatures

## Verification (2026-02-01)

**Status: STILL VALID**

- `NoOpLimiter.acquire()` still omits `timeout`, while `RateLimiter.acquire()` accepts it. (`src/elspeth/core/rate_limit/registry.py:22-27`, `src/elspeth/core/rate_limit/limiter.py:170-193`)
