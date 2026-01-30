# Bug Report: Multi-query config allows output-key collisions that silently overwrite LLM results

## Summary

- Multi-query transform config allows duplicate case_study/criterion names and collisions with reserved suffixes, causing later values to silently overwrite earlier ones via `output.update()`.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex (triaged by Claude)
- Date: 2026-01-31
- Related run/issue ID: N/A

## Evidence

- `src/elspeth/plugins/llm/multi_query.py:291-303` - `expand_queries()` builds `output_prefix = f"{case_study.name}_{criterion.name}"` without checking uniqueness
- Line 225 - `output_mapping` validation only checks non-empty
- Metadata suffixes (`_usage`, `_model`) could collide with user-defined suffixes
- Output is built via `output.update()` which silently overwrites duplicate keys

## Impact

- User-facing impact: Silent data loss - later LLM results overwrite earlier ones
- Data integrity / security impact: Audit trail contains incomplete/wrong data without any error
- Performance or cost impact: Wasted LLM calls for results that get overwritten

## Root Cause Hypothesis

- Missing validation for uniqueness of case_study.name + criterion.name combinations and collision detection with reserved suffixes.

## Proposed Fix

- Code changes:
  - Add `@model_validator(mode="after")` to MultiQuerySpec
  - Validate uniqueness of (case_study.name, criterion.name) pairs
  - Detect collisions with reserved suffixes (_usage, _model, _template_hash, _variables_hash)
- Tests to add/update:
  - Add config validation test with duplicate names, assert ValueError
  - Add test with suffix collision, assert ValueError

## Acceptance Criteria

- Duplicate case_study/criterion name combinations are rejected at config time
- Collisions with reserved suffixes are detected and rejected
- No silent overwrites possible in output
