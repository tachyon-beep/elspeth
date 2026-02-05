# Analysis: src/elspeth/testing/chaosllm/config.py

**Lines:** 541
**Role:** Configuration schema and loading for ChaosLLM. Defines Pydantic models for all server configuration (server binding, metrics, response generation, latency, error injection, burst patterns). Provides preset loading from YAML files and a deep-merge precedence system (CLI > config file > preset > defaults).
**Key dependencies:** Imports `yaml`, `pydantic` (BaseModel, Field, validators). Imported by every other module in the chaosllm package (`server.py`, `response_generator.py`, `error_injector.py`, `latency_simulator.py`, `metrics.py`, `cli.py`). Also imported by test fixtures (`tests/fixtures/chaosllm.py`, `tests/stress/conftest.py`).
**Analysis depth:** FULL

## Summary

This file is well-structured with comprehensive Pydantic validation. The configuration models are frozen (immutable), field ranges are validated, and preset loading includes proper error handling. The primary concern is that `ErrorInjectionConfig` does not validate that total error percentages do not exceed 100%, which could lead to unreachable "success" paths. There is also a subtle issue with the `_deep_merge` function that could lose nested config when a non-dict value overwrites a dict. Overall the code is solid. Confidence is HIGH.

## Warnings

### [183-349] No validation that total error percentages do not exceed 100%

**What:** `ErrorInjectionConfig` validates each individual percentage field is between 0 and 100, but there is no model-level validator ensuring the sum of all error percentages stays within a reasonable range. A user could configure `rate_limit_pct=50`, `capacity_529_pct=50`, `internal_error_pct=50`, etc., yielding a combined error probability well over 100%.

**Why it matters:** When using `selection_mode="priority"`, the error injector evaluates each error type independently in order. If the first error type has 100% probability, all subsequent checks are unreachable. This is not a bug in the injector logic (it correctly handles the math), but it means that configuring, say, `connection_failed_pct=80` and `rate_limit_pct=80` will result in ~80% connection failures and ~16% rate limits (80% of the remaining 20%), not the 80/80 split a user might expect.

For `selection_mode="weighted"`, the `_decide_weighted` method in `error_injector.py` handles this correctly by normalizing weights. But in priority mode, the configured percentages are misleading because later error types are shadowed by earlier ones.

A model validator that warns (or at least documents) when total error percentage exceeds 100% would prevent user confusion.

**Evidence:**
```python
# All fields validated individually (0-100) but no cross-field sum check
rate_limit_pct: float = Field(default=0.0, ge=0.0, le=100.0, ...)
capacity_529_pct: float = Field(default=0.0, ge=0.0, le=100.0, ...)
# ... 16 more percentage fields, all independently validated
```

### [473-489] _deep_merge does not protect against type mismatches

**What:** The `_deep_merge` function recursively merges dicts. When a key exists in both `base` and `override`, it only recurses if both values are dicts. If the override has a non-dict value for a key that was a dict in the base, the entire dict subtree is replaced by the scalar value.

**Why it matters:** Consider a scenario where a preset has:
```yaml
error_injection:
  burst:
    enabled: true
    interval_sec: 30
```
And a CLI override inadvertently passes:
```python
cli_overrides = {"error_injection": {"burst": True}}  # Bool instead of dict
```
The deep merge would replace the entire `burst` dict with `True`, which would then fail Pydantic validation. While Pydantic would catch the resulting invalid config, the error message would be confusing ("expected dict, got bool") rather than pointing to the merge issue. This is a defensive concern rather than a bug, since Pydantic provides the safety net.

**Evidence:**
```python
def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value  # Scalar replaces dict -- no type check
    return result
```

### [351-365] parse_range validator silently truncates to int

**What:** The `parse_range` validator converts range values to `int` via `int(v[0])`, which silently truncates floats. A user configuring `retry_after_sec: [1.5, 3.7]` would get `(1, 3)` with no warning.

**Why it matters:** For time-based ranges like `retry_after_sec` and `timeout_sec`, fractional seconds could be intentional. The silent truncation might cause unexpected behavior, especially for `connection_stall_start_sec` where sub-second precision could matter for testing timing-sensitive retry logic.

**Evidence:**
```python
@field_validator("retry_after_sec", "timeout_sec", ..., mode="before")
@classmethod
def parse_range(cls, v: Any) -> tuple[int, int]:
    if isinstance(v, (list, tuple)) and len(v) == 2:
        return (int(v[0]), int(v[1]))  # Silent truncation of floats
    raise ValueError(f"Expected [min, max] range, got {v!r}")
```

However, the `error_injector.py` uses `rng.uniform()` (returns float) for the actual delay values from these ranges, so the int constraint is intentional for Retry-After headers (which per HTTP spec are whole seconds). The concern is limited to the `connection_stall_*` and `slow_response_*` ranges where sub-second precision might be desired.

### [150-180] BurstConfig does not validate duration_sec <= interval_sec

**What:** `BurstConfig` validates that `interval_sec > 0` and `duration_sec > 0`, but does not check that `duration_sec <= interval_sec`. A configuration with `interval_sec=5, duration_sec=30` would mean the system is perpetually in burst mode (since `position_in_interval % 5 < 30` is always true).

**Why it matters:** While this is not technically a bug (the error injector handles it correctly -- the system would just always be in burst), it is almost certainly not what the user intended. A perpetual burst is functionally equivalent to just setting the base error rates to the burst rates, making the burst configuration misleading.

**Evidence:**
```python
class BurstConfig(BaseModel):
    interval_sec: int = Field(default=30, gt=0, ...)
    duration_sec: int = Field(default=5, gt=0, ...)
    # No validator ensuring duration_sec <= interval_sec
```

## Observations

### [14-15] DEFAULT_MEMORY_DB uses SQLite URI mode with shared cache

**What:** `DEFAULT_MEMORY_DB = "file:chaosllm-metrics?mode=memory&cache=shared"` creates a named in-memory database shared across connections. This is appropriate for multi-threaded access within a single process, but the `cache=shared` mode requires all connections to use the same database name.

### [391-427] ChaosLLMConfig is well-structured with frozen models

**What:** All configuration models use `model_config = {"frozen": True}`, making them immutable after construction. This is good practice -- it prevents accidental mutation and makes the config safe to share across threads (important for the multi-worker server).

### [492-541] load_config precedence is clean and correct

**What:** The three-layer precedence system (preset -> config file -> CLI overrides) is implemented clearly with `_deep_merge`. Each layer is applied in order, and the final dict is validated by Pydantic. The `preset_name` is recorded in the final config for observability.

### [437-442] list_presets uses glob on package directory

**What:** `list_presets()` globs `*.yaml` from the `presets/` subdirectory relative to the config module. This is a reasonable approach for a package that ships preset files. The presets directory existence check prevents errors when running from unexpected locations.

### [100-107] PresetResponseConfig file path is a plain string

**What:** `PresetResponseConfig.file` is typed as `str` with a default of `"./responses.jsonl"`. This means the path is relative to the current working directory, not to the config file location. This is standard for CLI tools but worth noting -- users must be aware that relative paths in config files are relative to the CWD, not the config file's directory.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** Add a model validator to `BurstConfig` ensuring `duration_sec <= interval_sec` (or at minimum a warning). Consider adding documentation or a warning validator to `ErrorInjectionConfig` about total error percentage behavior in priority mode. The `_deep_merge` type safety and `parse_range` truncation are minor and can be addressed as part of broader hardening.
**Confidence:** HIGH -- The Pydantic models provide strong static guarantees, and the issues identified are edge cases in configuration validation rather than runtime bugs.
