# Bug Report: TokenManager.update_row_data drops lineage metadata

## Summary

- `update_row_data()` creates a new `TokenInfo` with only basic fields, dropping `fork_group_id`, `join_group_id`, and `expand_group_id` lineage metadata.

## Severity

- Severity: moderate
- Priority: P2

## Reporter

- Name or handle: Codex (triaged by Claude)
- Date: 2026-01-31

## Evidence

- `src/elspeth/engine/tokens.py:206-225` - `update_row_data()` creates new TokenInfo with only `row_id`, `token_id`, `row_data`, `branch_name`
- Missing: `fork_group_id`, `join_group_id`, `expand_group_id`
- `TokenInfo` contract at `src/elspeth/contracts/identity.py:10-32` defines these fields

## Impact

- User-facing impact: Lineage metadata lost after row data updates
- Data integrity: Fork/join/expand relationships not preserved

## Proposed Fix

- Preserve all TokenInfo fields when updating row_data

## Acceptance Criteria

- `update_row_data()` preserves fork_group_id, join_group_id, expand_group_id

## Verification (2026-02-01)

**Status: STILL VALID**

- `update_row_data()` still returns a new `TokenInfo` without preserving lineage fields. (`src/elspeth/engine/tokens.py:211-229`)
