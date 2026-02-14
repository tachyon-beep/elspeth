## Summary

`get_unprocessed_rows()` dropped resumable rows when one token was buffered and a sibling token remained non-terminal/non-buffered.

## Severity

- Severity: critical
- Priority: P0

## Location

- File: `src/elspeth/core/checkpoint/recovery.py`
- Function/Method: `RecoveryManager.get_unprocessed_rows`

## Evidence

- Source report: `docs/bugs/generated/core/checkpoint/recovery.py.md`
- Root cause was row-level buffered exclusion instead of token-level exclusion logic.

## Root Cause Hypothesis

Buffered-exclusion logic used row granularity where token granularity was required.

## Suggested Fix

Use token-aware exclusion: only exclude rows whose incomplete leaf tokens are fully buffered.

## Impact

Silent omission of resumable work.

## Triage

- Status: closed-fixed
- Beads: elspeth-rapid-imp3
- Fixed in commit: `abd7f439`
- Source report: `docs/bugs/generated/core/checkpoint/recovery.py.md`
