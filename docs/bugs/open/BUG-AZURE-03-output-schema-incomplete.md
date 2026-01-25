# Bug Report: AzureLLMTransform output_schema Omits LLM Response Fields

## Summary

- `output_schema` doesn't include actual LLM response fields (model, usage, finish_reason), causing schema validation mismatches.

## Severity

- Severity: minor
- Priority: P2

## Reporter

- Name or handle: Branch Bug Scan
- Date: 2026-01-25
- Related run/issue ID: BUG-AZURE-03

## Evidence

- `src/elspeth/plugins/llm/azure.py` - Schema missing response metadata fields

## Impact

- Schema completeness: Downstream transforms can't rely on schema contract

## Proposed Fix

- Add LLM response fields to output_schema:
  ```python
  output_schema: ClassVar[type[PluginSchema]] = LLMResponseSchema
  # Include: model, usage_tokens, finish_reason, etc.
  ```

## Acceptance Criteria

- output_schema includes all emitted fields

## Tests

- New tests required: yes, schema validation test
