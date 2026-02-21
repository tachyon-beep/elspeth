## Summary

Operation input/output payload `{}` was treated as absent due to truthiness checks, so hashes/refs were not recorded.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `src/elspeth/core/landscape/_call_recording.py`
- Function/Method: `begin_operation`, `complete_operation`

## Evidence

- Source report: `docs/bugs/generated/core/landscape/_call_recording.py.md`
- Truthiness checks (`if input_data`, `if output_data`) conflated `None` and `{}`.

## Root Cause Hypothesis

Optional payload checks used truthiness instead of explicit optionality.

## Suggested Fix

Use `is not None` for payload presence and preserve hash/ref recording for empty objects.

## Impact

Loss of audit lineage for valid empty payloads.

## Triage

- Status: closed-fixed
- Beads: elspeth-rapid-o4ps
- Fixed in commit: `abd7f439`
- Source report: `docs/bugs/generated/core/landscape/_call_recording.py.md`
