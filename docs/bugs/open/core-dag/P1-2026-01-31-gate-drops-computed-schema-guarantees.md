# Bug Report: Gate nodes drop computed schema guarantees across pass-through

## Summary

- Gate nodes copy raw `config["schema"]` without preserving computed `output_schema_config` from upstream transforms, causing valid pipelines to fail DAG contract validation.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex (triaged by Claude)
- Date: 2026-01-31
- Related run/issue ID: N/A

## Evidence

- `src/elspeth/core/dag.py:446-456` - gate nodes overwrite `node_config["schema"]` with the **raw** upstream schema config (`config["schema"]`).
- `src/elspeth/core/dag.py:460-472` - `output_schema_config` is only taken from the gate instance itself (typically `None`), so computed upstream schema config is not propagated.
- `src/elspeth/core/dag.py:1088-1122` - `_get_schema_config_from_node()` prefers `output_schema_config` when present, otherwise parses the raw `config["schema"]`.
- Because gate nodes lack `output_schema_config`, they fall back to raw schema and lose upstream computed guarantees (LLM `_output_schema_config`).

## Impact

- User-facing impact: Valid pipelines fail DAG validation with false contract violations
- Data integrity / security impact: None (fails safe, but incorrectly)
- Performance or cost impact: Developer time debugging false validation failures

## Root Cause Hypothesis

- When an LLM transform computes `output_schema_config` with additional guaranteed fields (like `*_usage`, `*_model`), gates only copy the raw schema config, not the computed schema.

## Proposed Fix

- Code changes:
  - Gates should inherit/pass through upstream's `output_schema_config` rather than raw config schema
  - Or: Gates with no schema should be transparent in contract validation
- Tests to add/update:
  - Add test: LLM transform -> gate -> downstream requiring LLM fields, assert validation passes

## Acceptance Criteria

- Gates correctly pass through upstream's computed guaranteed fields
- DAG validation passes for valid transform->gate->transform chains

## Verification (2026-02-01)

**Status: STILL VALID**

- Gate nodes still copy raw schema config and do not inherit upstream `output_schema_config`, so computed guarantees are dropped in contract validation. (`src/elspeth/core/dag.py:446-472`, `src/elspeth/core/dag.py:1088-1122`)
