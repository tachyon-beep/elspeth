# Bug Report: explain() hides audit corruption when token exists but source row missing or run mismatch

## Summary

- `explain()` returns `None` when a token exists but its source row cannot be resolved, silently masking audit DB corruption or run mismatch instead of crashing per Tier 1 trust rules.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-01-30
- Related run/issue ID: N/A

## Environment

- Commit/branch: 17f7293805c0c36aa59bf5fad0f09e09c3035fc9
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: SQLite audit DB with a token whose row record was deleted (simulated corruption)

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `/home/john/elspeth-rapid/src/elspeth/core/landscape/lineage.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Create a run, row, and token (normal pipeline execution).
2. Manually delete the row from `rows` while leaving the token intact (e.g., via direct SQL with foreign_keys disabled).
3. Call `explain(recorder, run_id, token_id=<token_id>)`.

## Expected Behavior

- `explain()` raises a hard error (e.g., `ValueError`) indicating audit integrity violation when a token references a missing row or the row belongs to a different run.

## Actual Behavior

- `explain()` returns `None`, which the CLI/TUI interprets as “not found,” masking audit DB corruption or run mismatch.

## Evidence

- `src/elspeth/core/landscape/lineage.py:142-150` returns `None` when `recorder.explain_row(...)` returns `None`, even if a valid token was found.
- `src/elspeth/core/landscape/recorder.py:1915-1938` shows `explain_row()` returns `None` if the row is missing or `run_id` mismatches, which propagates to a silent `None` in `explain()`.

## Impact

- User-facing impact: CLI/TUI shows “not found” for tokens that do exist, misleading operators during incident response.
- Data integrity / security impact: Violates Tier 1 audit integrity by silently masking missing audit records instead of crashing.
- Performance or cost impact: None.

## Root Cause Hypothesis

- `explain()` treats missing `source_row` as a normal “not found” case even after confirming the token exists, conflating user lookup misses with audit DB corruption or run mismatch.

## Proposed Fix

- Code changes (modules/files):
  - `src/elspeth/core/landscape/lineage.py`: after retrieving the token, explicitly verify the row exists and belongs to `run_id`; if not, raise a `ValueError` (audit integrity violation) instead of returning `None`.
- Config or schema changes: Unknown
- Tests to add/update:
  - Update `tests/property/core/test_lineage_properties.py` to expect a `ValueError` when a token exists but `explain_row()` returns `None` due to missing/mismatched row.
- Risks or migration steps:
  - Existing callers will now see an explicit error instead of “not found” when the audit DB is inconsistent or `run_id` is wrong for a token.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:34-41` (Tier 1 audit data must crash on anomalies, no silent recovery).
- Observed divergence: `explain()` silently returns `None` when a token’s source row is missing or mismatched, masking audit anomalies.
- Reason (if known): Behavior likely optimized for “not found” lookups, but it conflates external lookup errors with internal audit corruption.
- Alignment plan or decision needed: Enforce Tier 1 behavior by raising on missing/mismatched row once a token is confirmed.

## Acceptance Criteria

- If a token exists but its source row is missing or belongs to a different run, `explain()` raises a clear audit integrity error.
- Existing “row not found” behavior remains unchanged when token is not found.
- Tests cover the token-present/row-missing case and assert an exception.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/property/core/test_lineage_properties.py -k source_row_not_found`
- New tests required: yes, update the property test to assert a raised error.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md` (Tier 1 audit integrity rules)
