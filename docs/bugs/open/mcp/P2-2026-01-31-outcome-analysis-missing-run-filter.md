# Bug Report: get_outcome_analysis counts fork/join operations across all runs

## Summary

- Fork/join count queries in `get_outcome_analysis` have no `run_id` filter, counting operations across all runs in the database.

## Severity

- Severity: moderate
- Priority: P2

## Reporter

- Name or handle: Codex (triaged by Claude)
- Date: 2026-01-31

## Evidence

- `src/elspeth/mcp/server.py:931-946` - fork_count query has no run_id filter
- `tokens_table` lacks `run_id` column, would need join through `rows_table`

## Impact

- User-facing impact: Incorrect counts in multi-run databases
- Data integrity: None (MCP is debugging tool)

## Proposed Fix

- Add run_id filter via join to rows_table or token_outcomes_table

## Acceptance Criteria

- Fork/join counts scoped to requested run_id
