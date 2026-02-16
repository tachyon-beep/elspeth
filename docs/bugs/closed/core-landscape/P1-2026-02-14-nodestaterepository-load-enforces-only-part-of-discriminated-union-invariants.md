## Summary

`NodeStateRepository.load()` enforces only part of the discriminated-union invariants, so status-incompatible fields can be silently dropped instead of crashing.

## Severity

- Severity: major
- Priority: P2 (downgraded from P1 — requires preceding writer bug to trigger; defense-in-depth gap)

## Location

- File: /home/john/elspeth-rapid/src/elspeth/core/landscape/repositories.py
- Line(s): 281-387
- Function/Method: `NodeStateRepository.load`

## Evidence

`NodeStateRepository.load()` validates only `output_hash`, `completed_at`, and `duration_ms` for status branches, but does not validate other status-incompatible columns before constructing narrower dataclasses.

Examples:
- OPEN branch checks only three fields, then returns `NodeStateOpen` (which has no `context_after_json`, `error_json`, `success_reason_json`): `/home/john/elspeth-rapid/src/elspeth/core/landscape/repositories.py:281-303`
- PENDING branch does not reject non-NULL `error_json` or `success_reason_json`: `/home/john/elspeth-rapid/src/elspeth/core/landscape/repositories.py:304-331`
- COMPLETED branch does not reject non-NULL `error_json`: `/home/john/elspeth-rapid/src/elspeth/core/landscape/repositories.py:333-357`
- FAILED branch does not reject non-NULL `success_reason_json`: `/home/john/elspeth-rapid/src/elspeth/core/landscape/repositories.py:359-382`

The union contracts show those fields are status-specific:
- `NodeStateOpen`: no error/success/after-context fields: `/home/john/elspeth-rapid/src/elspeth/contracts/audit.py:155-173`
- `NodeStateCompleted`: has `success_reason_json`, no `error_json`: `/home/john/elspeth-rapid/src/elspeth/contracts/audit.py:203-225`
- `NodeStateFailed`: has `error_json`, no `success_reason_json`: `/home/john/elspeth-rapid/src/elspeth/contracts/audit.py:229-251`

Downstream exporter then hardcodes missing fields as `None`, so non-NULL DB values are effectively erased from exported audit output:
`/home/john/elspeth-rapid/src/elspeth/core/landscape/exporter.py:371-376`
`/home/john/elspeth-rapid/src/elspeth/core/landscape/exporter.py:392-397`
`/home/john/elspeth-rapid/src/elspeth/core/landscape/exporter.py:416-418`
`/home/john/elspeth-rapid/src/elspeth/core/landscape/exporter.py:434-439`

## Root Cause Hypothesis

Invariant validation was added incrementally (focused on completion timing/hash fields) but not completed for all status-specific columns in the discriminated union.

## Suggested Fix

In `NodeStateRepository.load()`, add strict NULL checks for all status-incompatible columns before returning each variant:
- OPEN: require `context_after_json`, `error_json`, `success_reason_json` are `None`
- PENDING: require `error_json`, `success_reason_json` are `None`
- COMPLETED: require `error_json` is `None`
- FAILED: require `success_reason_json` is `None`

Also add repository tests for each rejected combination in `tests/unit/core/landscape/test_repositories.py`.

## Impact

Audit integrity can be violated without detection: corrupted/impossible `node_states` rows can load successfully, and status-incompatible data may disappear from exported records. This breaks Tier-1 "crash on anomaly" behavior and risks silent evidence loss.

## Triage

Triage: Downgraded P1→P2. Silently drops cross-status fields (e.g. error_json on COMPLETED row). But for this to cause data loss, the writer (complete_node_state) would need a bug setting both error and success_reason simultaneously. Defense-in-depth improvement.
