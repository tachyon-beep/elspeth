## Summary

`call_tool` returns plain text for invalid args/unknown tool, which MCP treats as success (`isError=false`) instead of error.

## Severity

- Severity: minor
- Priority: P2 (downgraded from P1 — MCP SDK validates tool inputs against jsonschema before handler runs, catching most issues; error text is clearly prefixed with "Invalid arguments:" making it identifiable; read-only diagnostic tool)

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
