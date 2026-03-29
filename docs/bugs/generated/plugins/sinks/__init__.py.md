## Summary

`src/elspeth/plugins/sinks/__init__.py` documents the wrong built-in sink name: it tells callers to request `"csv_sink"`, but the registered sink name is `"csv"`.

## Severity

- Severity: trivial
- Priority: P3

## Location

- File: /home/john/elspeth/src/elspeth/plugins/sinks/__init__.py
- Line(s): 5-8
- Function/Method: Module docstring

## Evidence

`/home/john/elspeth/src/elspeth/plugins/sinks/__init__.py:5-8` says:

```python
Plugins are accessed via PluginManager, not direct imports:
    manager = PluginManager()
    manager.register_builtin_plugins()
    sink = manager.get_sink_by_name("csv_sink")
```

But the actual plugin manager registers built-in sinks by their `name` attribute and looks them up verbatim via `get_sink_by_name(name)`:

- `/home/john/elspeth/src/elspeth/plugins/infrastructure/manager.py:54-73` registers discovered sinks
- `/home/john/elspeth/src/elspeth/plugins/infrastructure/manager.py:171-186` resolves sink names directly from `self._sinks`

The test suite confirms the real built-in sink names are `"csv"`, `"json"`, and `"database"`, not `"csv_sink"`:

- `/home/john/elspeth/tests/unit/plugins/test_hookimpl_registration.py:38-48`
- `/home/john/elspeth/tests/unit/plugins/test_hookimpl_registration.py:63-66`

So the example in the target file would lead readers to a `ValueError` for an unknown sink plugin instead of a working lookup.

## Root Cause Hypothesis

The package docstring appears to have drifted from the actual plugin naming convention. Sink class/file names use `*_sink`, but registration uses the plugin `name` field (`"csv"`), and the example was never updated to match that contract.

## Suggested Fix

Update the example to use the real registered sink name:

```python
sink = manager.get_sink_by_name("csv")
```

Optionally align it with sibling package docs in `plugins/sources/__init__.py` and `plugins/transforms/__init__.py`, which already use the actual plugin names.

## Impact

This does not break pipeline execution, audit trail, or sink registration. It is a user-facing documentation bug in the target file that can mislead developers into calling the plugin manager with an invalid sink name and getting a startup-time lookup failure.
