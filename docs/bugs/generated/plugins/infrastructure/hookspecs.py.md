## Summary

No concrete bug found in /home/john/elspeth/src/elspeth/plugins/infrastructure/hookspecs.py

## Severity

- Severity: trivial
- Priority: P3

## Location

- File: /home/john/elspeth/src/elspeth/plugins/infrastructure/hookspecs.py
- Line(s): 1-72
- Function/Method: Unknown

## Evidence

`src/elspeth/plugins/infrastructure/hookspecs.py:39-67` defines exactly the three hook names the plugin manager consumes: `elspeth_get_source`, `elspeth_get_transforms`, and `elspeth_get_sinks`.

```python
class ElspethSourceSpec:
    @hookspec
    def elspeth_get_source(self) -> list[type["SourceProtocol"]]: ...

class ElspethTransformSpec:
    @hookspec
    def elspeth_get_transforms(self) -> list[type["TransformProtocol"]]: ...

class ElspethSinkSpec:
    @hookspec
    def elspeth_get_sinks(self) -> list[type["SinkProtocol"]]: ...
```

`src/elspeth/plugins/infrastructure/manager.py:41-44` registers those exact spec classes with pluggy, and `src/elspeth/plugins/infrastructure/manager.py:109-128` calls those exact hook names to build the source/transform/sink caches. I did not find any mismatch between spec name and runtime use.

`src/elspeth/plugins/infrastructure/discovery.py:258-293` dynamically creates hook implementations using those same hook method names, so builtin discovery is aligned with the spec file.

`tests/unit/plugins/test_manager.py:270-290` verifies that a misspelled hook name is rejected by pluggy, which supports the conclusion that the spec names in `hookspecs.py` are the authoritative runtime contract. `tests/unit/plugins/test_hookspecs.py:18-32` also checks that the three hook methods exist.

I did not find evidence that this file is the primary cause of an audit-trail, trust-tier, protocol, state-management, validation, or integration bug.

## Root Cause Hypothesis

No bug identified.

## Suggested Fix

No fix recommended.

## Impact

No concrete runtime breakage attributable to `/home/john/elspeth/src/elspeth/plugins/infrastructure/hookspecs.py` was confirmed.
