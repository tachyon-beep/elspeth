## Summary

`RunResult` accepts a plain `str` for `status`, so an invalid contract instance can be created and later crashes consumers that assume `RunStatus`.

## Severity

- Severity: major
- Priority: P2

## Location

- File: /home/john/elspeth/src/elspeth/contracts/run_result.py
- Line(s): 22-23, 37-51
- Function/Method: `RunResult.__post_init__`

## Evidence

`RunResult` validates `run_id` and every integer counter, but never validates `status`:

```python
# /home/john/elspeth/src/elspeth/contracts/run_result.py:22-23,37-51
run_id: str
status: RunStatus
...
def __post_init__(self) -> None:
    if not self.run_id:
        raise ValueError("run_id must not be empty")
    require_int(self.rows_processed, "rows_processed", min_value=0)
    ...
    freeze_fields(self, "routed_destinations")
```

Downstream code assumes `status` is a real enum and dereferences enum-only attributes:

```python
# /home/john/elspeth/src/elspeth/cli.py:1973-1977,1984-1987
"status": result.status.value,
...
typer.echo(f"  Status: {result.status.value}")
```

```python
# /home/john/elspeth/src/elspeth/engine/dependency_resolver.py:135-140
if run_result.status != RunStatus.COMPLETED:
    raise DependencyFailedError(
        ...
        reason=f"Dependency pipeline finished with status: {run_result.status.name}",
    )
```

The repo’s adjacent audit contract already enforces this exact invariant:

```python
# /home/john/elspeth/src/elspeth/contracts/audit.py:47-72
class Run:
    status: RunStatus
    def __post_init__(self) -> None:
        _validate_enum(self.status, RunStatus, "status")
```

and it has an integration test proving string status must crash at construction time:

```python
# /home/john/elspeth/tests/integration/audit/test_tier1_integrity.py:230-237
with pytest.raises(TypeError, match="status must be RunStatus"):
    Run(..., status="running")
```

`RunResult` has no equivalent guard or test.

## Root Cause Hypothesis

When `RunResult` was moved into `contracts/` and hardened for integer counters, the enum validation pattern used by neighboring contracts was not carried over. The type hint alone is being treated as enforcement, but runtime callers can still pass a `str`.

## Suggested Fix

Add explicit enum validation in `RunResult.__post_init__`, matching the existing contract style used in `contracts.audit.Run`:

```python
from elspeth.contracts.audit import _validate_enum  # or extract shared helper to a smaller L0 utility

def __post_init__(self) -> None:
    if not self.run_id:
        raise ValueError("run_id must not be empty")
    _validate_enum(self.status, RunStatus, "status")
    ...
```

Also add a unit/integration test that `RunResult(status="completed")` raises `TypeError`.

## Impact

A malformed `RunResult` is allowed to cross subsystem boundaries and then fails later with less actionable errors such as `'str' object has no attribute 'value'` or `'str' object has no attribute 'name'`. That violates ELSPETH’s offensive-programming and contract expectations: the bug should crash at contract construction, not leak into CLI output or dependency resolution paths.
