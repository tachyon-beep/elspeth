## Summary

`PoolConfig` accepts `backoff_multiplier=float("inf")`, but the runtime throttle rejects it, so invalid pooling config passes validation and then crashes during executor construction.

## Severity

- Severity: minor
- Priority: P2

## Location

- File: `/home/john/elspeth/src/elspeth/plugins/infrastructure/pooling/config.py`
- Line(s): 29, 55-61
- Function/Method: `PoolConfig`, `to_throttle_config`

## Evidence

`PoolConfig` only enforces `gt=1.0` on `backoff_multiplier`:

```python
backoff_multiplier: float = Field(2.0, gt=1.0, description="Backoff multiplier on capacity error")
```

Source: [config.py](/home/john/elspeth/src/elspeth/plugins/infrastructure/pooling/config.py#L29)

That allows positive infinity. I verified it in this repo:

```python
PoolConfig(pool_size=2, max_dispatch_delay_ms=1, backoff_multiplier=float("inf"))
# accepted
```

But `to_throttle_config()` forwards the value unchanged into `ThrottleConfig`:

```python
return ThrottleConfig(
    min_dispatch_delay_ms=self.min_dispatch_delay_ms,
    max_dispatch_delay_ms=self.max_dispatch_delay_ms,
    backoff_multiplier=self.backoff_multiplier,
    recovery_step_ms=self.recovery_step_ms,
)
```

Source: [config.py](/home/john/elspeth/src/elspeth/plugins/infrastructure/pooling/config.py#L55)

`ThrottleConfig` explicitly rejects non-finite multipliers:

```python
if not math.isfinite(self.backoff_multiplier) or self.backoff_multiplier <= 1.0:
    raise ValueError(...)
```

Source: [throttle.py](/home/john/elspeth/src/elspeth/plugins/infrastructure/pooling/throttle.py#L44)

`PooledExecutor` constructs the throttle immediately from `PoolConfig`:

```python
self._throttle = AIMDThrottle(config.to_throttle_config())
```

Source: [executor.py](/home/john/elspeth/src/elspeth/plugins/infrastructure/pooling/executor.py#L119)

And the LLM path reaches this constructor from validated config:

- [base.py](/home/john/elspeth/src/elspeth/plugins/transforms/llm/base.py#L100) builds `PoolConfig(...)`
- [transform.py](/home/john/elspeth/src/elspeth/plugins/transforms/llm/transform.py#L1035) passes it into `PooledExecutor(...)`

I also verified that `LLMConfig.from_dict(...)` accepts `backoff_multiplier=float("inf")` and produces a `PoolConfig` with `inf`, so this is not just a synthetic direct-construction case.

The existing pool-config tests cover `backoff_multiplier <= 1` but not non-finite values:
[tests/unit/plugins/llm/test_pool_config.py](/home/john/elspeth/tests/unit/plugins/llm/test_pool_config.py#L146)

## Root Cause Hypothesis

Validation is split across two layers with inconsistent contracts. `PoolConfig` is treated as already-validated runtime input for the pooling subsystem, but its field constraint is weaker than the downstream `ThrottleConfig` contract. As a result, invalid numeric state is admitted at the target file boundary and only rejected later when the executor materializes the throttle.

## Suggested Fix

Make `PoolConfig` enforce finiteness for `backoff_multiplier` before `to_throttle_config()` is called.

A minimal fix is to extend the existing model validator in [config.py](/home/john/elspeth/src/elspeth/plugins/infrastructure/pooling/config.py#L33) with `math.isfinite(self.backoff_multiplier)` and raise a config-time `ValueError` if it is not finite.

Also add regression tests in [test_pool_config.py](/home/john/elspeth/tests/unit/plugins/llm/test_pool_config.py) covering `float("inf")`, `float("-inf")`, and `float("nan")`.

## Impact

Invalid pooling config is accepted at validation time and then fails later during executor setup, which turns a clear config error into a runtime construction crash. This breaks plugin contract expectations for `PoolConfig`, makes failures harder to diagnose, and leaves the pooling subsystem with inconsistent validation behavior across its config and runtime layers.
