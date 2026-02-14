## Summary

`purge --retention-days` accepts zero/negative overrides, bypassing configured `gt=0` retention contract.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `src/elspeth/cli.py`
- Function/Method: `purge`

## Evidence

- Source report: `docs/bugs/generated/cli.py.md`
- CLI override path does not validate positivity before `timedelta(days=retention_days)`.

## Root Cause Hypothesis

CLI option constraints were not aligned with settings-model constraints.

## Suggested Fix

Enforce `retention_days > 0` at CLI boundary and before invoking purge manager.

## Impact

Accidental over-purge can remove payload refs earlier than intended.

## Triage

- Status: open
- Source report: `docs/bugs/generated/cli.py.md`
- Beads: elspeth-rapid-wkb6
