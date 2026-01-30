# Bug Report: BaseLLMTransform output_schema omits LLM-added fields

## Summary

- `BaseLLMTransform` sets `output_schema = input_schema` but `process()` adds fields like `_usage`, `_model`, `_template_hash` that aren't in the schema.

## Severity

- Severity: minor
- Priority: P3

## Reporter

- Name or handle: Codex (triaged by Claude)
- Date: 2026-01-31

## Evidence

- `src/elspeth/plugins/llm/base.py:231-232` - `self.output_schema = schema` (same as input)
- Lines 329-341 - transform adds `_usage`, `_model`, etc.
- Output rows don't match declared schema

## Proposed Fix

- Generate output_schema including LLM-added fields

## Acceptance Criteria

- Output schema accurately reflects all emitted fields
