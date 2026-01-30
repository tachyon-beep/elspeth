# Bug Report: Missing audit Call records for rows absent from batch output

## Summary

- When a row's result is missing from Azure batch output JSONL, the code marks it with error but does NOT record an LLM call. Call recording loop only iterates over found results.

## Severity

- Severity: moderate
- Priority: P2

## Reporter

- Name or handle: Codex (triaged by Claude)
- Date: 2026-01-31

## Evidence

- `src/elspeth/plugins/llm/azure_batch.py:795-806` - when `custom_id not in results_by_id`, row gets error but no call
- Line 866 - call recording only iterates `results_by_id.items()`
- Violates "External calls - Full request AND response recorded"

## Impact

- User-facing impact: Audit trail incomplete for batch operations
- Data integrity: Missing call records for some rows

## Proposed Fix

- Record CallStatus.ERROR call for each missing result

## Acceptance Criteria

- All rows have Call records, even those missing from batch output
