## Summary

`AIMDThrottle` can enter a zero-delay retry storm when both `recovery_step_ms` and `min_dispatch_delay_ms` are `0`, causing capacity-error retries to spin without backoff.

## Severity

- Severity: major
- Priority: P1
- Status: CLOSED (duplicate)
- Closed reason: Duplicate of P1-2026-02-14-poolconfig-accepts-combinations-that-disable-aimd-backoff-entirely. Same root cause (zero bootstrap delay), fix belongs in PoolConfig validation.

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/plugins/pooling/throttle.py`
- Line(s): 32-35, 89-93
- Function/Method: `ThrottleConfig`, `AIMDThrottle.on_capacity_error`

## Evidence

`ThrottleConfig` permits `min_dispatch_delay_ms=0` and `recovery_step_ms=0` (`throttle.py:32-35`).
`on_capacity_error()` bootstraps from zero using:

```python
self._current_delay_ms = float(max(self._config.recovery_step_ms, self._config.min_dispatch_delay_ms))
```

(`throttle.py:89-93`), which stays `0.0` when both are zero.

In `PooledExecutor`, retry sleep is only performed when `retry_delay_ms > 0` (`src/elspeth/plugins/pooling/executor.py:476-479`), so zero delay means immediate reattempts.

Upstream config allows this state (`src/elspeth/plugins/pooling/config.py:28-31`).

Local runtime repro in this repo:
- Repeated `on_capacity_error()` with both values `0` kept delay at `0.0` each time.
- One row with always-failing `CapacityError` and `max_capacity_retry_seconds=1` executed `574,670` attempts before timeout.

Tests cover positive recovery values but do not cover the both-zero seed case (`tests/unit/plugins/llm/test_aimd_throttle.py:39-79`).

## Root Cause Hypothesis

The throttle algorithm assumes a positive bootstrap seed for AIMD, but target-file config/state logic does not enforce that invariant. When seed is zero, multiplicative backoff never starts and retry pacing collapses.

## Suggested Fix

In `throttle.py`, enforce invariants at runtime config boundary and fail clearly:

- Add `ThrottleConfig.__post_init__` to validate:
  - `min_dispatch_delay_ms <= max_dispatch_delay_ms`
  - `backoff_multiplier > 1.0`
  - `max(min_dispatch_delay_ms, recovery_step_ms) > 0` (required for non-zero AIMD bootstrap)
- In `on_capacity_error`, guard bootstrap seed (`<= 0`) with explicit `ValueError`/`RuntimeError` rather than silently continuing.

This keeps the primary fix in the target file and prevents silent zero-delay retry loops.

## Impact

Capacity errors can trigger a tight retry loop (effectively hammering external APIs), causing quota/cost spikes, rate-limit amplification, and unnecessary CPU churn. It also creates an observability blind spot because no throttle wait is recorded when delay stays zero.
