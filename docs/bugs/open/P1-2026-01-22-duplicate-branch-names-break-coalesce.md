# Bug Report: Duplicate Fork/Coalesce Branch Names Break Merge Semantics

## Summary

`fork_to` and `coalesce.branches` allow duplicate branch names; coalesce tracking uses a dict keyed by branch name, so duplicates overwrite tokens and can prevent `require_all/quorum` merges from ever completing.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex (static analysis agent)
- Date: 2026-01-22
- Related run/issue ID: Unknown

## Environment

- Commit/branch: main (d8df733)
- OS: Linux
- Python version: 3.12+
- Config profile / env vars: Pipeline with fork and coalesce configuration
- Data set or fixture: Any

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit for `src/elspeth/core/config.py`
- Model/version: GPT-5 (Codex)
- Tooling and permissions (sandbox/approvals): read-only sandbox, approvals disabled
- Determinism details (seed, run ID): Unknown
- Notable tool calls or steps: Reviewed config.py, dag.py, coalesce_executor.py

## Steps To Reproduce

1. Define a gate with `routes: {all: fork}` and `fork_to: ["path_a", "path_a"]` (duplicate branch)
2. Define a coalesce with `branches: ["path_a", "path_a"]` and `policy: require_all`
3. Run the pipeline
4. Coalesce never completes because only one unique branch can arrive

## Expected Behavior

- Duplicate branch names are rejected at config validation for both `fork_to` and `coalesce.branches`

## Actual Behavior

- Duplicates are accepted
- Coalesce overwrites arrivals and may stall indefinitely or drop a token

## Evidence

- Logs or stack traces: Unknown
- Artifacts (paths, IDs, screenshots):
  - `src/elspeth/core/config.py:238` validates `fork_to` only for reserved labels, not uniqueness
  - `src/elspeth/core/config.py:327` defines `CoalesceSettings.branches` without uniqueness validation
  - `src/elspeth/engine/coalesce_executor.py:172` stores arrivals by `branch_name`, overwriting duplicates
  - `src/elspeth/engine/coalesce_executor.py:195` compares `arrived_count` to `len(settings.branches)`, so duplicates can prevent merges
  - `src/elspeth/core/dag.py:415` maps `branch_to_coalesce` by branch name, overwriting duplicates across coalesce configs
- Minimal repro input (attach or link): Config YAML with duplicate branch names in fork_to or coalesce.branches

## Impact

- User-facing impact: Pipelines can hang at coalesce or route fewer results than expected
- Data integrity / security impact: Tokens can be overwritten, causing silent loss of branch results
- Performance or cost impact: Runs may stall until timeout or require manual intervention

## Root Cause Hypothesis

Missing uniqueness checks for branch lists (`fork_to`, `coalesce.branches`) and across coalesce configurations.

## Proposed Fix

- Code changes (modules/files): Add uniqueness validation in `GateSettings.validate_fork_to_labels` and a new validator in `CoalesceSettings` (or `ElspethSettings`) to enforce unique branch names. Optionally validate global uniqueness across coalesce definitions.
- Config or schema changes: None
- Tests to add/update: Add tests for duplicate `fork_to` and duplicate `coalesce.branches` in `tests/core/test_config.py`
- Risks or migration steps: Configs with duplicate branch names will fail fast

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): Unknown
- Observed divergence: Branch identifiers are treated as unique keys at runtime but not enforced in config
- Reason (if known): Unknown
- Alignment plan or decision needed: Enforce uniqueness at config validation

## Acceptance Criteria

- Duplicate branch names in `fork_to` or `coalesce.branches` are rejected with a clear error
- Coalesce merges complete when all distinct branches arrive

## Tests

- Suggested tests to run: `pytest tests/core/test_config.py -k coalesce`
- New tests required: Yes, duplicate branch validation

## Notes / Links

- Related issues/PRs:
  - Related to `docs/bugs/open/P2-2026-01-22-coalesce-duplicate-branch-overwrite.md` (runtime manifestation)
- Related design docs: Unknown

## Verification Status

- [ ] Bug confirmed via reproduction
- [ ] Root cause verified
- [ ] Fix implemented
- [ ] Tests added
- [ ] Fix verified
