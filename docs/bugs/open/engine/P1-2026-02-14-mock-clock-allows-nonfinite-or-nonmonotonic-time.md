## Summary

`MockClock` accepts non-finite and non-monotonic values, which can silently disable timeout behavior.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `src/elspeth/engine/clock.py`
- Function/Method: `MockClock.__init__`, `MockClock.advance`, `MockClock.set`

## Evidence

- Source report: `docs/bugs/generated/engine/clock.py.md`
- Current logic allows `NaN`, `inf`, and backward `set()` behavior while engine timeout checks assume valid monotonic time.

## Root Cause Hypothesis

Test-clock flexibility drifted beyond the `Clock` contract used by timeout-critical engine paths.

## Suggested Fix

Enforce finite, monotonic time values at all clock write points.

## Impact

Timeouts and duration-driven behavior can fail to trigger, leaving rows buffered indefinitely.

## Triage

- Status: open
- Source report: `docs/bugs/generated/engine/clock.py.md`
- Beads: elspeth-rapid-uqy2
