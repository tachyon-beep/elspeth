# Bug Report: explain() Allows Missing Parent Relationships Without Error

## Summary

- `explain()` returns a lineage result even when a token indicates it should have parents (`fork_group_id`, `join_group_id`, or `expand_group_id`) but `token_parents` has no entries, silently masking audit integrity violations.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: 1c70074ef3b71e4fe85d4f926e52afeca50197ab (RC2.3-pipeline-row)
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: In-memory LandscapeDB with a manually created token

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `src/elspeth/core/landscape/lineage.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Create a run, row, and token via `LandscapeRecorder`, but create the token with `fork_group_id`/`join_group_id`/`expand_group_id` using `create_token()` (not `fork_token`, `coalesce_tokens`, or `expand_token`), so no `token_parents` rows are recorded.
2. Record a terminal outcome for the token so `explain()` will resolve it.
3. Call `explain(recorder, run_id=..., token_id=...)`.

## Expected Behavior

- `explain()` should raise an error indicating audit integrity violation when a token that implies parent relationships (via group IDs) has no `token_parents` entries.

## Actual Behavior

- `explain()` returns a `LineageResult` with an empty `parent_tokens` list, silently masking missing lineage links.

## Evidence

- `src/elspeth/core/landscape/lineage.py:168-183` only validates missing parent tokens when `token_parents` rows exist; it does not enforce that tokens with group IDs must have parents, so empty `token_parents` yields silent omission.
- `docs/design/subsystems/06-token-lifecycle.md:507-515` specifies audit invariants: parent relationships must be recorded and lineage must be traversable.

## Impact

- User-facing impact: `explain()` can report incomplete lineage for fork/coalesce/expand paths without warning.
- Data integrity / security impact: Violates Tier 1 audit integrity expectations; missing parent links are not surfaced.
- Performance or cost impact: None.

## Root Cause Hypothesis

- `explain()` does not validate consistency between token metadata (`fork_group_id`, `join_group_id`, `expand_group_id`) and the existence of `token_parents` rows, so lineage breaks are not detected.

## Proposed Fix

- Code changes (modules/files): Add a guard in `src/elspeth/core/landscape/lineage.py` after fetching `parents` to raise `ValueError` if `token.fork_group_id`, `token.join_group_id`, or `token.expand_group_id` is set but `parents` is empty.
- Config or schema changes: None.
- Tests to add/update: Add a test in `tests/core/landscape/test_lineage.py` that creates a token with a group ID but no `token_parents` and asserts `explain()` raises an audit integrity violation.
- Risks or migration steps: None.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `docs/design/subsystems/06-token-lifecycle.md:507-515`
- Observed divergence: `explain()` does not enforce the “parent relationships recorded” invariant and can return lineage with missing parent links.
- Reason (if known): Unknown.
- Alignment plan or decision needed: Enforce invariant in `explain()` by validating group IDs against `token_parents`.

## Acceptance Criteria

- `explain()` raises a clear audit integrity error when a token has `fork_group_id`/`join_group_id`/`expand_group_id` but no parent relationships.
- Existing `explain()` behavior remains unchanged for tokens without group IDs.
- New test passes and confirms the guard.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/core/landscape/test_lineage.py -k "parent"`
- New tests required: yes, add a regression test for missing parent relationships with group IDs.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `docs/design/subsystems/06-token-lifecycle.md`
