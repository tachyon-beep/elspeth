# Bug Report: TokenManager.update_row_data drops lineage metadata

## Summary

- TokenManager.update_row_data recreates TokenInfo without fork_group_id/join_group_id/expand_group_id, so lineage metadata is lost any time this helper is used.

## Severity

- Severity: minor
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-01-30
- Related run/issue ID: N/A

## Environment

- Commit/branch: Unknown
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Unknown

## Agent Context (if relevant)

- Goal or task prompt: You are a static analysis agent doing a deep bug audit. Target file: /home/john/elspeth-rapid/src/elspeth/engine/tokens.py
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Create a TokenInfo that includes lineage metadata (e.g., fork_group_id set) via fork/expand/coalesce paths.
2. Call TokenManager.update_row_data(token, new_data).
3. Inspect the returned TokenInfo: fork_group_id/join_group_id/expand_group_id are None.

## Expected Behavior

- update_row_data should preserve all TokenInfo lineage fields (fork_group_id, join_group_id, expand_group_id) when updating row_data.

## Actual Behavior

- update_row_data returns a new TokenInfo that only preserves branch_name; all group IDs are dropped.

## Evidence

- update_row_data only copies row_id, token_id, row_data, branch_name. `src/elspeth/engine/tokens.py:206-225`
- TokenInfo contract explicitly includes fork_group_id/join_group_id/expand_group_id as part of token identity. `src/elspeth/contracts/identity.py:10-32`

## Impact

- User-facing impact: Potentially incorrect or missing lineage metadata for tokens in memory after transforms that use update_row_data.
- Data integrity / security impact: Token lineage breaks in memory; downstream components that rely on these fields (telemetry, recovery, future audit logic) can lose fork/join/expand grouping context.
- Performance or cost impact: None.

## Root Cause Hypothesis

- update_row_data reconstructs TokenInfo but omits fork_group_id/join_group_id/expand_group_id, unintentionally discarding lineage metadata.

## Proposed Fix

- Code changes (modules/files):
  - Preserve fork_group_id, join_group_id, expand_group_id in `TokenManager.update_row_data()` when constructing the new TokenInfo. `src/elspeth/engine/tokens.py`
- Config or schema changes: None
- Tests to add/update:
  - Unit test for update_row_data that verifies all TokenInfo lineage fields are preserved.
- Risks or migration steps:
  - Low risk; only affects in-memory TokenInfo and should be fully backward compatible.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `src/elspeth/contracts/identity.py:10-32` (TokenInfo defines lineage fields as part of token identity).
- Observed divergence: update_row_data drops lineage fields instead of preserving token identity across updates.
- Reason (if known): Likely oversight in helper implementation.
- Alignment plan or decision needed: Update update_row_data to carry forward lineage fields.

## Acceptance Criteria

- update_row_data preserves fork_group_id, join_group_id, and expand_group_id.
- Added test demonstrates preservation for forked/expanded/coalesced tokens.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/`
- New tests required: yes, unit test covering update_row_data lineage preservation.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `src/elspeth/contracts/identity.py` (TokenInfo contract)
