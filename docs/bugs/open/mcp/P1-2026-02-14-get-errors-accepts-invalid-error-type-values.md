## Summary

`get_errors()` accepts invalid `error_type` and returns partial success-shaped payload instead of a clear validation error.

## Severity

- Severity: minor
- Priority: P2 (downgraded from P1 — MCP SDK validates error_type against tool schema enum before reaching handler; defense-in-depth gap only, not reachable via MCP protocol)

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
