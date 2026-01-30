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

- `src/elspeth/core/dag.py:449-455` - gate copies raw `config["schema"]`
- Line 557-562 - config gate also copies raw schema
- `_get_effective_guaranteed_fields()` at lines 1217-1241 checks upstream for gates with no own guarantees
- But gates DO get their own guarantees from the raw schema copy, which may not include computed fields from LLM transforms

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
