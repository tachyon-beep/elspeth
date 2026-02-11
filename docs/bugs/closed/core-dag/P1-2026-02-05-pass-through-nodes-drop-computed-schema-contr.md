# Bug Report: Pass-Through Nodes Drop Computed Schema Contracts (Gate/Coalesce)

## Summary

- Gate and coalesce nodes inherit raw upstream `schema` dicts instead of computed `output_schema_config`, so audit metadata and contract fields (e.g., LLM guaranteed/audit fields) are silently dropped at pass-through points.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: 1c70074e
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: N/A

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit for `src/elspeth/core/dag.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Configure a transform that computes `_output_schema_config` (e.g., any LLM transform that adds guaranteed/audit fields) and place a config gate or coalesce downstream.
2. Build the graph via `ExecutionGraph.from_plugin_instances(...)`.
3. Inspect `graph.get_node_info(gate_or_coalesce_id).config["schema"]` or the `schema_config` recorded in Landscape for those nodes.

## Expected Behavior

- Pass-through nodes (gates/coalesce) should preserve and record the **computed** schema contract (including guaranteed/audit fields) from upstream, so audit metadata reflects the actual data contract.

## Actual Behavior

- Gate and coalesce nodes copy the **raw** upstream schema dict (from config), which omits computed contract fields. The audit trail and node schema metadata do not reflect actual guaranteed/audit fields.

## Evidence

- Gate node schema is copied from raw upstream config, not computed schema: `src/elspeth/core/dag.py:449`, `src/elspeth/core/dag.py:455`.
- Config gate schema is copied from raw upstream config: `src/elspeth/core/dag.py:549`.
- Coalesce schema is copied from raw upstream config for audit: `src/elspeth/core/dag.py:779`, `src/elspeth/core/dag.py:789`.
- Landscape registration uses `node_info.config["schema"]` for audit schema_config, so dropped fields are persisted: `src/elspeth/engine/orchestrator/core.py:755`.

## Impact

- User-facing impact: Audit metadata for gate/coalesce nodes omits computed contract fields, making lineage and schema auditing incomplete or misleading.
- Data integrity / security impact: Violates auditability standard (“if it’s not recorded, it didn’t happen”) for computed contract fields.
- Performance or cost impact: None.

## Root Cause Hypothesis

- `ExecutionGraph.from_plugin_instances()` propagates raw `config["schema"]` through pass-through nodes instead of using computed `output_schema_config` when available, and the orchestrator records that raw schema in Landscape.

## Proposed Fix

- Code changes (modules/files):
  - Update gate/config gate schema propagation to use computed schema config when available (derive via `_get_schema_config_from_node` and store normalized `SchemaConfig.to_dict()`), in `src/elspeth/core/dag.py`.
  - Update coalesce schema propagation to use computed schema configs from upstream branches before audit registration, in `src/elspeth/core/dag.py`.
- Config or schema changes: None.
- Tests to add/update:
  - Add a DAG test asserting that gate/coalesce node `config["schema"]` includes computed guaranteed/audit fields when upstream transform sets `_output_schema_config`.
- Risks or migration steps:
  - If `config["schema"]` participates in hashing or topology validation, ensure computed contract fields don’t unintentionally change node ID or topology hash without an explicit migration decision.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md` Auditability Standard (“No inference - if it’s not recorded, it didn’t happen”).
- Observed divergence: Computed contract fields are not recorded for gate/coalesce nodes, so the audit record does not reflect the true data contract at those nodes.
- Reason (if known): Schema propagation uses raw config dicts, ignoring computed `output_schema_config`.
- Alignment plan or decision needed: Decide whether computed schema contract should be stored in node config for audit (recommended), and update propagation accordingly.

## Acceptance Criteria

- Gate and coalesce nodes store schema configs that include computed guaranteed/audit fields from upstream transforms.
- Landscape node registrations reflect those computed fields.
- New test demonstrates the corrected behavior.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/core/test_dag.py -k \"schema\"`
- New tests required: yes, add a targeted DAG test for computed schema propagation through gate/coalesce.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md` auditability standard

## Closure Update (2026-02-11)

- Status: Closed after re-verification against current code.
- Verification summary: pass-through schema propagation now uses computed schema selection rather than copying only raw upstream config.
- Evidence:
  - `src/elspeth/core/dag/builder.py:492` assigns gate schema via `_best_schema_dict(producer_id)`.
  - `src/elspeth/core/dag/builder.py:711` and `src/elspeth/core/dag/builder.py:727` assign coalesce/deferred gate schemas via `_best_schema_dict(...)`.
  - `tests/unit/core/test_dag_schema_propagation.py` passes with coverage for computed schema propagation.
