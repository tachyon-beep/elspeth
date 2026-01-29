# Bug Report: Aggregation Flush Input Hash Mismatch

## Summary

- `node_state.input_hash` doesn't match `TransformResult.input_hash` for aggregation flushes, causing audit inconsistencies.

## Severity

- Severity: minor
- Priority: P2

## Reporter

- Name or handle: Branch Bug Scan
- Date: 2026-01-25
- Related run/issue ID: BUG-EXEC-01

## Evidence

- `src/elspeth/engine/executors.py` - Aggregation flush creates mismatched hashes

## Impact

- Audit consistency: Hash mismatch breaks lineage verification

## Proposed Fix

- Align hash computation between node_state and TransformResult for flush operations

## Acceptance Criteria

- Flush hashes match between node_state and TransformResult

## Tests

- New tests required: yes, verify flush hash consistency
