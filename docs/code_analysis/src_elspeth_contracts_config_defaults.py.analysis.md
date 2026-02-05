# Analysis: src/elspeth/contracts/config/defaults.py

**Lines:** 98
**Role:** Default value registries for runtime configuration. Contains two data structures: INTERNAL_DEFAULTS (hardcoded implementation values not exposed in user Settings) and POLICY_DEFAULTS (fallback values for plugin RetryPolicy dicts). Also provides accessor functions `get_internal_default()` and `get_policy_default()`.
**Key dependencies:**
- Imports: `typing.Final` only (leaf module)
- Imported by: `contracts.config.runtime` (INTERNAL_DEFAULTS, POLICY_DEFAULTS), `contracts.config.__init__`, `scripts/check_contracts.py`
**Analysis depth:** FULL

## Summary

This is a small, focused data module with no logic beyond simple dict lookups. The data is accurate when cross-referenced against `runtime.py` and `engine/retry.py`. The POLICY_DEFAULTS note about duplication from engine/retry.py is a concern worth investigating, and the INTERNAL_DEFAULTS telemetry entry `queue_size` is defined here but not referenced from `RuntimeTelemetryConfig`, making it orphaned documentation. No critical issues.

## Warnings

### [57-58] POLICY_DEFAULTS note about duplication from engine/retry.py

**What:** The comment on lines 57-58 says: "NOTE: This is duplicated from engine/retry.py to avoid circular imports. The authoritative source is here; engine/retry.py should import from here."

**Why it matters:** I checked `engine/retry.py` and it does NOT define its own POLICY_DEFAULTS -- it imports `RuntimeRetryProtocol` from `contracts.config` and the `RetryManager` only uses the protocol. The comment is stale -- the duplication it warns about has already been resolved. The comment should be removed to avoid confusing future maintainers who might search engine/retry.py for a second copy of these defaults and find nothing.

**Evidence:** `engine/retry.py` imports from `elspeth.contracts.config` (line 38) and does not define any default constants. The authoritative source is already `defaults.py` as intended.

### [40-46] INTERNAL_DEFAULTS["telemetry"]["queue_size"] is defined but not consumed by RuntimeTelemetryConfig

**What:** `INTERNAL_DEFAULTS` includes `"telemetry": {"queue_size": 1000}`, but `RuntimeTelemetryConfig` does not have a `queue_size` field and its `from_settings()` method does not reference this value.

**Why it matters:** This is orphaned documentation. The value is documented here for transparency (per the module docstring), but it has no mechanical connection to the code that actually uses it. If the actual queue size in the telemetry implementation changes from 1000 to something else, this documentation would silently become stale. Furthermore, `RUNTIME_TO_SUBSYSTEM` in `alignment.py` does not have an entry for `RuntimeTelemetryConfig`, so the AST checker cannot verify this value.

To be clear: this is not a bug -- `queue_size` is correctly described as an "internal implementation detail" that is not user-configurable. The concern is that documenting it here without a mechanical connection to the code creates a maintenance burden with no verification.

**Evidence:**
```python
INTERNAL_DEFAULTS = {
    "telemetry": {
        "queue_size": 1000,  # Documented but not consumed by RuntimeTelemetryConfig
    },
}
```

### [60-66] POLICY_DEFAULTS includes "jitter" but jitter is internal-only

**What:** `POLICY_DEFAULTS` includes `"jitter": 1.0` with the comment "Internal default, included for policy completeness." The `RetryPolicy` TypedDict in `contracts/engine.py` also includes `jitter: float`. This means plugins CAN override jitter via their retry policy, even though jitter is documented as "internal" in `RuntimeRetryConfig`.

**Why it matters:** There is a conceptual tension: `RuntimeRetryConfig` docstring says jitter is "INTERNAL - hardcoded to 1.0, not from Settings" and `INTERNAL_DEFAULTS` documents it as internal. But `from_policy()` in `runtime.py` allows plugins to override jitter via their RetryPolicy dict. These two statements contradict each other. Either jitter is internal (and should not be overridable via policy) or it is configurable per-plugin (and should not be in INTERNAL_DEFAULTS).

In practice, this works fine -- plugins that don't specify jitter get the default 1.0, and plugins that do specify it get their value. But the documentation is misleading about the field's actual configurability.

**Evidence:**
```python
# defaults.py says "internal default"
INTERNAL_DEFAULTS = {"retry": {"jitter": 1.0}}

# But POLICY_DEFAULTS allows override
POLICY_DEFAULTS = {"jitter": 1.0}

# And from_policy() reads it from policy dict
jitter = _validate_float_field("jitter", full["jitter"])  # full includes policy override
```

## Observations

### POLICY_DEFAULTS values match RetrySettings defaults

Cross-referencing with `core/config.py`:
- `max_attempts: 3` matches `RetrySettings(max_attempts=3)` -- correct
- `base_delay: 1.0` matches `RetrySettings(initial_delay_seconds=1.0)` -- correct (name mapping)
- `max_delay: 60.0` matches `RetrySettings(max_delay_seconds=60.0)` -- correct (name mapping)
- `exponential_base: 2.0` matches `RetrySettings(exponential_base=2.0)` -- correct

### POLICY_DEFAULTS uses runtime field names, not settings field names

The keys in `POLICY_DEFAULTS` use `base_delay` and `max_delay` (runtime names) rather than `initial_delay_seconds` and `max_delay_seconds` (settings names). This is correct because `from_policy()` constructs `RuntimeRetryConfig` directly using these field names.

### get_internal_default() and get_policy_default() are thin wrappers

These functions add no logic beyond dict lookup. They exist for discoverability and to provide a clean API. The docstrings correctly document that KeyError is raised for missing fields (which would indicate a bug, not user error). This aligns with the Tier 1 trust model.

### Type annotation for INTERNAL_DEFAULTS is restrictive

`INTERNAL_DEFAULTS: Final[dict[str, dict[str, int | float | bool | str]]]` restricts values to primitive types. This is intentional -- internal defaults should be simple values. If a future subsystem needs complex defaults (e.g., a dict or list), the type annotation would need updating. This is fine as-is.

## Verdict

**Status:** SOUND
**Recommended action:**
1. Remove the stale comment about duplication from engine/retry.py (lines 57-58).
2. Resolve the jitter documentation inconsistency -- either document that jitter IS overridable via plugin policy (and update INTERNAL_DEFAULTS comment), or remove jitter from POLICY_DEFAULTS and RetryPolicy (and hardcode it in from_policy()).
3. Consider whether `INTERNAL_DEFAULTS["telemetry"]["queue_size"]` should be mechanically connected to the telemetry implementation or removed.

**Confidence:** HIGH -- Small file, fully cross-referenced against consumers and producers.
