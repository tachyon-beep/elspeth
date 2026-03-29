## Summary

`elspeth.engine` drops part of the orchestrator public API: `AggregationFlushResult`, `ExecutionCounters`, and `RowPlugin` exist in the engine subsystem but cannot be imported from the package facade.

## Severity

- Severity: major
- Priority: P2

## Location

- File: /home/john/elspeth/src/elspeth/engine/__init__.py
- Line(s): 51-56, 62-85
- Function/Method: module scope (`__all__` / re-export surface)

## Evidence

`src/elspeth/engine/orchestrator/__init__.py:6-13` explicitly documents these names as part of the orchestrator public API:

```python
Public API (unchanged):
- Orchestrator
- PipelineConfig
- RunResult
- RouteValidationError
- AggregationFlushResult
- ExecutionCounters
- RowPlugin
```

But `src/elspeth/engine/__init__.py:51-56` only imports:

```python
from elspeth.engine.orchestrator import (
    Orchestrator,
    PipelineConfig,
    RouteValidationError,
    RunResult,
)
```

And `src/elspeth/engine/__init__.py:62-85` omits `AggregationFlushResult`, `ExecutionCounters`, and `RowPlugin` from `__all__`.

The symbols are real, live API objects in `src/elspeth/engine/orchestrator/types.py:55,104,144`, but package-level imports fail:

```python
from elspeth.engine import AggregationFlushResult  # ImportError
from elspeth.engine import ExecutionCounters       # ImportError
from elspeth.engine import RowPlugin               # ImportError
```

Verified in-repo against the current codebase; each raises:

```python
ImportError cannot import name 'AggregationFlushResult' from 'elspeth.engine'
```

This drift is easy to miss because tests use deeper imports instead, e.g. `tests/property/engine/test_orchestrator_lifecycle_properties.py:28-33` imports from `elspeth.engine.orchestrator.types`, so the broken top-level facade is not exercised.

## Root Cause Hypothesis

The orchestrator package was split into submodules and its own `__init__.py` preserved the broader API, but `src/elspeth/engine/__init__.py` was only partially updated. The engine facade still re-exports the older subset (`Orchestrator`, `PipelineConfig`, `RunResult`, `RouteValidationError`) and never picked up the additional orchestrator API surface.

## Suggested Fix

Import the missing symbols from `elspeth.engine.orchestrator` and add them to `__all__` in `src/elspeth/engine/__init__.py`.

Example:

```python
from elspeth.engine.orchestrator import (
    AggregationFlushResult,
    ExecutionCounters,
    Orchestrator,
    PipelineConfig,
    RouteValidationError,
    RowPlugin,
    RunResult,
)

__all__ = [
    ...
    "AggregationFlushResult",
    "ExecutionCounters",
    ...
    "RowPlugin",
    ...
]
```

Also add a regression test that imports the documented public API from `elspeth.engine` directly, not only from `elspeth.engine.orchestrator` or `...types`.

## Impact

Any caller using the package-level engine facade gets an immediate import-time failure for these documented engine types. That breaks the public contract of the engine package, forces consumers onto deeper module paths, and makes future refactors riskier because the intended stable import surface is already inconsistent. This is not an audit-trail corruption bug, but it is a real integration and protocol-contract break in the target file.
