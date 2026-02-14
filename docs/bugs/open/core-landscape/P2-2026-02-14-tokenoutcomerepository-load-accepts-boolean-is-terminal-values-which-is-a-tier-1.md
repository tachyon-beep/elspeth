## Summary

`TokenOutcomeRepository.load()` accepts boolean `is_terminal` values, which is a Tier-1 type-coercion leak for audit DB data.

## Severity

- Severity: minor
- Priority: P3 (downgraded from P2 — SQLAlchemy/SQLite returns int, never bool; pedantic type check)

## Location

- File: /home/john/elspeth-rapid/src/elspeth/core/landscape/repositories.py
- Line(s): 470-477
- Function/Method: `TokenOutcomeRepository.load`

## Evidence

Validation currently uses membership:
```python
if row.is_terminal not in (0, 1):
```
(`/home/john/elspeth-rapid/src/elspeth/core/landscape/repositories.py:472`)

In Python, `True == 1` and `False == 0`, so booleans pass this check even though they are not integer literals in a strict Tier-1 sense. The current unit test explicitly accepts this behavior:
`/home/john/elspeth-rapid/tests/unit/core/landscape/test_repositories.py:1267-1276`

Tier-1 policy says wrong types in audit DB must crash:
`/home/john/elspeth-rapid/CLAUDE.md:29-33`

## Root Cause Hypothesis

Validation used value-equivalence (`in (0, 1)`) instead of exact-type + value validation, and Python bool-int subtype behavior masked it.

## Suggested Fix

Use strict type/value checking:
```python
if type(row.is_terminal) is not int or row.is_terminal not in (0, 1):
    raise ValueError(...)
```
Then update tests so bool input is rejected.

## Impact

Malformed type data in `token_outcomes.is_terminal` can pass undetected, violating Tier-1 “no coercion” guarantees and weakening corruption/tampering detection.

## Triage

- Status: open
- Source report: `docs/bugs/generated/core/landscape/repositories.py.md`
- Finding index in source report: 2
- Beads: pending

Triage: Downgraded P2→P3. The is_terminal column is Integer. SQLAlchemy result proxy returns Python int, not bool. bool-in-(0,1) is True due to Python subclassing but never occurs in production.
