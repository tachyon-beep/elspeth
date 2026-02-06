# Analysis: src/elspeth/plugins/manager.py

**Lines:** 331
**Role:** Plugin lifecycle manager. Manages plugin discovery, registration, and lookup via pluggy. Provides factory methods (`create_source`, `create_transform`, `create_gate`, `create_sink`) that validate configuration before instantiating plugins. Maintains internal caches mapping plugin names to their classes.
**Key dependencies:** Imports `pluggy`, `elspeth.plugins.hookspecs` (PROJECT_NAME, hookspec classes), `elspeth.plugins.protocols` (all protocol types), `elspeth.plugins.validation` (PluginConfigValidator). Deferred import of `discovery.py` in `register_builtin_plugins()`. Imported by `plugins/__init__.py`, `cli.py`, test fixtures, and integration tests.
**Analysis depth:** FULL

## Summary

The PluginManager is well-structured and follows sensible patterns for registration and lookup. The main concerns are: (1) double validation -- configs are validated once by the validator and then again during plugin `__init__`, which calls `from_dict` a second time; (2) gate-related dead code that should be removed per No Legacy Code Policy; (3) `_refresh_caches` is called on every `register()` call, which scales poorly if many plugins are registered incrementally.

## Critical Findings

### [225-250, 252-277] Double parsing of plugin configuration

**What:** The `create_source()` and `create_transform()` methods (and `create_gate()` / `create_sink()`) first validate the config dict through `PluginConfigValidator` (which calls `ConfigClass.from_dict(config)` internally to validate), then pass the raw `config` dict to the plugin class constructor: `plugin_cls(config)`. The plugin constructor then calls `from_dict(config)` again to build its own typed config object.

This means every config dict is parsed and validated twice: once by the validator (result discarded), and once by the plugin constructor.

**Why it matters:** This is not a correctness bug -- both passes should produce the same result. However, it is wasteful and creates a subtle coupling risk: if the validator's registry maps a type name to a different config class than the plugin's own constructor uses, the validator could pass a config that the constructor rejects (or vice versa). For example, if validation.py maps `"azure_llm"` to `AzureOpenAIConfig` but the plugin's `__init__` uses a different config class (perhaps through inheritance), the two validation passes could diverge silently.

**Evidence:**
```python
# manager.py line 239: Validates via PluginConfigValidator
errors = self._validator.validate_source_config(source_type, config)
# ... error handling ...

# manager.py line 250: Passes raw dict to plugin constructor, which validates again
return plugin_cls(config)
```

## Warnings

### [111-116] Gate hook iteration is dead code

**What:** `_refresh_caches()` iterates over `self._pm.hook.elspeth_get_gates()` (line 111) and populates `self._gates`. However, `register_builtin_plugins()` never registers any gate hookimpl (gates are explicitly excluded per the comment on line 70). Since no gate hookimpls are ever registered, this loop always produces an empty dict.

Combined with the gate-related methods (`get_gates()`, `get_gate_by_name()`, `create_gate()`), this constitutes dead code that gives the appearance of gate plugin support. This is a known issue (documented in `docs/bugs/open/plugins-transforms/P2-2026-02-05-gate-hook-spec-still-advertised-after-gate-pl.md`).

**Why it matters:** Per the No Legacy Code Policy, this dead code should be removed. It misleads developers into thinking gate plugins are supported through the plugin system, when in fact gates are config-driven system operations handled by the engine.

**Evidence:**
```python
# Line 70: Gates explicitly excluded from registration
# (gates excluded - they're system operations, not plugins)

# Line 111-116: But gate hooks are still iterated
for gates in self._pm.hook.elspeth_get_gates():
    for cls in gates:
        name = cls.name
        if name in new_gates:
            raise ValueError(...)
        new_gates[name] = cls
```

### [84-129] _refresh_caches rebuilds entire cache on every register() call

**What:** Every call to `register()` triggers `_refresh_caches()`, which re-iterates ALL hooks for ALL plugin types (sources, transforms, gates, sinks) and rebuilds the entire cache from scratch.

**Why it matters:** During startup, `register_builtin_plugins()` calls `register()` three times (once each for sources, transforms, sinks dynamic hookimpls at lines 71-73). Each call triggers a full cache rebuild. While the current plugin count is small (~20 total), this O(n*k) pattern (n plugins, k register calls) is worth noting. If `register()` were called many times (e.g., for external plugin packs), this would become wasteful.

Additionally, the method creates entirely new dicts (`new_sources`, etc.) and then assigns them to the instance attributes. During the brief window between clearing old caches and assigning new ones, there is no atomicity concern in single-threaded code, but if the manager were ever used concurrently, this pattern would be unsafe.

**Evidence:**
```python
def register(self, plugin: Any) -> None:
    self._pm.register(plugin)
    self._refresh_caches()  # Full rebuild every time

def _refresh_caches(self) -> None:
    new_sources: dict[str, type[SourceProtocol]] = {}
    # ... iterates ALL hooks for ALL types ...
    self._sources = new_sources  # Atomic assignment, but full rebuild
```

### [225-331] create_* methods use PluginConfigValidator which has incomplete registry

**What:** All `create_*` methods delegate validation to `PluginConfigValidator`, which (as documented in the validation.py analysis) has a hardcoded registry that is missing several plugins. If `create_transform("web_scrape", config)` is called, the validator will raise `ValueError("Unknown transform type: web_scrape")`.

**Why it matters:** This means the factory path (`create_transform`) is broken for any plugin not in the validator's registry. This is a transitive bug from validation.py but has direct impact on the manager's public API.

**Evidence:**
```python
def create_transform(self, transform_type: str, config: dict[str, Any]) -> TransformProtocol:
    errors = self._validator.validate_transform_config(transform_type, config)
    # If transform_type is "web_scrape", this raises ValueError before validation even happens
```

## Observations

### [37-52] Clean initialization with proper hookspec registration

The constructor correctly registers all three hookspec classes and initializes empty caches. The separation of `_sources`, `_transforms`, `_gates`, `_sinks` as typed dicts provides clear type safety.

### [96-129] Duplicate detection in _refresh_caches is thorough

The cache refresh correctly detects duplicate plugin names within each type and provides helpful error messages that name both the conflicting class and the existing registration.

### [150-221] Lookup methods provide helpful error messages

All `get_*_by_name()` methods include the list of available plugins in the error message, which aids debugging configuration errors. This is a good pattern.

### [54-73] register_builtin_plugins follows deferred import pattern

The method correctly uses deferred imports for `discovery.py` functions, avoiding circular import issues. The dynamic hookimpl creation via `create_dynamic_hookimpl` is a clean pattern for bridging file-scan discovery with pluggy's registration model.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** (1) Remove gate-related dead code (get_gates, get_gate_by_name, create_gate, and gate iteration in _refresh_caches). (2) Address the double-validation issue by either passing the already-validated config object to the plugin constructor or removing the validator step from create_* methods. (3) Fix the transitive incomplete-registry bug by updating validation.py's registries.
**Confidence:** HIGH -- the double-validation and dead-code issues are clearly visible in the code. The incomplete-registry issue is a transitive finding from validation.py with clear impact on manager.py's public API.
