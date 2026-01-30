# Bug Report: get_outcome_analysis counts fork/join operations across all runs (missing run_id filter)

## Summary

- Fork/join counts in `get_outcome_analysis()` aggregate across the entire `tokens` table because the queries don’t scope to the requested `run_id`, so per-run outcome analysis is incorrect when multiple runs exist.

## Severity

- Severity: minor
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-01-30
- Related run/issue ID: N/A

## Environment

- Commit/branch: 290716a2563735271d162f1fac7d40a7690e6ed6 (fix/RC1-RC2-bridge)
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Unknown

## Agent Context (if relevant)

- Goal or task prompt: static analysis deep bug audit on `src/elspeth/mcp/server.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Create or use an audit DB with at least two runs that include fork/join operations.
2. Call `get_outcome_analysis(run_id=<run_A>)`.
3. Observe `summary.fork_operations` / `summary.join_operations`.

## Expected Behavior

- Fork/join counts are computed only from tokens belonging to the specified `run_id`.

## Actual Behavior

- Fork/join counts include tokens from other runs, inflating counts for the requested run.

## Evidence

- `src/elspeth/mcp/server.py:931-946` shows `fork_count` and `join_count` queries on `tokens_table` without any `run_id` filter.
- `src/elspeth/core/landscape/schema.py:117-128` shows `tokens_table` has no `run_id`, so a run filter requires a join (e.g., via `rows_table`).

## Impact

- User-facing impact: Misleading outcome diagnostics for a specific run, especially in multi-run databases.
- Data integrity / security impact: No direct data corruption, but incorrect operational insight.
- Performance or cost impact: None significant.

## Root Cause Hypothesis

- The fork/join aggregation queries omit run scoping and rely on a table that lacks `run_id`, so they implicitly aggregate across all runs.

## Proposed Fix

- Code changes (modules/files):
  - `src/elspeth/mcp/server.py`: Join `tokens_table` to `rows_table` (or use `token_outcomes_table`) and filter on `run_id` when counting distinct `fork_group_id`/`join_group_id`.
- Config or schema changes: None.
- Tests to add/update:
  - Add a unit/integration test for `get_outcome_analysis` that seeds two runs with different fork/join counts and verifies per-run isolation.
- Risks or migration steps:
  - Low risk; query becomes more accurate and slightly more expensive due to join.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): Unknown
- Observed divergence: Unknown
- Reason (if known): Unknown
- Alignment plan or decision needed: Unknown

## Acceptance Criteria

- `get_outcome_analysis(run_id=X)` returns fork/join counts that match only tokens from run X.
- A multi-run test fixture demonstrates correct isolation.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/`
- New tests required: yes, add a focused test for run-scoped fork/join counts in outcome analysis.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: Unknown
---
# Bug Report: LLM usage report misclassifies call status (uses “completed” instead of “success”)

## Summary

- `get_llm_usage_report()` classifies successful LLM calls by checking `row.status == "completed"`, but call statuses are stored as `"success"` or `"error"`, causing success counts to be zero and failures inflated.

## Severity

- Severity: minor
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-01-30
- Related run/issue ID: N/A

## Environment

- Commit/branch: 290716a2563735271d162f1fac7d40a7690e6ed6 (fix/RC1-RC2-bridge)
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Unknown

## Agent Context (if relevant)

- Goal or task prompt: static analysis deep bug audit on `src/elspeth/mcp/server.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Run a pipeline that performs LLM calls successfully.
2. Call `get_llm_usage_report(run_id=<run_id>)`.
3. Inspect `by_plugin[*].successful` and `failed` counts.

## Expected Behavior

- Successful calls are counted when status is `"success"`; failed calls are counted when status is `"error"`.

## Actual Behavior

- Successful count remains zero because the code checks for `"completed"`, which is not a valid call status.

## Evidence

- `src/elspeth/mcp/server.py:812-815` uses `if row.status == "completed": ... else: failed`.
- `src/elspeth/contracts/enums.py:197-204` defines `CallStatus` values as `"success"` and `"error"`.
- `src/elspeth/core/landscape/recorder.py:1881-1887` stores `status.value` into `calls.status`, confirming persisted values are `"success"`/`"error"`.

## Impact

- User-facing impact: LLM usage reports show incorrect success/failure metrics, misleading operational decisions.
- Data integrity / security impact: No corruption, but analytic outputs are wrong.
- Performance or cost impact: None significant.

## Root Cause Hypothesis

- Hard-coded string `"completed"` in the LLM usage report doesn’t align with the `CallStatus` enum values used in storage.

## Proposed Fix

- Code changes (modules/files):
  - `src/elspeth/mcp/server.py`: Compare `row.status` to `"success"` (or `CallStatus.SUCCESS.value`) instead of `"completed"`.
- Config or schema changes: None.
- Tests to add/update:
  - Add a test for `get_llm_usage_report` verifying correct success/failure aggregation given stored statuses.
- Risks or migration steps:
  - Low risk; purely fixes reporting logic.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): Unknown
- Observed divergence: Unknown
- Reason (if known): Unknown
- Alignment plan or decision needed: Unknown

## Acceptance Criteria

- LLM usage report counts successes when call status is `"success"` and failures when `"error"`.
- Test fixture with mixed statuses passes.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/`
- New tests required: yes, add a focused test for LLM call status aggregation.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: Unknown
