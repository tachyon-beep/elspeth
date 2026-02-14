## Summary

`call_tool` returns plain text for invalid args/unknown tool, which MCP treats as success (`isError=false`) instead of error.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `src/elspeth/mcp/server.py`
- Function/Method: `call_tool`

## Evidence

- Source report: `docs/bugs/generated/mcp/server.py.md`
- Validation and unknown-tool failures return normal content lists rather than MCP error results.

## Root Cause Hypothesis

Error conditions are mapped to message content instead of protocol-level error results.

## Suggested Fix

Return MCP error responses for argument validation failures and unknown tool dispatch.

## Impact

Clients can mis-handle failures as successful tool runs.

## Triage

- Status: open
- Source report: `docs/bugs/generated/mcp/server.py.md`
- Beads: elspeth-rapid-o70k
