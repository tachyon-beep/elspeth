# Analysis: src/elspeth/plugins/pooling/throttle.py

**Lines:** 155
**Role:** AIMDThrottle implements a TCP-style Additive Increase / Multiplicative Decrease congestion control algorithm for API call pacing. On capacity errors, the delay multiplies (fast backoff). On success, a fixed amount is subtracted (slow recovery). Tracks statistics for audit trail. Used by `PooledExecutor` to adaptively rate-limit dispatches to external APIs.
**Key dependencies:** Imports only stdlib (`dataclasses`, `threading.Lock`). `ThrottleConfig` is imported by `config.py` for conversion. The `AIMDThrottle` class is instantiated by `PooledExecutor.__init__`. Re-exported from `__init__.py`.
**Analysis depth:** FULL

## Summary

The throttle is a clean, minimal state machine with correct thread safety. The AIMD algorithm implementation is standard and well-tested. I found one genuine bug: `on_success()` can drive `_current_delay_ms` negative before the floor check catches it, which works correctly due to the floor at line 115-116, but there's a subtle interaction where a negative delay minus `recovery_step_ms` stays negative through multiple success calls while `min_dispatch_delay_ms` is 0. This is cosmetic since the floor check corrects it, but `current_delay_ms` returning a negative value (briefly, between the subtraction and the clamp) cannot happen because the lock is held across both operations. So this is actually fine. The real concern is the stats accumulation issue raised in the executor analysis.

## Warnings

### [111-116] `on_success()` can drive delay negative before clamping

**What:** Line 112 unconditionally subtracts `recovery_step_ms` from `_current_delay_ms`:
```python
self._current_delay_ms -= self._config.recovery_step_ms
```
If `_current_delay_ms` is 0 and `min_dispatch_delay_ms` is 0 (the default), then after subtraction `_current_delay_ms` becomes `-50.0` (with default `recovery_step_ms=50`). The floor check at lines 115-116 then sets it to `0.0` (since `0.0 > -50.0`):
```python
if self._current_delay_ms < self._config.min_dispatch_delay_ms:
    self._current_delay_ms = float(self._config.min_dispatch_delay_ms)
```

**Why it matters:** This is functionally correct because the lock is held for the entire `on_success()` call, so no other thread can observe the intermediate negative value. The `current_delay_ms` property also acquires the lock, so it will always see the clamped value. However, the pattern is fragile -- if someone adds logic between the subtraction and the clamp that reads `_current_delay_ms`, they'd see a negative value. A clearer approach would be `self._current_delay_ms = max(self._current_delay_ms - step, min_val)`.

### [146-155] `reset_stats()` sets `_peak_delay_ms` to `_current_delay_ms`, not zero

**What:** Line 154:
```python
self._peak_delay_ms = self._current_delay_ms
```
After reset, `peak_delay_ms` reflects the current delay (which may be nonzero if the throttle is under pressure), not zero. This means the stat labeled "peak" may start at a nonzero value after reset.

**Why it matters:** This is a design choice, not a bug -- the peak after reset should reflect "peak since reset," and the current delay is a valid starting point. If the intent were "peak in this batch only," then zero would be more appropriate, and the next `on_capacity_error` would set it correctly anyway. However, this means that if `reset_stats()` is called while the throttle has a delay of 500ms, and the next batch has no capacity errors, `peak_delay_ms` will report 500ms for a batch that experienced no issues. This could mislead audit analysis.

This interacts with the P2 bug about stats not being reset between batches. Even if `reset_stats()` is called, the peak will carry over from the previous batch's delay state.

## Observations

### [17-35] ThrottleConfig is a frozen dataclass, not a Pydantic model

**What:** The docstring at line 22-24 explains this correctly: ThrottleConfig is internal runtime state, not user-facing YAML config. It's built from `PoolConfig.to_throttle_config()`. This correctly follows the Settings-to-Runtime pattern described in CLAUDE.md.

### [88-92] Bootstrap logic on first capacity error

**What:** When `_current_delay_ms == 0` (initial state), the first capacity error bootstraps the delay to `max(recovery_step_ms, min_dispatch_delay_ms)`. This ensures the first backoff respects the configured minimum. Subsequent errors multiply from there. This is a sensible design that avoids the degenerate case of `0 * multiplier = 0`.

### [62-63] Initial delay is 0.0 regardless of config

**What:** The throttle always starts with `_current_delay_ms = 0.0`, even if `min_dispatch_delay_ms > 0`. This means the first dispatch will have no AIMD delay. The dispatch gate in the executor separately enforces `min_dispatch_delay_ms`, so the initial dispatch is still paced, but the AIMD state doesn't reflect the configured minimum until the first capacity error.

After `on_success()` with delay at 0 and `min_dispatch_delay_ms = 10`, the delay becomes `max(-50, 10) = 10`. So a success at 0 delay with nonzero min would set it to min. This is correct but slightly surprising -- the first success "activates" the minimum delay.

### Thread safety model is correct and simple

**What:** Every public method acquires `self._lock`. The lock scope is minimal (a few arithmetic operations). No blocking I/O under the lock. No nested locks. No deadlock risk. No risk of lock contention since the operations are microsecond-level.

### No hysteresis or cooldown period

**What:** The AIMD algorithm has no "cooldown" concept -- a single success immediately starts reducing the delay. In aggressive retry scenarios where a service returns 429 then immediately succeeds on retry, the delay will quickly ramp back down, potentially causing another 429. Traditional TCP implementations use a "slow start" phase and a "congestion avoidance" phase. This simple AIMD implementation lacks these refinements.

**Why this is acceptable:** The executor's `_wait_for_dispatch_gate()` provides a separate minimum pacing floor. The combination of per-worker AIMD backoff and global dispatch gating provides two layers of protection. The simplicity is appropriate for the current use case.

## Verdict

**Status:** SOUND
**Recommended action:** When fixing the P2 stats accumulation bug, consider whether `reset_stats()` should set `_peak_delay_ms` to 0 rather than `_current_delay_ms`. Also consider adding a `max()` call to `on_success()` to make the clamping intent explicit and avoid the intermediate negative value.
**Confidence:** HIGH -- The module is small, well-tested (including edge cases for floor/ceiling behavior), and the concurrency model is trivial.
