# Bug Report: Duplicate Fork/Coalesce Branch Names Accepted, Causing Stalls and Token Overwrites

## Summary

- DAG builder accepts duplicate `branch_name` values in fork_to_paths configuration, causing coalesce config maps to silently overwrite earlier entries, leading to tokens never reaching coalesce nodes and pipeline stalls.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Branch Bug Scan (fix/rc1-bug-burndown-session-4)
- Date: 2026-01-25
- Related run/issue ID: BUG-DAG-01

## Environment

- Commit/branch: fix/rc1-bug-burndown-session-4
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Fork/coalesce DAG with duplicate branch names

## Agent Context (if relevant)

- Goal or task prompt: Static analysis agent doing a deep bug audit of dag.py
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Configure a gate with fork_to_paths using duplicate branch names:
   ```yaml
   fork_to_paths:
     - branch_name: "analysis"
       nodes: [transform_a]
     - branch_name: "analysis"  # DUPLICATE
       nodes: [transform_b]
   ```
2. Configure coalesce node expecting both branches.
3. Run pipeline with forking gate.

## Expected Behavior

- DAG builder should reject duplicate branch names with validation error at config parse time.

## Actual Behavior

- DAG builder accepts duplicate names.
- Coalesce config maps branch_name → node_id.
- Last duplicate silently overwrites earlier entries.
- Tokens on earlier branch never reach coalesce (map entry missing).
- Pipeline stalls waiting for missing tokens.

## Evidence

- `src/elspeth/core/dag.py` - DAG builder does not validate branch name uniqueness in fork_to_paths
- Coalesce configuration creates map `branch_to_coalesce = {branch_name: coalesce_node_id}`
- Dict creation with duplicate keys → last value wins, earlier entries lost

## Impact

- User-facing impact: Pipeline stalls indefinitely waiting for tokens that will never arrive. No error message, silent hang.
- Data integrity / security impact: Rows on earlier duplicate branch never processed, silent data loss.
- Performance or cost impact: Pipeline runs forever until manually killed, wasting resources.

## Root Cause Hypothesis

- DAG builder lacks validation for branch name uniqueness within a single fork_to_paths configuration.

## Proposed Fix

- Code changes (modules/files):
  ```python
  # In DAG builder (src/elspeth/core/dag.py)
  seen_branches = set()
  for branch in gate_config.fork_to_paths:
      if branch.branch_name in seen_branches:
          raise ValueError(
              f"Duplicate branch name '{branch.branch_name}' in gate '{gate_id}'. "
              "Each branch must have a unique name within fork_to_paths."
          )
      seen_branches.add(branch.branch_name)
  ```

- Config or schema changes: None (validation only).

- Tests to add/update:
  - `test_duplicate_branch_names_rejected()` - Verify DAG builder raises ValueError
  - `test_unique_branch_names_accepted()` - Verify valid config passes

- Risks or migration steps: Existing configs with duplicates will now fail validation (breaking change acceptable per CLAUDE.md).

## Architectural Deviations

- Spec or doc reference: N/A (no spec explicitly requires unique branch names, but it's implied by map structure)
- Observed divergence: Silent data loss via dict overwrite violates fail-fast principle.
- Reason (if known): Missing validation at config parse time.
- Alignment plan or decision needed: Add uniqueness validation to DAG builder.

## Acceptance Criteria

- DAG builder rejects configs with duplicate branch names with clear error message.
- Existing unique branch name configs continue to work.

## Tests

- Suggested tests to run: `pytest tests/core/test_dag_builder.py`
- New tests required: yes (2 tests listed above)

## Notes / Links

- Related issues/PRs: May explain user-reported fork/coalesce stalls
- Related design docs: `docs/bugs/BRANCH_BUG_TRIAGE_2026-01-25.md`
