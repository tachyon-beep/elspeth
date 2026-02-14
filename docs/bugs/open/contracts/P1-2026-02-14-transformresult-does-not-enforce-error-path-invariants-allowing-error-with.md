## Summary

`TransformResult` does not enforce error-path invariants, allowing `status="error"` with `reason=None`, which creates a failed node state without actionable error context before crashing later.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth-rapid/src/elspeth/contracts/results.py
- Line(s): 126-139
- Function/Method: TransformResult.__post_init__

## Evidence

`TransformResult.__post_init__` validates only success cases:

```python
if self.status == "success" and self.success_reason is None: ...
if self.status == "success" and self.row is None and self.rows is None: ...
```

(`/home/john/elspeth-rapid/src/elspeth/contracts/results.py:126`)

No corresponding check exists for `status == "error"` requiring non-null `reason`.

Downstream, executor code assumes this invariant, but too late:

- It first records FAILED with `error=result.reason`
  (`/home/john/elspeth-rapid/src/elspeth/engine/executors/transform.py:371-376`)
- Then asserts `result.reason is not None`
  (`/home/john/elspeth-rapid/src/elspeth/engine/executors/transform.py:395-398`)
- `ctx.record_transform_error(...)` happens after that assert
  (`/home/john/elspeth-rapid/src/elspeth/engine/executors/transform.py:399-405`)

So invalid `TransformResult(status="error", reason=None)` can persist a FAILED node_state with null error payload, then abort before structured transform error recording/routing event.

Test evidence also shows direct dataclass construction is intentionally possible for invariant probing, so this path is real if plugin code bypasses factories:
`/home/john/elspeth-rapid/tests/unit/contracts/test_results.py:199-201`.

## Root Cause Hypothesis

Invariant enforcement in `TransformResult.__post_init__` is asymmetric: success invariants are enforced, error invariants are deferred to executor assertions. That leaves a gap where malformed error results can partially write audit state before invariant failure.

## Suggested Fix

In `TransformResult.__post_init__`, enforce full error-contract invariants at object construction:

- `status=="error"` requires `reason is not None`
- `status=="error"` must have `row is None` and `rows is None`
- `status=="error"` must have `success_reason is None`

Example:

```python
if self.status == "error" and self.reason is None:
    raise ValueError("TransformResult with status='error' MUST provide reason.")
if self.status == "error" and (self.row is not None or self.rows is not None):
    raise ValueError("TransformResult with status='error' MUST NOT include output data.")
if self.status == "error" and self.success_reason is not None:
    raise ValueError("TransformResult with status='error' MUST NOT include success_reason.")
```

Also add unit tests in `tests/unit/contracts/test_results.py` for these error invariants.

## Impact

This is an auditability defect: malformed transform errors can produce FAILED node states without actionable error details, and may skip `transform_errors` recording/routing metadata. In a high-stakes audit trail, that breaks "every failure is attributable" guarantees.
