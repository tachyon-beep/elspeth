# Bug Report: RowResult exposes legacy token_id/row_id accessors

## Summary

- `RowResult` defines `token_id` and `row_id` properties explicitly labeled "backwards compatibility," violating the No Legacy Code Policy.

## Severity

- Severity: minor
- Priority: P3

## Reporter

- Name or handle: Codex (triaged by Claude)
- Date: 2026-01-31

## Evidence

- `src/elspeth/contracts/results.py:210-218` - properties documented as "backwards compatibility"
- CLAUDE.md:797-841 forbids backwards compatibility code

## Proposed Fix

- Remove properties; update callers to use `row_result.token.token_id`

## Acceptance Criteria

- No backwards compatibility properties remain
