# Bug Report: LLM usage report misclassifies call status

## Summary

- LLM usage report checks `if row.status == "completed"` but actual stored value is `"success"` per `CallStatus` enum. All successful calls are misclassified as failures.

## Severity

- Severity: moderate
- Priority: P2

## Reporter

- Name or handle: Codex (triaged by Claude)
- Date: 2026-01-31

## Evidence

- `src/elspeth/mcp/server.py:812` - `if row.status == "completed":`
- `src/elspeth/contracts/enums.py:203-204` - `CallStatus.SUCCESS = "success"`
- 100% of successful calls misclassified

## Impact

- User-facing impact: Completely broken LLM usage reporting
- Data integrity: None (MCP is debugging tool)

## Proposed Fix

- Change to `if row.status == "success":` or use `CallStatus.SUCCESS.value`

## Acceptance Criteria

- Successful calls correctly counted as successful
