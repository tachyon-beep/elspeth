# Bug Report: Trigger condition silently coerces non-boolean results

## Summary

- Trigger evaluation uses `if bool(result):` which coerces non-boolean expression results. Integer or string expressions trigger flushes based on truthiness rather than explicit boolean.

## Severity

- Severity: moderate
- Priority: P2

## Reporter

- Name or handle: Codex (triaged by Claude)
- Date: 2026-01-31

## Evidence

- `src/elspeth/engine/triggers.py:125-136` - Line 134: `if bool(result):` coerces non-boolean
- A condition like `"row['batch_count']"` (integer) would trigger on any non-zero value
- Violates CLAUDE.md prohibition on coercion for our data

## Impact

- User-facing impact: Unexpected batch boundaries from truthy non-boolean values
- Data integrity: Aggregation behavior depends on Python truthiness rules

## Proposed Fix

- Validate that expression result is actually boolean, raise if not

## Acceptance Criteria

- Non-boolean expression results raise ValueError
- Boolean results work as expected

## Verification (2026-02-01)

**Status: STILL VALID**

- Trigger condition still coerces result with `bool(result)` instead of enforcing boolean. (`src/elspeth/engine/triggers.py:125-135`)
