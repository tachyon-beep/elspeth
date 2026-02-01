# Bug Report: CSVFormatter allows NaN/Infinity in list serialization

## Summary

- `CSVFormatter` uses `json.dumps(value)` for list fields without `allow_nan=False`, allowing NaN/Infinity in CSV exports.

## Severity

- Severity: moderate
- Priority: P2

## Reporter

- Name or handle: Codex (triaged by Claude)
- Date: 2026-01-31

## Evidence

- `src/elspeth/core/landscape/formatters.py:215-217` - `json.dumps(value)` without `allow_nan=False`.

## Impact

- User-facing impact: CSV exports may contain non-standard JSON
- Data integrity: Inconsistent serialization

## Proposed Fix

- Use `json.dumps(..., allow_nan=False)` or `canonical_json()`

## Acceptance Criteria

- List values with NaN/Infinity are rejected or handled consistently

## Verification (2026-02-01)

**Status: STILL VALID**

- `CSVFormatter` still serializes list values via `json.dumps()` without NaN/Infinity rejection. (`src/elspeth/core/landscape/formatters.py:215-217`)
