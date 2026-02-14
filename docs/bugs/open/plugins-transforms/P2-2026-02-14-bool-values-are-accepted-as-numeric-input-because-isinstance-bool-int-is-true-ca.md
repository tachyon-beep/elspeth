## Summary

`bool` values are accepted as numeric input because `isinstance(bool, int)` is true, causing silent aggregation of flags as `1/0` despite plugin contract text saying `int or float`.

## Severity

- Severity: minor
- Priority: P2

## Location

- File: /home/john/elspeth-rapid/src/elspeth/plugins/transforms/batch_stats.py
- Line(s): 30, 157-162
- Function/Method: `BatchStats.process`

## Evidence

Type gate:

- `/home/john/elspeth-rapid/src/elspeth/plugins/transforms/batch_stats.py:157` uses `isinstance(raw_value, (int, float))`
- In Python, `bool` is a subclass of `int`, so `True/False` pass this check.
- Error text says expected `int or float` (`/home/john/elspeth-rapid/src/elspeth/plugins/transforms/batch_stats.py:159-160`), implying `bool` should not be accepted.

Concrete repro (executed in repo):

- Input `amount` values `[True, False, True]`
- Output was `{'count': 3, 'sum': 2, 'batch_size': 3, 'mean': 0.6666666666666666}`

## Root Cause Hypothesis

Using `isinstance(..., (int, float))` for numeric validation unintentionally includes `bool`, so schema/contract mistakes can be hidden as plausible numeric aggregates.

## Suggested Fix

Use strict type discrimination that excludes `bool`, e.g. `type(raw_value) in (int, float)` (or explicit `isinstance(..., bool)` rejection) before arithmetic. Add a unit test in `tests/unit/plugins/transforms/test_batch_stats.py` for boolean input rejection.

## Impact

Boolean fields can be silently treated as numeric measures, producing misleading sums/means and obscuring upstream schema errors in production/audit outputs.

## Triage

- Status: open
- Source report: `docs/bugs/generated/plugins/transforms/batch_stats.py.md`
- Finding index in source report: 2
- Beads: pending
