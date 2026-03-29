## Summary

`RuntimeRetryConfig` accepts non-finite float values (`inf`, and via direct construction `nan`), so invalid retry configuration can reach `RetryManager` and produce infinite backoff delays instead of failing fast.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `/home/john/elspeth/src/elspeth/contracts/config/runtime.py`
- Line(s): 159-175, 206-228
- Function/Method: `RuntimeRetryConfig.__post_init__`, `RuntimeRetryConfig.from_settings`

## Evidence

`RuntimeRetryConfig.__post_init__` validates only numeric ranges:

```python
require_int(self.max_attempts, "max_attempts", min_value=1)
if self.base_delay < 0.01:
    raise ValueError(...)
if self.max_delay < 0.1:
    raise ValueError(...)
if self.jitter < 0.0:
    raise ValueError(...)
if self.exponential_base <= 1.0:
    raise ValueError(...)
```

Source: `/home/john/elspeth/src/elspeth/contracts/config/runtime.py:167-175`

Those comparisons reject negative values, but they do not reject `math.inf` or `math.nan` because comparisons like `inf < 0.01` and `nan <= 1.0` are false. The same file already treats non-finite values as invalid in the policy path:

```python
if isinstance(value, float):
    if not math.isfinite(value):
        raise ValueError(...)
```

Source: `/home/john/elspeth/src/elspeth/contracts/config/runtime.py:70-75`, `/home/john/elspeth/src/elspeth/contracts/config/runtime.py:105-123`

`from_settings()` copies `RetrySettings` values straight into the runtime config with no finiteness check:

```python
return cls(
    max_attempts=settings.max_attempts,
    base_delay=settings.initial_delay_seconds,
    max_delay=settings.max_delay_seconds,
    jitter=float(INTERNAL_DEFAULTS["retry"]["jitter"]),
    exponential_base=settings.exponential_base,
)
```

Source: `/home/john/elspeth/src/elspeth/contracts/config/runtime.py:222-228`

`RetrySettings` itself uses only `gt` constraints, which still allow positive infinity:

```python
initial_delay_seconds: float = Field(default=1.0, gt=0, ...)
max_delay_seconds: float = Field(default=60.0, gt=0, ...)
exponential_base: float = Field(default=2.0, gt=1.0, ...)
```

Source: `/home/john/elspeth/src/elspeth/core/config.py:1136-1139`

Verified behavior in the repo environment:

- `RetrySettings(initial_delay_seconds=float('inf'))` succeeds.
- `RuntimeRetryConfig.from_settings(...)` then produces `base_delay=inf`.
- Direct `RuntimeRetryConfig(..., base_delay=float('nan'), ...)` also succeeds.

Downstream, `RetryManager` passes those values directly to tenacity:

```python
wait=wait_exponential_jitter(
    initial=self._config.base_delay,
    max=self._config.max_delay,
    exp_base=self._config.exponential_base,
    jitter=self._config.jitter,
)
```

Source: `/home/john/elspeth/src/elspeth/engine/retry.py:108-115`

In the same environment, `wait_exponential_jitter(initial=inf, max=inf, exp_base=2.0, jitter=1.0)` returns `inf`, so the retry sleep can become unbounded instead of failing at startup.

## Root Cause Hypothesis

The runtime retry config was hardened against out-of-range values after the earlier clamping bug, but the validation stopped at lower-bound checks and missed the separate “must be finite” invariant. The policy conversion helpers were updated to reject non-finite floats, but the dataclass constructor and `from_settings()` path were not brought into parity.

## Suggested Fix

Add explicit finiteness checks in `RuntimeRetryConfig.__post_init__` for all float fields before the range checks, for example:

```python
for field_name, value in (
    ("base_delay", self.base_delay),
    ("max_delay", self.max_delay),
    ("jitter", self.jitter),
    ("exponential_base", self.exponential_base),
):
    if not math.isfinite(value):
        raise ValueError(f"{field_name} must be finite, got {value}")
```

Then keep the existing lower-bound checks.

Also add regression coverage showing that:

- `RuntimeRetryConfig(base_delay=float("nan"), ...)` raises.
- `RuntimeRetryConfig(max_delay=float("inf"), ...)` raises.
- `RuntimeRetryConfig.from_settings(RetrySettings(initial_delay_seconds=float("inf")))` raises.

## Impact

Invalid retry settings can pass configuration loading and reach execution, where they can produce infinite retry waits or other non-finite timing behavior. That can stall transform retries indefinitely, violate fail-fast configuration guarantees, and make run behavior diverge from the project’s explicit rule that non-finite values must be rejected rather than silently carried into runtime.
