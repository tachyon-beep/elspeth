## Summary

`RowDataResult` does not validate that `state` is a `RowDataState`, so invalid/raw string states are silently accepted.

## Severity

- Severity: major
- Priority: P3 (downgraded from P2 — all callers use enum members; StrEnum equality lets raw strings pass but no caller sends them)

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/core/landscape/row_data.py`
- Line(s): `56-68`
- Function/Method: `RowDataResult.__post_init__`

## Evidence

`__post_init__` validates only state/data combinations, not state type:

```python
# src/elspeth/core/landscape/row_data.py:56-68
if self.state == RowDataState.AVAILABLE:
    ...
if self.state != RowDataState.AVAILABLE and self.data is not None:
    raise ValueError(f"{self.state} state requires None data")
```

There is no check like `type(self.state) is RowDataState`. Because `RowDataState` is a `StrEnum`, raw strings compare against enum values, so bad inputs pass:

- `RowDataResult(state="available", data={"a": 1})` succeeds with `state` type `str`
- `RowDataResult(state="bogus", data=None)` also succeeds

I verified this in runtime with `.venv/bin/python` in this repo.
This violates the discriminated-union contract in the same file (`state: RowDataState`) and weakens Tier-1 strictness.

Related test coverage misses this case: `tests/unit/core/landscape/test_row_data.py` and `tests/property/core/test_row_data_properties.py` only construct with enum values.

## Root Cause Hypothesis

The class relies on static typing annotations plus equality checks, but does not enforce runtime enum typing. `StrEnum`’s string comparability makes this especially easy to miss.

## Suggested Fix

Add explicit runtime type validation at the top of `__post_init__`:

```python
if type(self.state) is not RowDataState:
    actual_type = type(self.state).__name__
    raise TypeError(f"state must be RowDataState, got {actual_type}")
```

Also add tests asserting string states (valid-looking or invalid) raise `TypeError`.

## Impact

Invalid state values can propagate as if they were valid `RowDataResult` objects, causing downstream `match`/branch logic to miss expected cases and potentially hide audit-state anomalies instead of crashing fast. This undermines contract reliability for row-data retrieval semantics.

## Triage

- Status: open
- Source report: `docs/bugs/generated/core/landscape/row_data.py.md`
- Finding index in source report: 1
- Beads: pending

Triage: Downgraded P2→P3. All RowDataResult constructors in _query_methods.py use RowDataState.X enum members. Raw string scenario requires future caller bug. Trivial fix: add type() check.
