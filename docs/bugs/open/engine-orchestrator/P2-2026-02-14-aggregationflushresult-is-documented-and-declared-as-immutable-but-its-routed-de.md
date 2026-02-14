## Summary

`AggregationFlushResult` is documented and declared as immutable, but its `routed_destinations` field remains mutable, allowing post-creation counter mutation.

## Severity

- Severity: minor
- Priority: P2

## Location

- File: /home/john/elspeth-rapid/src/elspeth/engine/orchestrator/types.py
- Line(s): 89, 94, 105
- Function/Method: `AggregationFlushResult` (dataclass definition)

## Evidence

`AggregationFlushResult` is `frozen=True`, and the docstring says this “prevents accidental mutation”, but the field is a plain `dict`:

```python
# /home/john/elspeth-rapid/src/elspeth/engine/orchestrator/types.py:89-95
@dataclass(frozen=True, slots=True)
class AggregationFlushResult:
    """...
    and type safety. Using frozen dataclass prevents accidental mutation.
    """

# /home/john/elspeth-rapid/src/elspeth/engine/orchestrator/types.py:105
routed_destinations: dict[str, int] = field(default_factory=dict)
```

Runtime verification shows mutation is possible:

```python
from elspeth.engine.orchestrator.types import AggregationFlushResult
r = AggregationFlushResult(routed_destinations={"a": 1})
r.routed_destinations["b"] = 2
print(r.routed_destinations)  # {'a': 1, 'b': 2}
```

So immutability is shallow, not effective for this field.

## Root Cause Hypothesis

`frozen=True` only blocks attribute reassignment on the dataclass, not mutation of mutable objects stored in fields. The implementation assumes deep immutability, but `dict` violates that assumption.

## Suggested Fix

Make `routed_destinations` immutable at construction time in `types.py`:

- Change field type to `Mapping[str, int]`.
- In `__post_init__`, copy and wrap with `MappingProxyType` via `object.__setattr__`.
- Keep `__add__` returning a fresh immutable mapping as well.
- Add a unit test proving nested mutation (`result.routed_destinations["x"] = 1`) fails.

## Impact

This allows accidental or intentional mutation of flush counters after result creation, which can skew aggregated execution counters and final run summary metrics (`routed_destinations`). That undermines the intended safety/invariant guarantees around orchestrator accounting.

## Triage

- Status: open
- Source report: `docs/bugs/generated/engine/orchestrator/types.py.md`
- Finding index in source report: 1
- Beads: pending
