## Summary

`resume` can create a new SQLite DB from a bad settings URL and then report `run not found` against the wrong database.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `src/elspeth/cli.py`
- Function/Method: `resume`

## Evidence

- Source report: `docs/bugs/generated/cli.py.md`
- Resume path does not apply existing-SQLite validation before opening settings-derived URL.

## Root Cause Hypothesis

Resume path is missing the existing DB preflight used by other commands.

## Suggested Fix

Validate SQLite URL existence and open in `create_tables=False` mode for resume.

## Impact

Operators can silently target a wrong/empty audit DB, harming diagnosis and trust.

## Triage

- Status: open
- Source report: `docs/bugs/generated/cli.py.md`
- Beads: elspeth-rapid-ti23
