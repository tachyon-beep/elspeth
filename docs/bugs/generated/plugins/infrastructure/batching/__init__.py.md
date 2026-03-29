## Summary

No concrete bug found in /home/john/elspeth/src/elspeth/plugins/infrastructure/batching/__init__.py

## Severity

- Severity: trivial
- Priority: P3

## Location

- File: /home/john/elspeth/src/elspeth/plugins/infrastructure/batching/__init__.py
- Line(s): 29-37
- Function/Method: Unknown

## Evidence

`/home/john/elspeth/src/elspeth/plugins/infrastructure/batching/__init__.py:29-37` only re-exports three symbols:

```python
from elspeth.plugins.infrastructure.batching.mixin import BatchTransformMixin
from elspeth.plugins.infrastructure.batching.ports import OutputPort
from elspeth.plugins.infrastructure.batching.row_reorder_buffer import RowReorderBuffer

__all__ = [
    "BatchTransformMixin",
    "OutputPort",
    "RowReorderBuffer",
]
```

I verified the package-level import surface against real call sites:

- `/home/john/elspeth/src/elspeth/plugins/transforms/llm/transform.py:33` imports `BatchTransformMixin, OutputPort` from this package.
- `/home/john/elspeth/src/elspeth/plugins/transforms/azure/base.py:28` imports `BatchTransformMixin, OutputPort` from this package.
- `/home/john/elspeth/tests/unit/contracts/transform_contracts/test_batch_transform_protocol.py:48-49` imports `OutputPort` from the package and `BatchTransformMixin` from the submodule.
- `/home/john/elspeth/tests/unit/plugins/batching/test_batch_transform_mixin.py:25-26` imports `BatchTransformMixin` from the package and test-only helpers from the `ports` submodule.

Those imports match the symbols exported here. I did not find a missing export, broken alias, circular import symptom, or package-level contract mismatch whose primary fix belongs in `__init__.py`.

## Root Cause Hypothesis

No bug identified.

## Suggested Fix

No fix required.

## Impact

No concrete runtime, audit-trail, protocol, or state-management failure was confirmed as originating in `/home/john/elspeth/src/elspeth/plugins/infrastructure/batching/__init__.py`. Any substantive batching behavior and related risks live in the underlying implementation modules, not this re-export file.
