## Summary

`PluginManager.register()` leaves pluggy polluted when duplicate plugin names are detected, so a failed registration permanently poisons future registrations in the same manager instance.

## Severity

- Severity: major
- Priority: P2 (downgraded from P1 -- single startup call site, no hot-reload path, duplicate detection structurally prevented by separate per-type discovery)

## Location

- File: `src/elspeth/plugins/manager.py`
- Line(s): `79-87`, `100-119`
- Function/Method: `PluginManager.register`, `PluginManager._refresh_caches`

## Evidence

`register()` adds the plugin to pluggy first, only rolling back for `PluginValidationError`:

```python
# src/elspeth/plugins/manager.py:79-87
self._pm.register(plugin)
try:
    self._pm.check_pending()
except pluggy.PluginValidationError:
    self._pm.unregister(plugin=plugin)
    raise
self._refresh_caches()
```

Duplicate-name detection happens later inside `_refresh_caches()` and raises `ValueError`:

```python
# src/elspeth/plugins/manager.py:107-112
for transforms in self._pm.hook.elspeth_get_transforms():
    for cls in transforms:
        name = cls.name
        if name in new_transforms:
            raise ValueError(...)
```

Because `register()` does not catch `_refresh_caches()` failures, the newly added plugin remains in `self._pm` after the exception. A local repro in this repo showed:

- duplicate registration raises `ValueError` (expected),
- failed plugin remains in `self._pm.get_plugins()`,
- later valid registrations also fail with the same duplicate error due to persistent polluted state.

Related tests currently assert only that an error is raised, not state rollback after duplicate failure (`tests/unit/plugins/test_manager.py:122-147`, `tests/unit/plugins/test_hookimpl_registration.py:68-76`).

## Root Cause Hypothesis

Rollback logic is incomplete: it handles hook-spec validation failures (`check_pending`) but not cache-refresh failures (duplicate name conflicts), even though both occur after `self._pm.register(plugin)` mutates manager state.

## Suggested Fix

In `register()`, treat `_refresh_caches()` failure as transactional failure:

1. Register plugin.
2. Validate hooks.
3. Refresh caches.
4. If step 2 or 3 fails, unregister the just-added plugin, refresh caches back to last-good state, then re-raise.

Example shape:

```python
self._pm.register(plugin)
try:
    self._pm.check_pending()
    self._refresh_caches()
except Exception:
    self._pm.unregister(plugin=plugin)
    self._refresh_caches()
    raise
```

Also add a regression test: after duplicate registration failure, registering a distinct plugin should still succeed.

## Impact

A single duplicate-registration attempt can leave `PluginManager` in a corrupted in-memory state, causing all subsequent registrations to fail in-process. This breaks plugin lifecycle reliability and can block startup/reload flows that attempt additional registration after an initial config/discovery error.
