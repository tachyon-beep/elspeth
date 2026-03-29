## Summary

`elspeth.core` exposes `ExecutionGraph` and `GraphValidationError` but forgets to re-export `GraphValidationWarning`, making the warning type for the DAG public API impossible to import from the package’s advertised top-level namespace.

## Severity

- Severity: minor
- Priority: P3

## Location

- File: `/home/john/elspeth/src/elspeth/core/__init__.py`
- Line(s): 33-39, 57-98
- Function/Method: Unknown

## Evidence

`/home/john/elspeth/src/elspeth/core/__init__.py:33-39` imports only these DAG symbols:

```python
from elspeth.core.dag import (
    ExecutionGraph,
    GraphValidationError,
    NodeConfig,
    NodeInfo,
    WiredTransform,
)
```

and `/home/john/elspeth/src/elspeth/core/__init__.py:57-98` includes `GraphValidationError` in `__all__` but not `GraphValidationWarning`.

That is inconsistent with the DAG package’s own public surface. `/home/john/elspeth/src/elspeth/core/dag/__init__.py:3-18` explicitly exports both:

```python
from elspeth.core.dag.models import (
    GraphValidationError,
    GraphValidationWarning,
    NodeConfig,
    NodeInfo,
    WiredTransform,
)
```

The warning type is not internal-only. `/home/john/elspeth/src/elspeth/core/dag/graph.py:902-905` exposes it in a public method signature:

```python
def warn_divert_coalesce_interactions(
    self,
    coalesce_configs: dict[NodeID, CoalesceSettings],
) -> list[GraphValidationWarning]:
```

and `/home/john/elspeth/src/elspeth/core/dag/graph.py:973-983` constructs and returns `GraphValidationWarning` instances.

Direct verification confirms the package export is broken: `from elspeth.core import GraphValidationWarning` raises `ImportError`, while `from elspeth.core import ExecutionGraph, GraphValidationError` succeeds. Existing integration coverage only checks the latter in `/home/john/elspeth/tests/unit/core/test_canonical.py:625-644`, so this gap is currently untested.

## Root Cause Hypothesis

`src/elspeth/core/__init__.py` appears to be a curated convenience surface that was not updated when `GraphValidationWarning` was added to the DAG public API. The file re-exports part of `elspeth.core.dag` rather than mirroring its full public contract, so the warning type drifted out of sync.

## Suggested Fix

Re-export `GraphValidationWarning` from `elspeth.core` and add it to `__all__`.

Example:

```python
from elspeth.core.dag import (
    ExecutionGraph,
    GraphValidationError,
    GraphValidationWarning,
    NodeConfig,
    NodeInfo,
    WiredTransform,
)
```

and add `"GraphValidationWarning"` to `__all__`.

A regression test should also be added alongside `/home/john/elspeth/tests/unit/core/test_canonical.py:628-632` to verify `from elspeth.core import GraphValidationWarning` works.

## Impact

Code that treats `elspeth.core` as the package-level API cannot import the warning type returned by `ExecutionGraph.warn_divert_coalesce_interactions()`. That breaks public API consistency and makes downstream typing, matching, and documentation examples fail unexpectedly. This does not appear to violate audit trail guarantees directly, but it is a real integration contract bug in the target file.
