## Summary

`OpenRouterBatch` classifies successful rows as errors when row data already contains key `error`.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `src/elspeth/plugins/llm/openrouter_batch.py`
- Function/Method: `_process_batch`, `_process_single_row`

## Evidence

- Source report: `docs/bugs/generated/plugins/llm/openrouter_batch.py.md`
- Error detection is keyed off `"error" in result`, which collides with user row fields.

## Root Cause Hypothesis

Dictionary-key sentinel for outcome encoding collides with valid payload shape.

## Suggested Fix

Use explicit typed/flagged outcome wrapper rather than key-presence sentinel.

## Impact

Valid model outputs can be dropped and rewritten as failures.

## Triage

- Status: open
- Source report: `docs/bugs/generated/plugins/llm/openrouter_batch.py.md`
- Beads: elspeth-rapid-ydk4
