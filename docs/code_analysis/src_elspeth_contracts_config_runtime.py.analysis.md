# Analysis: src/elspeth/contracts/config/runtime.py

**Lines:** 598
**Role:** Runtime*Config frozen dataclasses with from_settings() factory methods. Converts Pydantic Settings models into immutable runtime config objects. Also provides from_policy() for plugin-level retry overrides and default()/no_retry() convenience factories.
**Key dependencies:**
- Imports: `contracts.config.defaults` (INTERNAL_DEFAULTS, POLICY_DEFAULTS), `contracts.engine` (RetryPolicy), `contracts.enums` (BackpressureMode, TelemetryGranularity, _IMPLEMENTED_BACKPRESSURE_MODES)
- Lazy imports (in from_settings()): `core.config` (RetrySettings, RateLimitSettings, etc.)
- Imported by: `contracts.config.__init__`, `engine.retry`, `engine.orchestrator.core`, `cli.py`, `core.rate_limit.registry`, `telemetry.factory`
**Analysis depth:** FULL

## Summary

This file is well-structured and carefully designed. The frozen dataclasses, explicit factory methods, and detailed docstrings demonstrate strong engineering discipline. However, there are several issues ranging from a potential silent data corruption bug in float validation (NaN/Infinity passthrough) to missing validation in the `from_settings` path and a mutable dict reference in a frozen dataclass. The clamping behavior in `from_policy` also silently alters user intent without any warning, which could confuse operators. Overall, the file is SOUND with a few items that need attention.

## Critical Findings

### [74-75] _validate_float_field passes through NaN and Infinity

**What:** The `_validate_float_field` function checks `isinstance(value, float)` on line 107-108 and returns it directly. `float('nan')` and `float('inf')` are both `isinstance(x, float) == True`. Neither the validator nor the `__post_init__` methods on the dataclasses reject these values.

**Why it matters:** Per CLAUDE.md, NaN and Infinity are strictly rejected in canonical JSON. If a plugin policy dict contains `{"base_delay": float('nan')}`, it would pass through `_validate_float_field`, pass the `max(0.01, nan)` clamp (which returns `nan` because all comparisons with NaN are false), and become a `RuntimeRetryConfig` with `base_delay=nan`. This would then propagate to tenacity's `wait_exponential_jitter()`, causing unpredictable retry behavior. Similarly, `float('inf')` would bypass max_delay clamping since `max(0.1, inf) == inf`, creating an effectively infinite wait.

**Evidence:**
```python
# Line 107-108
if isinstance(value, float) and not isinstance(value, bool):
    return value  # NaN and Infinity pass through unchecked!
```
```python
# Line 258 - max() with NaN always returns NaN
max_delay=max(0.1, max_delay_val),  # max(0.1, nan) == nan
```

The `_validate_int_field` function has the same pattern on line 74 for float-to-int conversion: `int(float('nan'))` raises ValueError (caught), but `int(float('inf'))` raises OverflowError (NOT caught). This is a secondary failure mode.

### [288] Mutable dict reference in frozen RuntimeRateLimitConfig.services

**What:** The `services` field is typed as `dict[str, "ServiceRateLimit"]`. While the dataclass is `frozen=True`, this only prevents reassigning the attribute. The dict itself is mutable. In `from_settings()` at line 344, `dict(settings.services)` creates a shallow copy, but the dict values are `ServiceRateLimit` Pydantic models (frozen, so safe). However, nothing prevents external code from calling `config.services["new_key"] = something` after construction.

**Why it matters:** The frozen dataclass contract implies immutability, but the mutable dict breaks this. If any consumer adds or removes entries from `config.services` after construction, the original config object is silently modified. This is particularly dangerous for the audit trail if the config snapshot is taken before and after mutation. For a frozen dataclass with slots, this is a contract smell rather than an active bug, but it violates the stated design principle of immutability.

**Evidence:**
```python
@dataclass(frozen=True, slots=True)
class RuntimeRateLimitConfig:
    services: dict[str, "ServiceRateLimit"]  # Mutable container in frozen dataclass
```

## Warnings

### [254-261] Silent clamping in from_policy() alters user configuration without notification

**What:** `from_policy()` clamps values to safe minimums: `max(1, max_attempts)`, `max(0.01, base_delay)`, `max(0.1, max_delay)`, `max(0.0, jitter)`, `max(1.01, exponential_base)`. If a plugin provides `{"max_attempts": -5}`, it silently becomes 1. No warning is logged, no audit event is emitted.

**Why it matters:** Per ELSPETH's auditability standard, the audit trail must explain every decision. If a plugin's retry policy specifies `max_attempts: 0` (intending no retries), it silently becomes 1 (one attempt). The operator seeing retries would have no indication that the policy was modified. This is particularly problematic because `from_policy(None)` returns `no_retry()` (which has `max_attempts=1`), but `from_policy({"max_attempts": 0})` also returns `max_attempts=1` via clamping -- two different intents, same result, no way to distinguish.

**Evidence:**
```python
return cls(
    max_attempts=max(1, max_attempts),      # 0 or negative -> 1 (silently)
    base_delay=max(0.01, base_delay),       # 0 -> 0.01 (silently)
    max_delay=max(0.1, max_delay_val),      # 0 -> 0.1 (silently)
    jitter=max(0.0, jitter),               # negative -> 0 (silently)
    exponential_base=max(1.01, exponential_base),  # 1.0 -> 1.01 (silently)
)
```

### [260] exponential_base clamp minimum of 1.01 is inconsistent with RetrySettings validation

**What:** `from_policy()` clamps `exponential_base` to `min=1.01`, but `RetrySettings` in `core/config.py` validates `gt=1.0` (strictly greater than 1.0). This means `from_settings()` can produce `exponential_base=1.001` (valid per Pydantic), but `from_policy()` would clamp `1.001` to `1.01`.

**Why it matters:** Two different entry paths produce different minimum values for the same field. A plugin specifying `exponential_base: 1.005` via policy gets clamped to `1.01`, while the same value via settings YAML passes through unchanged. This inconsistency could lead to confusion when debugging retry behavior.

**Evidence:**
```python
# core/config.py line 744
exponential_base: float = Field(default=2.0, gt=1.0, ...)  # Accepts 1.001

# runtime.py line 260
exponential_base=max(1.01, exponential_base),  # Clamps 1.001 -> 1.01
```

### [306-309] Lazy import of ServiceRateLimit inside get_service_config creates coupling

**What:** `RuntimeRateLimitConfig.get_service_config()` lazily imports `ServiceRateLimit` from `elspeth.core.config` to construct a default. This is a runtime import inside a method that could be called frequently (once per service lookup).

**Why it matters:** While Python caches module imports after the first call (making subsequent imports cheap), this pattern is fragile. If `core.config` evolves to have import-time side effects or the import path changes, this method breaks at runtime rather than at module load time. The comment explains the leaf boundary motivation, which is valid, but the method body creates the coupling it was trying to avoid. Additionally, the `services` field already holds `ServiceRateLimit` objects, so the type is already reachable at runtime.

### [581-582] Enum parsing uses .lower() but doesn't handle empty strings

**What:** `RuntimeTelemetryConfig.from_settings()` calls `settings.granularity.lower()` and `settings.backpressure_mode.lower()` before parsing to enum. If these values are empty strings, `TelemetryGranularity("")` would raise a ValueError with an opaque error message.

**Why it matters:** While Pydantic validation should catch empty strings (the field is `Literal["lifecycle", "rows", "full"]`), if the Settings object is constructed programmatically (not via YAML), an empty string could slip through. The error message from the enum constructor would be unhelpful compared to a deliberate validation.

## Observations

### [43-49] _merge_policy_with_defaults uses dict unpacking -- clear and correct

The `{**POLICY_DEFAULTS, **policy}` pattern is idiomatic and correct for merging with override precedence. The `RetryPolicy` TypedDict with `total=False` means all fields are optional, so missing fields correctly fall back to `POLICY_DEFAULTS`.

### [155-158] RuntimeRetryConfig.__post_init__ only validates max_attempts

The `__post_init__` validates `max_attempts >= 1` but does not validate `base_delay > 0`, `max_delay > 0`, `exponential_base > 1.0`, or `jitter >= 0`. The `from_policy()` path handles this via clamping, and `from_settings()` relies on Pydantic validation upstream. However, direct construction (used in tests and by `no_retry()`) has no such guard. If someone constructs `RuntimeRetryConfig(max_attempts=3, base_delay=-1.0, ...)`, the negative base_delay would cause tenacity to behave unexpectedly.

### [590] ExporterConfig options dict is copied via `dict(exp.options)`

In `from_settings()` for telemetry, `dict(exp.options)` creates a shallow copy of each exporter's options. If options contain nested mutable structures, modifications to the original settings would not affect the runtime config (good), but modifications to nested objects within the copy would still be shared (minor concern).

### [344] from_settings copies services dict but not deeply

`dict(settings.services)` creates a shallow copy. Since `ServiceRateLimit` is a frozen Pydantic model, this is safe -- the values are immutable. This is correct.

### Documentation quality is excellent

Every class has a comprehensive docstring explaining field origins, protocol coverage, and design rationale. The `from_settings()` methods document field mappings explicitly. This is exemplary documentation for a configuration bridge layer.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:**
1. Add NaN/Infinity rejection to `_validate_float_field` (critical -- this can cause silent data corruption in retry timing).
2. Consider adding `__post_init__` validation for all float fields in `RuntimeRetryConfig` (base_delay, max_delay, exponential_base) to catch invalid direct construction.
3. Consider using `MappingProxyType` or `frozenset`-based pattern for the `services` dict in `RuntimeRateLimitConfig` to enforce true immutability.
4. Consider logging a warning when `from_policy()` clamps values, so operators can see that configuration was modified.

**Confidence:** HIGH -- Full analysis of all code paths, cross-referenced with consumers in engine/retry.py, cli.py, and the AST checker. The NaN/Infinity issue is demonstrable with `float('nan')`.
