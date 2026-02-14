## Summary

`PoolConfig` accepts combinations that disable AIMD backoff entirely (`current_delay_ms` stays `0.0` on capacity errors), causing tight retry loops and API hammering instead of adaptive throttling.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth-rapid/src/elspeth/plugins/pooling/config.py
- Line(s): 28-41
- Function/Method: `PoolConfig._validate_delay_invariants`

## Evidence

`PoolConfig` currently validates only ordering (`min <= max`) and per-field lower bounds:

```python
# src/elspeth/plugins/pooling/config.py:28-32
min_dispatch_delay_ms: int = Field(0, ge=0, ...)
max_dispatch_delay_ms: int = Field(5000, ge=0, ...)
recovery_step_ms: int = Field(50, ge=0, ...)

# src/elspeth/plugins/pooling/config.py:37-40
if self.min_dispatch_delay_ms > self.max_dispatch_delay_ms:
    raise ValueError(...)
```

But runtime throttle logic depends on a positive bootstrap delay:

```python
# src/elspeth/plugins/pooling/throttle.py:91-99
self._current_delay_ms = float(max(self._config.recovery_step_ms, self._config.min_dispatch_delay_ms))
...
if self._current_delay_ms > self._config.max_dispatch_delay_ms:
    self._current_delay_ms = float(self._config.max_dispatch_delay_ms)
```

Retry sleep uses that delay directly:

```python
# src/elspeth/plugins/pooling/executor.py:476-479
retry_delay_ms = self._throttle.current_delay_ms
if retry_delay_ms > 0:
    time.sleep(retry_delay_ms / 1000)
```

So valid config values like `recovery_step_ms=0` and `min_dispatch_delay_ms=0` keep delay at zero forever.
I verified this in repo runtime:

- `AIMDThrottle` with `PoolConfig(..., min_dispatch_delay_ms=0, recovery_step_ms=0)` stayed at `0.0` after repeated `on_capacity_error()`.
- `PooledExecutor` with that config and `max_capacity_retry_seconds=1` executed ~518,110 retries in ~1s before timeout (`retry_timeout`), demonstrating a tight retry storm.

## Root Cause Hypothesis

Validation in `PoolConfig` is syntactic, not behavioral: it enforces numeric bounds and ordering but does not enforce that AIMD can actually increase to a positive delay. This allows mathematically valid yet operationally invalid configs that violate intended throttling semantics.

## Suggested Fix

Strengthen invariants in `PoolConfig._validate_delay_invariants` to require a viable positive backoff path, for example:

- `max_dispatch_delay_ms > 0`
- `min_dispatch_delay_ms > 0 OR recovery_step_ms > 0`

Example adjustment in `/home/john/elspeth-rapid/src/elspeth/plugins/pooling/config.py`:

```python
if self.max_dispatch_delay_ms <= 0:
    raise ValueError("max_dispatch_delay_ms must be > 0 for AIMD backoff")
if self.min_dispatch_delay_ms == 0 and self.recovery_step_ms == 0:
    raise ValueError(
        "At least one of min_dispatch_delay_ms or recovery_step_ms must be > 0 to bootstrap backoff"
    )
```

Also add regression tests in pool config/throttle tests for these zero-delay combinations.

## Impact

- Capacity errors can trigger extremely high-frequency retry loops (CPU burn, thread churn).
- External APIs can be hammered during outage/overload windows, worsening rate limiting and increasing failure blast radius.
- Observed behavior contradicts documented AIMD recovery expectations (reactive backoff), making retry control unreliable under stress.
