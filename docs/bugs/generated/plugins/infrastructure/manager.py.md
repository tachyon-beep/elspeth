## Summary

`get_shared_plugin_manager()` publishes the global singleton before built-in plugin registration finishes, so a concurrent first caller can observe an empty `PluginManager` and cache incomplete plugin state.

## Severity

- Severity: major
- Priority: P2

## Location

- File: `/home/john/elspeth/src/elspeth/plugins/infrastructure/manager.py`
- Line(s): 301-305
- Function/Method: `get_shared_plugin_manager`

## Evidence

[`/home/john/elspeth/src/elspeth/plugins/infrastructure/manager.py#L301`](file:///home/john/elspeth/src/elspeth/plugins/infrastructure/manager.py#L301) assigns the singleton before registration completes:

```python
global _shared_instance
if _shared_instance is None:
    _shared_instance = PluginManager()
    _shared_instance.register_builtin_plugins()
return _shared_instance
```

That creates a publication window where `_shared_instance` is non-`None` but still has empty caches. [`/home/john/elspeth/src/elspeth/plugins/infrastructure/manager.py#L46`](file:///home/john/elspeth/src/elspeth/plugins/infrastructure/manager.py#L46)-[`/home/john/elspeth/src/elspeth/plugins/infrastructure/manager.py#L49`](file:///home/john/elspeth/src/elspeth/plugins/infrastructure/manager.py#L49) show those caches start empty, and they are only populated inside `_refresh_caches()` during registration.

A caller that grabs the singleton during that window can permanently cache the bad state. [`/home/john/elspeth/src/elspeth/web/catalog/service.py#L36`](file:///home/john/elspeth/src/elspeth/web/catalog/service.py#L36)-[`/home/john/elspeth/src/elspeth/web/catalog/service.py#L39`](file:///home/john/elspeth/src/elspeth/web/catalog/service.py#L39) copies the plugin lists once in `CatalogServiceImpl.__init__`, and [`/home/john/elspeth/src/elspeth/web/dependencies.py#L37`](file:///home/john/elspeth/src/elspeth/web/dependencies.py#L37)-[`/home/john/elspeth/src/elspeth/web/dependencies.py#L44`](file:///home/john/elspeth/src/elspeth/web/dependencies.py#L44) explicitly assumes the returned manager is already initialized.

There is no concurrency coverage for this path. [`/home/john/elspeth/tests/unit/plugins/test_manager_singleton.py#L11`](file:///home/john/elspeth/tests/unit/plugins/test_manager_singleton.py#L11)-[`/home/john/elspeth/tests/unit/plugins/test_manager_singleton.py#L30`](file:///home/john/elspeth/tests/unit/plugins/test_manager_singleton.py#L30) only checks repeated sequential calls.

## Root Cause Hypothesis

The singleton factory conflates allocation and publication. It stores the global reference before the expensive side effect (`register_builtin_plugins()`) has established the invariant “shared manager is fully initialized,” and there is no lock around first-use publication.

## Suggested Fix

Construct and initialize a local manager first, then publish it only after successful registration. Protect first initialization with a module-level lock.

Example shape:

```python
_lock = threading.Lock()

def get_shared_plugin_manager() -> PluginManager:
    global _shared_instance
    if _shared_instance is not None:
        return _shared_instance
    with _lock:
        if _shared_instance is None:
            manager = PluginManager()
            manager.register_builtin_plugins()
            _shared_instance = manager
    return _shared_instance
```

Add a regression test that forces two concurrent first calls and asserts both callers receive the same fully populated manager.

## Impact

The first concurrent access can yield a manager with zero registered plugins. That can make catalog endpoints return empty plugin inventories, or cause later lookups to fail with misleading “Unknown plugin” errors even though built-ins exist. It is an integration/state-management bug in the manager’s shared initialization path.
---
## Summary

If built-in discovery/registration throws once, `get_shared_plugin_manager()` leaves `_shared_instance` pointing at a broken, uninitialized manager, so later calls silently reuse poisoned state instead of retrying or surfacing the original failure.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `/home/john/elspeth/src/elspeth/plugins/infrastructure/manager.py`
- Line(s): 301-305
- Function/Method: `get_shared_plugin_manager`

## Evidence

The same singleton code in [`/home/john/elspeth/src/elspeth/plugins/infrastructure/manager.py#L301`](file:///home/john/elspeth/src/elspeth/plugins/infrastructure/manager.py#L301)-[`/home/john/elspeth/src/elspeth/plugins/infrastructure/manager.py#L305`](file:///home/john/elspeth/src/elspeth/plugins/infrastructure/manager.py#L305) assigns `_shared_instance` before the fallible work runs:

```python
if _shared_instance is None:
    _shared_instance = PluginManager()
    _shared_instance.register_builtin_plugins()
return _shared_instance
```

`register_builtin_plugins()` can legitimately raise: it calls discovery, and discovery is intentionally crash-on-bug. [`/home/john/elspeth/src/elspeth/plugins/infrastructure/discovery.py#L79`](file:///home/john/elspeth/src/elspeth/plugins/infrastructure/discovery.py#L79)-[`/home/john/elspeth/src/elspeth/plugins/infrastructure/discovery.py#L82`](file:///home/john/elspeth/src/elspeth/plugins/infrastructure/discovery.py#L82) says import/syntax errors must propagate, and [`/home/john/elspeth/src/elspeth/plugins/infrastructure/discovery.py#L116`](file:///home/john/elspeth/src/elspeth/plugins/infrastructure/discovery.py#L116)-[`/home/john/elspeth/src/elspeth/plugins/infrastructure/discovery.py#L121`](file:///home/john/elspeth/src/elspeth/plugins/infrastructure/discovery.py#L121) re-raises module import failures.

Because the global is set first, any exception exits with `_shared_instance` still non-`None`. The next call skips initialization entirely and returns that empty manager. Downstream callers then see secondary symptoms. For example, [`/home/john/elspeth/src/elspeth/cli.py#L1235`](file:///home/john/elspeth/src/elspeth/cli.py#L1235) uses the shared manager to list plugins, and [`/home/john/elspeth/src/elspeth/cli_helpers.py#L67`](file:///home/john/elspeth/src/elspeth/cli_helpers.py#L67)-[`/home/john/elspeth/src/elspeth/cli_helpers.py#L70`](file:///home/john/elspeth/src/elspeth/cli_helpers.py#L70) uses it for plugin lookup. After poisoning, those paths can emit misleading “unknown plugin” behavior instead of the real discovery failure.

There is no regression test for failed first initialization in [`/home/john/elspeth/tests/unit/plugins/test_manager_singleton.py`](file:///home/john/elspeth/tests/unit/plugins/test_manager_singleton.py).

## Root Cause Hypothesis

The function does not treat initialization as transactional. A partially initialized object is published globally, and there is no rollback/reset when `register_builtin_plugins()` fails.

## Suggested Fix

Do not assign the global until initialization succeeds. If registration fails, leave `_shared_instance` as `None` so the real failure can be retried or surfaced cleanly.

Example shape:

```python
def get_shared_plugin_manager() -> PluginManager:
    global _shared_instance
    if _shared_instance is None:
        manager = PluginManager()
        manager.register_builtin_plugins()
        _shared_instance = manager
    return _shared_instance
```

If a lock is added for the race above, keep the same transactional pattern inside the critical section. Add a test that monkeypatches `register_builtin_plugins()` to raise once and asserts a later call retries instead of returning an empty manager.

## Impact

A single discovery/import bug can poison the process-wide plugin registry. After that, callers stop seeing the original framework bug and instead operate on an empty manager, producing misleading lookup failures and empty plugin catalogs. That obscures root cause and breaks plugin discovery across CLI and web entry points.
