# Bug Report: BaseLLMTransform Output Omits Model Metadata

## Summary

- LLM transform responses don't include model version and metadata in output, reducing auditability of LLM decisions.

## Severity

- Severity: trivial
- Priority: P3

## Reporter

- Name or handle: Branch Bug Scan
- Date: 2026-01-25
- Related run/issue ID: BUG-BASE-01

## Evidence

- `src/elspeth/plugins/llm/base.py` - Output missing model/version fields

## Impact

- Observability: Cannot determine which model version produced output

## Proposed Fix

- Include model metadata in transform output:
  ```python
  output = {
      "response": llm_response,
      "_model": "gpt-4",
      "_model_version": "0613",
      "_usage": usage_stats,
  }
  ```

## Acceptance Criteria

- All LLM outputs include model metadata

## Tests

- New tests required: yes, metadata presence test
