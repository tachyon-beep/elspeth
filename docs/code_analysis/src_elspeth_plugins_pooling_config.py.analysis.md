# Analysis: src/elspeth/plugins/pooling/config.py

**Lines:** 50
**Role:** Pydantic configuration model for the pooling subsystem. Defines `PoolConfig` with validation for pool size, dispatch delay bounds, AIMD backoff parameters, and capacity retry timeout. Provides `to_throttle_config()` for converting to the runtime `ThrottleConfig` dataclass.
**Key dependencies:** Imports `BaseModel`, `Field`, `model_validator` from Pydantic; `ThrottleConfig` from `throttle.py`. Consumed by `executor.py` (constructor), `azure_multi_query.py`, `openrouter_multi_query.py`, `prompt_shield.py`, `content_safety.py`, and `base.py` (LLM transform base class).
**Analysis depth:** FULL

## Summary

This is a well-structured configuration class with appropriate validation constraints. The `to_throttle_config()` method follows the project's Settings-to-Runtime pattern. The `model_config = {"extra": "forbid"}` prevents unrecognized fields. I found no bugs but identified two minor design concerns around default values and a missing validation for `recovery_step_ms` relative to `min_dispatch_delay_ms`.

## Warnings

### [31] `recovery_step_ms` can be 0, leading to no recovery from backoff

**What:** `recovery_step_ms` has constraint `ge=0`, allowing a value of 0. If set to 0, `on_success()` in `AIMDThrottle` will subtract 0 from the delay, meaning the delay never decreases after capacity errors. The throttle would ramp up on errors but never recover.

**Why it matters:** A user configuring `recovery_step_ms: 0` would create a throttle that only increases delay, never decreases. After the first capacity error, every subsequent dispatch would be delayed by at least the bootstrap value, and every additional error would multiply it further. Successes would have no effect. The pipeline would progressively slow to `max_dispatch_delay_ms` and stay there permanently.

While this is a valid configuration choice (some users might want to be extremely conservative), it's a surprising footgun. A value of 0 disables recovery entirely, which is unlikely to be intentional.

**Evidence:**
```python
recovery_step_ms: int = Field(50, ge=0, description="Recovery step in milliseconds")
```

### [32] Default `max_capacity_retry_seconds` of 3600 (1 hour) may be too generous

**What:** The default retry timeout for capacity errors is 3600 seconds (1 hour). This means a single row's transform could retry for up to an hour before giving up.

**Why it matters:** In a pipeline processing thousands of rows, a single row hitting persistent capacity limits would block its worker thread for up to an hour. With the default `pool_size=1`, this would stall the entire pipeline for an hour on a single row's persistent 429 errors. Even with a larger pool, each stuck row consumes a thread. The default seems designed for batch processing scenarios where throughput is more important than latency, but it could surprise users who expect faster failure.

## Observations

### [34-41] Model validator correctly enforces min <= max for dispatch delays

**What:** The `_validate_delay_invariants` validator ensures `min_dispatch_delay_ms <= max_dispatch_delay_ms`. This is the correct constraint. Pydantic's `mode="after"` ensures individual field validators run first (ge=0 checks).

### [25] `extra = "forbid"` prevents config drift

**What:** The `model_config = {"extra": "forbid"}` setting means any unrecognized YAML fields under the pool config will cause a validation error. This is the correct approach for catching typos and preventing silent config errors (e.g., `pool_sizee: 10` would be caught).

### [43-50] `to_throttle_config()` correctly maps all throttle-relevant fields

**What:** The conversion method maps exactly four fields to `ThrottleConfig`. Notably, `pool_size` and `max_capacity_retry_seconds` are not passed to the throttle (they're used by the executor directly). This separation is clean -- the throttle only needs delay-related parameters.

### [27] Default `pool_size=1` is conservative but appropriate

**What:** The default pool size of 1 means no parallelism by default. Users must explicitly opt in to concurrent execution. This is the safe default for a system where API rate limits are a primary concern.

### No validation that `recovery_step_ms <= max_dispatch_delay_ms`

**What:** If `recovery_step_ms > max_dispatch_delay_ms`, the bootstrap on first capacity error in `AIMDThrottle.on_capacity_error()` would set delay to `recovery_step_ms`, then immediately clamp to `max_dispatch_delay_ms`. Recovery would then set delay to `max - recovery_step`, which could be negative, then clamp to `min`. This means a single success could jump from max to min, bypassing the gradual recovery. This is a degenerate but not broken configuration.

## Verdict

**Status:** SOUND
**Recommended action:** Consider adding a validator or at minimum documentation warning about `recovery_step_ms: 0` disabling recovery. Consider whether the 1-hour default for `max_capacity_retry_seconds` is appropriate or whether a shorter default (e.g., 300 seconds / 5 minutes) would better serve the common case.
**Confidence:** HIGH -- The module is 50 lines of well-validated Pydantic config with straightforward semantics. Test coverage includes edge cases like min > max validation.
