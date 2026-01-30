# Bug Report: Schema compatibility allows int->float coercion even when consumer schema is strict

## Summary

- `_types_compatible()` unconditionally allows `int -> float` coercion without checking consumer schema strictness, violating the Data Manifesto rule that transforms/sinks must NOT coerce.

## Severity

- Severity: moderate
- Priority: P2

## Reporter

- Name or handle: Codex (triaged by Claude)
- Date: 2026-01-31

## Evidence

- `src/elspeth/contracts/data.py:225-245` - `_types_compatible()` at line 244: `if expected is float and actual is int: return True`
- `check_compatibility()` at lines 134-199 never inspects consumer schema strictness
- CLAUDE.md Data Manifesto: transforms/sinks must NOT coerce

## Impact

- User-facing impact: Invalid pipelines pass DAG validation, fail at runtime
- Data integrity: Schema contract violations not caught at construction time

## Proposed Fix

- Add consumer strictness check to `_types_compatible()` before allowing int->float

## Acceptance Criteria

- Strict schemas reject int->float coercion
- Non-strict schemas continue to allow it
