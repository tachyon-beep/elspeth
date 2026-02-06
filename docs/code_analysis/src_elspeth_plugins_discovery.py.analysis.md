# Analysis: src/elspeth/plugins/discovery.py

**Lines:** 281
**Role:** Dynamic plugin discovery by filesystem scanning. Scans configured plugin directories for Python files, imports them, and finds classes that inherit from base classes (BaseSource, BaseTransform, BaseSink), have a `name` attribute, and are not abstract. Also provides `create_dynamic_hookimpl()` for bridging discovered plugins into pluggy's registration model, and `get_plugin_description()` for CLI display.
**Key dependencies:** Imports `importlib.util`, `inspect`, `sys`, `pathlib.Path`, `logging`. Deferred import of `elspeth.plugins.base` (BaseSource, BaseTransform, BaseSink) in `_get_base_classes()`. Deferred import of `elspeth.plugins.hookspecs` (hookimpl) in `create_dynamic_hookimpl()`. Imported by `manager.py` and `cli.py`.
**Analysis depth:** FULL

## Summary

The discovery module is well-designed for its purpose, with proper handling of module naming collisions, Python 3.13+ dataclass compatibility, and clean separation between scanning and hookimpl generation. The primary concern is the `EXCLUDED_FILES` set acting as a fragile deny-list that can silently prevent plugin discovery if a new plugin file has a name that collides with an excluded name. There is also a subtle issue with `multi_query.py` being excluded from discovery despite containing classes that are NOT plugins (which is correct), but this is a fragile convention.

## Critical Findings

No critical findings that would cause production incidents.

## Warnings

### [18-47] EXCLUDED_FILES deny-list is fragile and grows monotonically

**What:** `EXCLUDED_FILES` is a hardcoded frozenset of filenames that should never be scanned. It currently contains 20 entries including infrastructure files (`__init__.py`, `base.py`, `protocols.py`), helper files (`utils.py`, `templates.py`, `auth.py`), LLM helpers (`aimd_throttle.py`, `capacity_errors.py`, `reorder_buffer.py`, `pooled_executor.py`, `multi_query.py`), and client helpers (`http.py`, `llm.py`, `replayer.py`, `verifier.py`).

**Why it matters:** This deny-list approach has two fragility risks:

1. **False exclusion:** If a new plugin file happens to share a name with an excluded file (e.g., someone creates a `utils.py` containing a plugin in a new directory), it will be silently excluded from discovery. The developer will see no error -- the plugin simply won't appear.

2. **Monotonic growth:** Every non-plugin Python file added to any scanned directory must be added to this list. If forgotten, the file will be imported during discovery and may cause unexpected side effects (especially for files like `examples.py` in the batching directory, which is NOT in the excluded list but lives in a directory that IS scanned -- though currently `batching/` is not in `PLUGIN_SCAN_CONFIG`).

An allow-list approach (e.g., plugin classes registering themselves, or a `__plugin__ = True` marker) would be more robust.

**Evidence:**
```python
EXCLUDED_FILES: frozenset[str] = frozenset(
    {
        "__init__.py",
        "hookimpl.py",
        "base.py",
        "templates.py",
        # ... 16 more entries
        "multi_query.py",  # Added because multi_query.py has config classes but no plugin
    }
)
```

### [96-114] Module registration in sys.modules persists even on successful load

**What:** `_discover_in_file()` registers the dynamically loaded module in `sys.modules` (line 108) before executing it. On failure, the module is cleaned up (line 113). On success, the module remains registered under the synthetic name `elspeth.plugins._discovered.{parent}.{stem}`.

**Why it matters:** These synthetic module entries persist in `sys.modules` for the entire process lifetime. If the same plugin file is imported through a normal import path elsewhere (e.g., `from elspeth.plugins.sources.csv_source import CSVSource`), there will be two module objects for the same file: one at the normal path and one at the `_discovered` path. This means `CSVSource` from the normal import and `CSVSource` from discovery are different class objects (even though they come from the same file), which can cause `isinstance` and `issubclass` checks to behave unexpectedly.

The `_discover_in_file` function mitigates this partially through the check `if obj.__module__ != module.__name__: continue` (line 120), which filters out classes imported from other modules. But the root issue remains: the same file can be loaded as two different modules.

**Evidence:**
```python
module_name = f"elspeth.plugins._discovered.{parent_name}.{py_file.stem}"
spec = importlib.util.spec_from_file_location(module_name, py_file)
# ...
sys.modules[module.__name__] = module  # Persists forever
```

In practice, this may not cause issues because:
- Discovery runs once at startup before normal imports
- Plugin classes are looked up by `name` attribute, not by identity
- The `obj.__module__` check prevents double-registration

But it is a latent risk if test code or other startup code imports plugin modules before discovery runs.

### [246-281] create_dynamic_hookimpl uses setattr on a dynamically created class

**What:** `create_dynamic_hookimpl()` creates a `DynamicHookImpl` class, creates a hook method function, decorates it with `@hookimpl`, and attaches it to the class via `setattr`. This is necessary because pluggy looks for hook methods by name on plugin instances.

**Why it matters:** This pattern works but has a subtle issue: the `DynamicHookImpl` class is created fresh each time `create_dynamic_hookimpl()` is called, but the `hook_method` closure captures the `plugin_classes` list by reference. If the caller modifies the list after calling `create_dynamic_hookimpl()`, the hook method will return the modified list. This is unlikely in practice (the caller is `discover_all_plugins()` which creates fresh lists), but worth noting.

A more idiomatic approach would be to use `tuple(plugin_classes)` in the closure to snapshot the list.

**Evidence:**
```python
def hook_method(self: Any) -> list[type]:
    return plugin_classes  # Captures by reference, not by value
```

## Observations

### [85-147] _discover_in_file is well-implemented

The function correctly handles:
- Module naming to avoid collisions (line 99: includes parent directory name)
- Python 3.13+ dataclass compatibility (lines 105-108: registers in sys.modules before exec_module)
- Filtering out imported classes (line 120: checks `__module__`)
- Filtering out abstract classes (line 128: checks `isabstract`)
- Filtering out classes without `name` attribute (line 135: uses `getattr` appropriately at framework boundary)
- Cleanup on failure (line 113: removes from sys.modules)

### [169-173] PLUGIN_SCAN_CONFIG correctly lists subdirectories explicitly

The configuration lists `"transforms/azure"` as a separate entry rather than relying on recursive scanning. This is documented as intentional ("Non-recursive scanning - subdirectories must be listed explicitly") and matches the flat scanning design.

### [176-219] discover_all_plugins has proper duplicate detection

The function checks for duplicate plugin names across directories within the same type (lines 206-212), providing a clear error message that includes both the existing and conflicting module paths. This catches the case where two different files in different scanned directories define plugins with the same name.

### [222-243] get_plugin_description gracefully handles missing docstrings

The function extracts the first non-empty line from the plugin class docstring, with a fallback to the plugin name. The `getattr(plugin_cls, "name", plugin_cls.__name__)` on line 242 is legitimate framework-level polymorphism (this function may be called with non-plugin classes for CLI display).

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** (1) Consider converting `EXCLUDED_FILES` from a deny-list to an allow-list or marker-based approach to prevent silent exclusion of new plugins. (2) Consider snapshotting `plugin_classes` with `tuple()` in the `create_dynamic_hookimpl` closure. (3) Document the sys.modules dual-registration risk and ensure test fixtures do not trigger it.
**Confidence:** HIGH -- the deny-list fragility and sys.modules issues are structural and well-understood. The current code works correctly for the current set of plugins but has clear scaling/maintenance risks.
