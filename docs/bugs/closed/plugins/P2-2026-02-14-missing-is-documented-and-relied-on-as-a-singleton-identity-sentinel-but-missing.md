## Summary

`MISSING` is documented and relied on as a singleton identity sentinel, but `MissingSentinel` does not enforce singleton semantics, so copies/deserialization/new instantiation produce distinct objects and break `is MISSING` checks.

## Severity

- Severity: minor
- Priority: P3 (downgraded from P2 -- no production code path copies, pickles, or re-instantiates the sentinel; identity checks only occur on freshly-returned values within single function scope)

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/plugins/sentinels.py`
- Line(s): `31-45`
- Function/Method: `MissingSentinel` (class construction/instance lifecycle)

## Evidence

`/home/john/elspeth-rapid/src/elspeth/plugins/sentinels.py:34-35` says this is a singleton and must be compared by identity, but the implementation is only:

```python
class MissingSentinel:
    __slots__ = ()
MISSING: Final[MissingSentinel] = MissingSentinel()
```

No `__new__`, `__copy__`, `__deepcopy__`, or `__reduce__` guard exists.

Runtime repro from this repo workspace:

```text
deepcopy_identity False
pickle_identity False
new_instance_identity False
```

(Executed with: import `MISSING`, `MissingSentinel`; then `copy.deepcopy`, `pickle.dumps/loads`, and direct `MissingSentinel()`.)

Identity checks are used in integration points:
- `/home/john/elspeth-rapid/src/elspeth/plugins/utils.py:15,52` (returns sentinel default)
- `/home/john/elspeth-rapid/src/elspeth/plugins/transforms/field_mapper.py:121` (`if value is MISSING`)

So a non-canonical sentinel instance will be treated as a real value instead of “missing.”

## Root Cause Hypothesis

The module defines a singleton by convention/documentation only, not by construction mechanics. Python object copying/pickling and direct class calls create distinct `MissingSentinel` instances, violating the identity-based contract.

## Suggested Fix

Enforce singleton semantics in `sentinels.py` itself:

- Make `MissingSentinel.__new__` return the module singleton instance.
- Implement `__copy__`, `__deepcopy__`, and `__reduce__` to preserve identity.
- Optionally hide direct construction (e.g., module-private class/factory) and expose only `MISSING`.

Example pattern:

```python
class MissingSentinel:
    __slots__ = ()
    _instance: "MissingSentinel | None" = None

    def __new__(cls) -> "MissingSentinel":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __copy__(self) -> "MissingSentinel":
        return self

    def __deepcopy__(self, memo: dict[int, object]) -> "MissingSentinel":
        return self

    def __reduce__(self) -> tuple[type["MissingSentinel"], tuple[()]]:
        return (MissingSentinel, ())
```

## Impact

Missing-field detection can silently fail when sentinel values cross copy/serialization boundaries, causing downstream logic to treat “missing” as present data. In practice this can corrupt transform behavior (`field_mapper`) and weaken audit correctness by misclassifying row state/field provenance.

## Triage

- Status: open
- Source report: `docs/bugs/generated/plugins/sentinels.py.md`
- Finding index in source report: 1
- Beads: pending
