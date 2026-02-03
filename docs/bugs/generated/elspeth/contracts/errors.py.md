# Bug Report: Backwards-Compat Alias in Coalesce Failure Schema Violates No-Legacy Policy and Creates Ambiguous Audit Payloads

## Summary

- `CoalesceFailureReason` defines `branches_arrived` as a backwards-compat alias of `actual_branches`, violating the no-legacy policy and allowing coalesce failure payloads to omit the canonical field.

## Severity

- Severity: minor
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-03
- Related run/issue ID: N/A

## Environment

- Commit/branch: 3aa2fa93d8ebd2650c7f3de23b318b60498cd81c / RC2.3-pipeline-row
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Unknown

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `src/elspeth/contracts/errors.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Run a pipeline that triggers a coalesce failure (e.g., `select_branch_not_arrived`).
2. Inspect the recorded coalesce failure payload in the audit trail.

## Expected Behavior

- Coalesce failure payloads should use a single canonical field for arrived branches (e.g., `actual_branches`) with no backwards-compat alias.

## Actual Behavior

- The contract includes `branches_arrived` as a backwards-compat alias, and coalesce failure payloads are recorded with `branches_arrived` (not `actual_branches`), creating ambiguity and violating the no-legacy policy.

## Evidence

- `src/elspeth/contracts/errors.py:22` defines `CoalesceFailureReason` and includes a backwards-compat alias.
- `src/elspeth/contracts/errors.py:34` explicitly declares `branches_arrived` as “backwards compat.”
- `src/elspeth/engine/coalesce_executor.py:350` records error payloads using `branches_arrived`, not `actual_branches`.

## Impact

- User-facing impact: Audit consumers relying on the canonical field may see missing data or need to special-case the alias.
- Data integrity / security impact: Audit schema ambiguity undermines strict auditability and violates the no-legacy policy.
- Performance or cost impact: Minimal, but increases maintenance and audit query complexity.

## Root Cause Hypothesis

- `CoalesceFailureReason` deliberately retains a backwards-compat alias, which is prohibited by the project’s no-legacy policy and enables non-canonical payloads.

## Proposed Fix

- Code changes (modules/files): Remove `branches_arrived` from `CoalesceFailureReason` and standardize on `actual_branches` in the contract; update producers to emit `actual_branches` only.
- Config or schema changes: None.
- Tests to add/update: Add a contract test asserting coalesce failure payloads include `actual_branches` and do not include `branches_arrived`.
- Risks or migration steps: Update any consumers or queries that currently read `branches_arrived`.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:841`
- Observed divergence: Backwards-compat alias field is present in a core contract.
- Reason (if known): Retention of legacy field name for compatibility.
- Alignment plan or decision needed: Remove alias and update all call sites to the canonical field.

## Acceptance Criteria

- `branches_arrived` is removed from `CoalesceFailureReason`.
- Coalesce failure payloads record `actual_branches` consistently.
- Tests verify the canonical field and absence of the alias.

## Tests

- Suggested tests to run: Unknown.
- New tests required: Yes, contract-level test for coalesce failure payload keys.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md:841`
