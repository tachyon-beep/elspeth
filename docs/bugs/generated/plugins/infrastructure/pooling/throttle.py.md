## Summary

`AIMDThrottle` under-backs off after recovery when `min_dispatch_delay_ms > 0`: once successes floor the throttle to the minimum delay, the next capacity error multiplies that baseline floor instead of re-seeding congestion backoff from `recovery_step_ms`.

## Severity

- Severity: major
- Priority: P2

## Location

- File: `/home/john/elspeth/src/elspeth/plugins/infrastructure/pooling/throttle.py`
- Line(s): 101-107, 123-128
- Function/Method: `AIMDThrottle.on_capacity_error`, `AIMDThrottle.on_success`

## Evidence

`on_success()` pushes `_current_delay_ms` down to the configured minimum, not to an uncongested state:

```python
# /home/john/elspeth/src/elspeth/plugins/infrastructure/pooling/throttle.py:123-128
with self._lock:
    self._current_delay_ms -= self._config.recovery_step_ms
    if self._current_delay_ms < self._config.min_dispatch_delay_ms:
        self._current_delay_ms = float(self._config.min_dispatch_delay_ms)
```

Then `on_capacity_error()` only uses the documented bootstrap path when `_current_delay_ms == 0`:

```python
# /home/john/elspeth/src/elspeth/plugins/infrastructure/pooling/throttle.py:100-107
with self._lock:
    if self._current_delay_ms == 0:
        self._current_delay_ms = float(max(self._config.recovery_step_ms, self._config.min_dispatch_delay_ms))
    else:
        self._current_delay_ms *= self._config.backoff_multiplier
```

That means this sequence is possible:

1. Configure `min_dispatch_delay_ms=10`, `recovery_step_ms=100`.
2. A success path floors the throttle to `10` ms.
3. The next capacity error goes down the `else` branch and becomes `20` ms, not the documented bootstrap value `100` ms.

This matters because the executor already enforces `min_dispatch_delay_ms` separately via the dispatch gate:

```python
# /home/john/elspeth/src/elspeth/plugins/infrastructure/pooling/executor.py:366-378
# NOTE: This gate intentionally uses only the static min_dispatch_delay_ms,
# NOT the AIMD delay.
delay_ms = self._config.min_dispatch_delay_ms
if delay_ms <= 0:
    return
```

So the throttle state is being used for reactive congestion control, while the static minimum spacing is already handled elsewhere. Mixing the two causes the first post-recovery capacity error to back off far less than configured.

Repository docs also describe AIMD as the reactive 429 handler:

```python
# /home/john/elspeth/docs/reference/configuration.md:807-810
2. **PooledExecutor AIMD (Reactive)**
   - Handles 429 errors that slip through
   - Uses AIMD backoff: multiply delay on 429, subtract on success
```

The existing tests cover:
- bootstrap from `0` on first error (`tests/unit/plugins/llm/test_aimd_throttle.py:39-47`)
- flooring to `min_dispatch_delay_ms` after repeated successes (`tests/unit/plugins/llm/test_aimd_throttle.py:101-116`)

But there is no test for “recovered to min, then capacity error again,” which is the broken path.

## Root Cause Hypothesis

`AIMDThrottle` stores the static dispatch floor and the congestion-backoff state in the same `_current_delay_ms` variable. After recovery, `_current_delay_ms` remains at the minimum dispatch delay, so the next capacity error is treated as “already congested” and multiplied from that baseline instead of being bootstrapped from the configured recovery step. The file’s own bootstrap condition (`== 0`) becomes unreachable in steady-state configurations where `min_dispatch_delay_ms > 0`.

## Suggested Fix

Keep the baseline dispatch floor distinct from the congestion state, or at minimum treat “at baseline floor” as the bootstrap condition.

A minimal fix in this file would be to bootstrap when the throttle is at or below the configured minimum:

```python
def on_capacity_error(self) -> None:
    with self._lock:
        if self._current_delay_ms <= self._config.min_dispatch_delay_ms:
            self._current_delay_ms = float(
                max(self._config.recovery_step_ms, self._config.min_dispatch_delay_ms)
            )
        else:
            self._current_delay_ms *= self._config.backoff_multiplier
        if self._current_delay_ms > self._config.max_dispatch_delay_ms:
            self._current_delay_ms = float(self._config.max_dispatch_delay_ms)
```

Add a regression test covering:
- `ThrottleConfig(min_dispatch_delay_ms=10, recovery_step_ms=100, backoff_multiplier=2.0)`
- recover to `10`
- next `on_capacity_error()` should become `100`, not `20`

## Impact

Reactive throttling is weaker than configured after any successful period with a non-zero minimum dispatch delay. In practice, the pooled executor will keep retrying capacity-limited calls with too-small delays, increasing repeated 429/529 responses, prolonging recovery, and making `max_capacity_retry_seconds` timeouts more likely under load. This does not directly corrupt audit lineage, but it degrades the executor’s rate-limit recovery behavior and makes the recorded throttle statistics understate the intended congestion response.
