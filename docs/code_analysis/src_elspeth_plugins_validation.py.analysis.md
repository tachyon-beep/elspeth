# Analysis: src/elspeth/plugins/validation.py

**Lines:** 355
**Role:** Plugin configuration validation subsystem. Validates plugin configurations BEFORE instantiation by delegating to Pydantic config models for each plugin type. Provides structured error reporting rather than exceptions. Contains a hardcoded registry mapping plugin type names to their config classes.
**Key dependencies:** Imports from `pydantic` (ValidationError), `elspeth.plugins.config_base` (PluginConfig, TYPE_CHECKING only), `elspeth.contracts.schema` (SchemaConfig). Imported by `manager.py`. Conditionally imports all plugin config classes (CSVSourceConfig, FieldMapperConfig, etc.) in `_get_*_config_model()` methods.
**Analysis depth:** FULL

## Summary

This file has a significant architectural problem: it maintains a hardcoded registry of plugin type names to config classes that must be manually synchronized with the plugin discovery system. Several recently added plugins are missing from this registry, meaning their configurations cannot be validated through the `PluginManager.create_*()` path. The duplicate validation code across four `validate_*_config` methods is also a maintenance concern.

## Critical Findings

### [235-295] Hardcoded transform registry is incomplete -- missing 4 transform plugins

**What:** The `_get_transform_config_model()` method maps transform type names to their Pydantic config classes via a hardcoded if/elif chain. This registry is missing at least four transform plugins that exist in the codebase:

1. `openrouter_batch_llm` (class `OpenRouterBatchConfig` in `llm/openrouter_batch.py`)
2. `openrouter_multi_query_llm` (class `OpenRouterMultiQueryConfig` in `llm/openrouter_multi_query.py`)
3. `azure_multi_query_llm` -- WAIT, this IS present at line 286. Let me re-check. Actually `azure_multi_query_llm` is mapped on line 286 but the name used in validation is `"azure_multi_query_llm"` while discovery finds it by its `name` class attribute which is also `"azure_multi_query_llm"`, so that one is correct.
4. `web_scrape` (class `WebScrapeConfig` in `transforms/web_scrape.py`)

When any of these plugin types is passed to `validate_transform_config()`, the `_get_transform_config_model()` method will hit the `else` clause at line 294 and raise `ValueError(f"Unknown transform type: {transform_type}")`. This means `PluginManager.create_transform()` will crash when asked to create these plugins.

**Why it matters:** If the `create_transform()` path is used (rather than direct plugin instantiation), these plugins cannot be created. Whether this is a production issue depends on whether the `create_transform()` path is used for these plugins. But the registry being out of sync with discovery is a latent bug that will bite eventually -- any code path that goes through validation before instantiation will fail for these plugins.

**Evidence:**
```python
# Transforms in the registry (lines 242-294):
# passthrough, field_mapper, json_explode, keyword_filter, truncate,
# batch_replicate, batch_stats, azure_content_safety, azure_prompt_shield,
# azure_llm, azure_batch_llm, azure_multi_query_llm, openrouter_llm

# Transforms discovered by discovery.py but NOT in registry:
# openrouter_batch_llm, openrouter_multi_query_llm, web_scrape
```

### [297-304] Gate validation always raises -- no gate config models exist

**What:** `_get_gate_config_model()` immediately raises `ValueError(f"Unknown gate type: {gate_type}")` for any input. The comment says "No gate plugins exist yet in codebase."

**Why it matters:** While this matches the current state (gates are config-driven system operations, not plugins), the `PluginManager` class exposes `create_gate()` (line 279 of manager.py) and `validate_gate_config()` (line 141) as public methods. Additionally, `_refresh_caches()` in manager.py iterates over `elspeth_get_gates()` hooks (line 111) and stores gates in `self._gates`. This creates a misleading API surface: gates appear to be first-class plugin types with validation and creation support, but calling these methods always fails. Per the No Legacy Code Policy, this dead code should be removed rather than left as a placeholder.

**Evidence:**
```python
def _get_gate_config_model(self, gate_type: str) -> type["PluginConfig"]:
    # No gate plugins exist yet in codebase
    raise ValueError(f"Unknown gate type: {gate_type}")
```

## Warnings

### [51-199] Four nearly identical validate_*_config methods with duplicated error handling

**What:** `validate_source_config`, `validate_transform_config`, `validate_gate_config`, and `validate_sink_config` all have identical bodies except for the model-lookup method they call. Each one duplicates the same try/except pattern for catching both `PydanticValidationError` and wrapped `PluginConfigError`.

**Why it matters:** This is a maintenance burden. When the error handling pattern needs to change, it must be changed in four places. A single generic `_validate_config()` method that takes a config model resolver would eliminate the duplication.

**Evidence:** Lines 51-83, 111-139, 141-169, 171-199 are structurally identical, differing only in:
- The method name
- The call to `self._get_{type}_config_model(type_name)`

### [76-83, 134-139, 166-169, 196-199] Broad Exception catch may mask bugs

**What:** Each `validate_*_config` method catches `Exception` and checks if the cause is a wrapped `PydanticValidationError`. If the cause is NOT a `PydanticValidationError`, it re-raises. While the re-raise is correct, the pattern of catching the broad `Exception` class means any unexpected error from `from_dict()` that happens to have a `PydanticValidationError` as its `__cause__` will be silently converted to a validation error list.

**Why it matters:** If `from_dict()` has a bug that raises a non-`PluginConfigError` exception whose `__cause__` happens to be a `PydanticValidationError`, this would be caught and treated as user-facing validation output rather than crashing as a system bug. The probability is low but the pattern is fragile.

**Evidence:**
```python
except Exception as e:
    # from_dict wraps ValidationError in PluginConfigError
    if e.__cause__ and isinstance(e.__cause__, PydanticValidationError):
        return self._extract_errors(e.__cause__)
    raise  # Re-raise if not a wrapped validation error
```

### [85-109, 306-330] Hardcoded source and sink registries may also go stale

**What:** Like the transform registry, `_get_source_config_model()` and `_get_sink_config_model()` use hardcoded if/elif chains. Currently these appear to be complete (csv, json, azure_blob, null for sources; csv, json, database, azure_blob for sinks), but they are structurally susceptible to the same drift problem seen in the transform registry.

**Why it matters:** As new source or sink plugins are added, they must be manually added to these registries. There is no mechanism to detect when the registries fall out of sync with discovery.

## Observations

### [332-355] _extract_errors is well-implemented

The Pydantic error extraction correctly joins location tuples into dot-separated paths and extracts the `input` field for debugging. No issues found.

### [201-233] validate_schema_config correctly limits exception scope

The `validate_schema_config` method only catches `ValueError` (which is what `SchemaConfig.from_dict()` documents as its error type) and explicitly does NOT have a catch-all Exception handler. The comment (lines 229-233) explains why, following the CLAUDE.md principle that unexpected exceptions from our own code should crash.

### [29-42] ValidationError dataclass is appropriately simple

The structured validation error type provides clear field-level error reporting. The `value: Any` field stores the invalid value for debugging, which is useful for operator-facing error messages.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** (1) Add missing transforms to `_get_transform_config_model()`: `openrouter_batch_llm`, `openrouter_multi_query_llm`, `web_scrape`. (2) Consider refactoring the four `validate_*_config` methods into a single generic method to eliminate duplication. (3) Either remove the gate validation/creation dead code or add a comment explaining why it is retained. (4) Consider whether the hardcoded registries should be replaced with a discovery-driven approach (e.g., each plugin config class declares a `plugin_name` that the validator can look up dynamically).
**Confidence:** HIGH -- the missing transforms are verifiable by comparing the `_get_transform_config_model` if/elif chain against the `name` attributes of all `BaseTransform` subclasses in the codebase.
