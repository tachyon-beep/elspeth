## Summary

`elspeth.core.checkpoint` omits `IncompatibleCheckpointError` from its public re-export surface even though `CheckpointManager` publicly raises that exception, so callers using the package facade cannot import and catch the documented failure type from the same API boundary.

## Severity

- Severity: minor
- Priority: P3

## Location

- File: `/home/john/elspeth/src/elspeth/core/checkpoint/__init__.py`
- Line(s): 14, 18-27
- Function/Method: module export surface (`__all__`)

## Evidence

`/home/john/elspeth/src/elspeth/core/checkpoint/__init__.py:14-16` re-exports only `CheckpointCorruptionError` from `manager.py`:

```python
from elspeth.core.checkpoint.manager import CheckpointCorruptionError, CheckpointManager
from elspeth.core.checkpoint.recovery import RecoveryManager
from elspeth.core.checkpoint.serialization import checkpoint_dumps, checkpoint_loads
```

`/home/john/elspeth/src/elspeth/core/checkpoint/__init__.py:18-27` also excludes `IncompatibleCheckpointError` from `__all__`:

```python
__all__ = [
    "CheckpointCompatibilityValidator",
    "CheckpointCorruptionError",
    "CheckpointManager",
    "RecoveryManager",
    "ResumeCheck",
    "ResumePoint",
    "checkpoint_dumps",
    "checkpoint_loads",
]
```

But `CheckpointManager.get_latest_checkpoint()` explicitly documents and raises `IncompatibleCheckpointError` as part of its public contract in `/home/john/elspeth/src/elspeth/core/checkpoint/manager.py:146-157, 258-274`:

```python
def get_latest_checkpoint(self, run_id: str) -> Checkpoint | None:
    ...
    Raises:
        IncompatibleCheckpointError: If checkpoint predates deterministic node IDs
```

```python
if checkpoint.format_version is None:
    raise IncompatibleCheckpointError(...)
if checkpoint.format_version != Checkpoint.CURRENT_FORMAT_VERSION:
    raise IncompatibleCheckpointError(...)
```

The repo already works around this missing export by importing the exception from the submodule directly in `/home/john/elspeth/tests/unit/core/checkpoint/test_manager.py:16`:

```python
from elspeth.core.checkpoint.manager import CheckpointManager, IncompatibleCheckpointError
```

What the code does now:
- Exposes `CheckpointManager` at package level.
- Hides one of `CheckpointManager`'s documented exception types from that same package-level API.

What it should do:
- Re-export `IncompatibleCheckpointError` alongside `CheckpointManager`, or stop presenting `elspeth.core.checkpoint` as the subsystem facade.

## Root Cause Hypothesis

The package facade was updated to expose the main checkpoint classes and one error type (`CheckpointCorruptionError`), but `IncompatibleCheckpointError` was missed when the public surface was assembled. That leaves the facade internally inconsistent with the manager’s documented exception contract.

## Suggested Fix

Import and export `IncompatibleCheckpointError` in `/home/john/elspeth/src/elspeth/core/checkpoint/__init__.py`.

Example:

```python
from elspeth.core.checkpoint.manager import (
    CheckpointCorruptionError,
    CheckpointManager,
    IncompatibleCheckpointError,
)

__all__ = [
    "CheckpointCompatibilityValidator",
    "CheckpointCorruptionError",
    "CheckpointManager",
    "IncompatibleCheckpointError",
    "RecoveryManager",
    "ResumeCheck",
    "ResumePoint",
    "checkpoint_dumps",
    "checkpoint_loads",
]
```

A small regression test that verifies `from elspeth.core.checkpoint import IncompatibleCheckpointError` succeeds would lock the contract down.

## Impact

This does not corrupt checkpoint data, but it does break the checkpoint package’s public API contract. Any caller using the facade import style can instantiate `CheckpointManager` from `elspeth.core.checkpoint` yet must know to reach into `elspeth.core.checkpoint.manager` to catch one of its documented resume/version errors. That is a protocol/contract inconsistency and a likely source of `ImportError` or ad hoc submodule imports in downstream code.
