## Summary

`CoalesceFailureReason` is declared as a frozen audit DTO but does not deep-freeze `expected_branches` or `branches_arrived`, so callers can pass mutable lists and mutate the recorded failure payload after construction.

## Severity

- Severity: minor
- Priority: P2

## Location

- File: `/home/john/elspeth/src/elspeth/contracts/errors.py`
- Line(s): 65-106
- Function/Method: `CoalesceFailureReason.__post_init__`

## Evidence

`CoalesceFailureReason` has container fields annotated as tuples, but `__post_init__` only validates emptiness and `timeout_ms`; it never freezes or copies the branch collections:

```python
@dataclass(frozen=True, slots=True)
class CoalesceFailureReason:
    expected_branches: tuple[str, ...]
    branches_arrived: tuple[str, ...]
    ...
    def __post_init__(self) -> None:
        if not self.failure_reason:
            ...
        if not self.expected_branches:
            ...
```

Source: `/home/john/elspeth/src/elspeth/contracts/errors.py:65-89`

The serializer reads those fields later, at audit-write time:

```python
if error is not None:
    error_data = error.to_dict() if isinstance(error, (ExecutionError, CoalesceFailureReason)) else error
    error_json = canonical_json(error_data)
```

Source: `/home/john/elspeth/src/elspeth/core/landscape/execution_repository.py:277-281`

Repo tests already construct `CoalesceFailureReason` with mutable lists, proving this contract is used that way:

```python
error = CoalesceFailureReason(
    failure_reason="quorum_not_met",
    expected_branches=["a", "b"],
    branches_arrived=["a"],
    merge_policy="union",
)
```

Source: `/home/john/elspeth/tests/unit/contracts/test_errors.py:521-526`

This violates the project’s frozen-dataclass rule, which requires `freeze_fields()`/`deep_freeze()` for container fields:

Source: `/home/john/elspeth/CLAUDE.md:342-355`

For comparison, the same file already fixes this correctly for `GracefulShutdownError` by deep-freezing its mapping input:

Source: `/home/john/elspeth/src/elspeth/contracts/errors.py:674-692`

What the code does now:
- Accepts mutable lists into a “frozen” DTO.
- Leaves those lists mutable after construction.
- Serializes whatever current contents exist when `to_dict()` is called.

What it should do:
- Freeze/copy `expected_branches` and `branches_arrived` during construction so the audit payload is immutable once created.

## Root Cause Hypothesis

`CoalesceFailureReason` was implemented as a frozen dataclass, but the deep-immutability step was omitted. The tests focus on attribute reassignment and `to_dict()` shape, not nested/container mutability, so the gap was not caught.

## Suggested Fix

In `CoalesceFailureReason.__post_init__`, freeze the container fields, e.g. with `freeze_fields(self, "expected_branches", "branches_arrived")`, or explicitly `deep_freeze` and assign via `object.__setattr__`.

Example shape:

```python
from elspeth.contracts.freeze import freeze_fields

def __post_init__(self) -> None:
    freeze_fields(self, "expected_branches", "branches_arrived")
    if not self.failure_reason:
        ...
```

Also add a regression test mirroring the existing `GracefulShutdownError` freeze tests:
- construct with lists
- mutate the original lists
- assert the stored fields do not change
- assert direct mutation raises `TypeError`/fails via tuple immutability

## Impact

This weakens audit integrity for coalesce failures. A failure reason object can be created with one branch set and later serialize a different branch set, which means the persisted `node_states.error_json` may not faithfully represent the state at failure time. That undermines the “frozen DTO” contract and the repository’s stated requirement that audit records remain immutable and attributable.
