## Summary

`get_errors()` accepts invalid `error_type` and returns partial success-shaped payload instead of a clear validation error.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `src/elspeth/mcp/analyzers/queries.py`
- Function/Method: `get_errors`

## Evidence

- Source report: `docs/bugs/generated/mcp/analyzers/queries.py.md`
- Unsupported `error_type` values bypass both validation branches and still return `{"run_id": ...}`.

## Root Cause Hypothesis

Value-domain validation was omitted for `error_type` in analyzer runtime path.

## Suggested Fix

Reject unsupported `error_type` values with explicit error.

## Impact

MCP callers can conclude “no errors” when input was invalid.

## Triage

- Status: open
- Source report: `docs/bugs/generated/mcp/analyzers/queries.py.md`
- Beads: elspeth-rapid-z6qk
