# Bug Report: Gate nodes drop computed schema guarantees across pass-through, causing false DAG contract violations

## Summary

- Gate nodes copy only the upstream *raw* schema config into their own config, so computed schema guarantees (e.g., LLM metadata fields) are lost at pass-through gates and downstream `required_input_fields` can fail validation even though the upstream transform actually guarantees them.

## Severity

- Severity: major
- Priority: P1

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

- Goal or task prompt: static analysis bug audit of `/home/john/elspeth-rapid/src/elspeth/core/dag.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Configure an LLM transform with an explicit schema (mode `strict`/`free`) and a `response_field` (e.g., `llm_response`), so it computes additional guaranteed fields like `llm_response_usage` and `llm_response_model`.
2. Add a **config gate** immediately after that LLM transform.
3. Add a downstream transform that declares `required_input_fields: ["llm_response_usage"]`.
4. Build the graph via `ExecutionGraph.from_plugin_instances(...)` (or run `elspeth validate`).

## Expected Behavior

- DAG validation should recognize the LLM transform’s computed guarantees across the gate (pass-through) and allow the downstream required fields.

## Actual Behavior

- DAG validation treats the gate as having only the *raw* schema config (without computed guarantees), so it reports missing required fields and fails graph construction.

## Evidence

- Gate nodes copy the upstream **raw** schema config into their own config (no propagation of computed schema config):
  - `/home/john/elspeth-rapid/src/elspeth/core/dag.py:446-472`
  - `/home/john/elspeth-rapid/src/elspeth/core/dag.py:545-562`
- `_get_effective_guaranteed_fields` stops at a gate if it has any guarantees in its own config, instead of always inheriting upstream computed guarantees:
  - `/home/john/elspeth-rapid/src/elspeth/core/dag.py:1217-1241`
- LLM transforms explicitly compute additional guaranteed fields into `_output_schema_config`:
  - `/home/john/elspeth-rapid/src/elspeth/plugins/llm/base.py:234-248`

## Impact

- User-facing impact: Valid pipelines that place a gate after an LLM transform can fail validation if downstream transforms require LLM metadata fields that are guaranteed at runtime.
- Data integrity / security impact: Encourages users to remove `required_input_fields` or avoid gates, weakening contract validation and auditability.
- Performance or cost impact: Wasted configuration iterations; no direct runtime cost.

## Root Cause Hypothesis

- Gate nodes are populated with upstream **raw** `schema` config instead of the upstream computed `output_schema_config`, and `_get_effective_guaranteed_fields` treats gate-local guarantees as authoritative, so computed guarantees added by transforms (e.g., LLM metadata) don’t propagate past gates.

## Proposed Fix

- Code changes (modules/files):
  - `/home/john/elspeth-rapid/src/elspeth/core/dag.py`: When adding gate nodes (both plugin gates and config gates), propagate the upstream computed `output_schema_config` into the gate’s `output_schema_config` (or set `config["schema"]` from `output_schema_config.to_dict()` when present) so contract validation uses computed guarantees.
  - Optionally harden `_get_effective_guaranteed_fields` to always inherit from upstream for gates (pass-through nodes), regardless of gate-local config.
- Config or schema changes: None.
- Tests to add/update:
  - Add a DAG validation test where an upstream transform has computed `output_schema_config` guarantees and a gate is inserted; downstream `required_input_fields` should pass.
  - A regression case for an LLM transform with explicit schema + config gate + downstream requiring `*_usage`.
- Risks or migration steps:
  - Ensure that gate node config hashes remain stable if `schema` is serialized differently; if changing `config["schema"]`, verify deterministic hashing and checkpoint compatibility.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): Unknown
- Observed divergence: Pass-through gates do not preserve computed guarantees from upstream transforms.
- Reason (if known): Unknown
- Alignment plan or decision needed: Propagate upstream `output_schema_config` into gate nodes or treat gates as unconditional pass-through for guarantees.

## Acceptance Criteria

- A pipeline with LLM transform → config gate → downstream transform requiring LLM metadata fields validates successfully.
- Unit/property tests confirm gates preserve computed guarantees across pass-through.
- No regression in existing DAG validation behavior for non-gate paths.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/property/core/test_dag_properties.py -k gate`
- New tests required: yes, add a regression test for computed guarantees across gates.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: Unknown
