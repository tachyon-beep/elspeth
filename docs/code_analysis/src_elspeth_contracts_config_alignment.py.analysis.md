# Analysis: src/elspeth/contracts/config/alignment.py

**Lines:** 170
**Role:** Machine-readable documentation of how Settings fields map to Runtime*Config fields. Used by the AST checker (`scripts/check_contracts.py`), alignment tests (`tests/core/test_config_alignment.py`), and human maintainers. Defines four data structures: FIELD_MAPPINGS (renamed fields), SETTINGS_TO_RUNTIME (class pairings), EXEMPT_SETTINGS (Settings that don't need Runtime counterparts), and RUNTIME_TO_SUBSYSTEM (maps Runtime classes to INTERNAL_DEFAULTS subsystem keys).
**Key dependencies:**
- Imports: `typing.Final` only (leaf module -- no elspeth imports)
- Imported by: `contracts.config.__init__`, `scripts/check_contracts.py`, `tests/core/test_config_alignment.py`
**Analysis depth:** FULL

## Summary

This file is well-designed pure data -- it has no runtime behavior, only documentation structures and simple lookup functions. The data is accurate when cross-referenced against the actual code in `runtime.py` and `core/config.py`. However, there are two structural gaps in the documentation that could allow future field orphaning to go undetected, and the `RUNTIME_TO_SUBSYSTEM` mapping is incomplete.

## Warnings

### [112-115] RUNTIME_TO_SUBSYSTEM is incomplete -- missing RuntimeTelemetryConfig

**What:** `RUNTIME_TO_SUBSYSTEM` only maps `RuntimeRetryConfig` to the `"retry"` subsystem. However, `INTERNAL_DEFAULTS` in `defaults.py` also has a `"telemetry"` subsystem (with `queue_size: 1000`). The comment on line 114 says `# Future: "RuntimeCheckpointConfig": "checkpoint"` but does not mention telemetry at all.

**Why it matters:** The AST checker (`check_hardcode_documentation()`) uses `RUNTIME_TO_SUBSYSTEM` to determine which `INTERNAL_DEFAULTS` subsystem to check for hardcoded literals. If `RuntimeTelemetryConfig` ever uses a plain literal in its `from_settings()` method (rather than referencing `INTERNAL_DEFAULTS` directly), the AST checker would flag it as having "no subsystem mapping" rather than checking against `INTERNAL_DEFAULTS["telemetry"]`. Currently, `RuntimeTelemetryConfig.from_settings()` does not use any hardcoded literals (it pulls all values from settings), so there is no active bug. But the mapping gap means the safety net is incomplete.

**Evidence:**
```python
RUNTIME_TO_SUBSYSTEM: Final[dict[str, str]] = {
    "RuntimeRetryConfig": "retry",
    # Future: "RuntimeCheckpointConfig": "checkpoint",
    # Missing: "RuntimeTelemetryConfig": "telemetry"
}
```
Meanwhile in defaults.py:
```python
INTERNAL_DEFAULTS = {
    "retry": {"jitter": 1.0},
    "telemetry": {"queue_size": 1000},  # Not referenced in RUNTIME_TO_SUBSYSTEM
}
```

### [38-43] FIELD_MAPPINGS for TelemetrySettings is incomplete

**What:** `FIELD_MAPPINGS["TelemetrySettings"]` documents `{"exporters": "exporter_configs"}` as the only renamed field. However, the `granularity` and `backpressure_mode` fields undergo type transformations in `from_settings()` (string to enum). While these are not name renames (the field names stay the same), the absence of documentation about type transformation could mislead maintainers.

**Why it matters:** The FIELD_MAPPINGS docstring says "Only list fields that have DIFFERENT names." This is correct -- `granularity` and `backpressure_mode` keep the same names. However, these fields have a significant semantic transformation (string literal to Enum), and `frequency` in `CheckpointSettings` has a similar transformation (Literal to int) that is also undocumented here. A future maintainer might expect FIELD_MAPPINGS to be the complete record of all non-trivial mappings.

This is a documentation clarity issue, not a bug. The AST checker correctly handles type transformations separately from name renames.

### [75-96] EXEMPT_SETTINGS may need periodic review for completeness

**What:** `EXEMPT_SETTINGS` is a manually maintained set of Settings class names that don't need Runtime counterparts. If a new Settings class is added to `core/config.py` and is not added to either `SETTINGS_TO_RUNTIME` or `EXEMPT_SETTINGS`, the AST checker and alignment tests will catch it.

**Why it matters:** This is the intended design and works correctly -- the `check_settings_alignment()` function in `check_contracts.py` and the `test_settings_to_runtime_mapping_is_complete()` test verify completeness. The concern is that the categories in the comments (Plugin option containers, Config-driven DAG construction, Infrastructure, Nested, Top-level) are not enforced programmatically. A Settings class could be added to `EXEMPT_SETTINGS` with the wrong rationale, and nothing would catch it. This is a minor governance concern.

## Observations

### get_runtime_field_name and get_settings_field_name are correct and symmetric

The forward and reverse lookup functions are simple and correct. `get_runtime_field_name` looks up the mapping and falls back to identity. `get_settings_field_name` does a reverse search through the mapping dict. For the small number of renamed fields (currently 3 across 2 Settings classes), the linear scan in the reverse lookup is negligible.

### CheckpointSettings frequency transformation is not in FIELD_MAPPINGS

`CheckpointSettings.frequency` (Literal["every_row", "every_n", "aggregation_only"]) maps to `RuntimeCheckpointConfig.frequency` (int). The field name is the same, so it correctly does not appear in `FIELD_MAPPINGS`. However, this is one of the most complex transformations in the config layer, and it is only documented in `runtime.py`'s docstring. A "type transformation" registry (separate from name renames) could improve traceability.

### Pure data module with no elspeth imports -- true leaf module

This file imports only `typing.Final`. It has zero coupling to the rest of the codebase at import time. The AST checker and tests import it, but it never imports from `core` or `engine`. This is exactly right for a documentation/metadata module.

### SETTINGS_TO_RUNTIME is accurate

Cross-referencing with `core/config.py` and `contracts/config/runtime.py`:
- RetrySettings -> RuntimeRetryConfig: Correct (verified from_settings exists)
- RateLimitSettings -> RuntimeRateLimitConfig: Correct
- ConcurrencySettings -> RuntimeConcurrencyConfig: Correct
- CheckpointSettings -> RuntimeCheckpointConfig: Correct
- TelemetrySettings -> RuntimeTelemetryConfig: Correct

All five pairings are accurate.

## Verdict

**Status:** SOUND
**Recommended action:**
1. Add `"RuntimeTelemetryConfig": "telemetry"` to `RUNTIME_TO_SUBSYSTEM` to close the safety net gap, even though there are no active violations currently.
2. Consider adding a comment section or separate data structure documenting type transformations (frequency Literal->int, granularity string->enum, backpressure_mode string->enum) for completeness.

**Confidence:** HIGH -- This file is pure data with simple lookup functions. Cross-referenced against all consuming code (AST checker, alignment tests, runtime.py) to verify accuracy.
