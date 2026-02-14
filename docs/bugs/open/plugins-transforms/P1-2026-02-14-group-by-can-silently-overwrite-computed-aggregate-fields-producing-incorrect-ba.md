## Summary

`group_by` can silently overwrite computed aggregate fields (`count`, `sum`, `mean`, `batch_size`, etc.), producing incorrect batch statistics without any error.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth-rapid/src/elspeth/plugins/transforms/batch_stats.py
- Line(s): 31-34, 186-190, 197-199, 213
- Function/Method: `BatchStatsConfig` / `BatchStats.process`

## Evidence

`group_by` is accepted as any string with no reserved-name validation:

- `/home/john/elspeth-rapid/src/elspeth/plugins/transforms/batch_stats.py:31-34`

`process()` builds reserved aggregate keys, then writes `result[self._group_by] = group_value`, which can overwrite them:

- Reserved keys created at `/home/john/elspeth-rapid/src/elspeth/plugins/transforms/batch_stats.py:186-190` and `/home/john/elspeth-rapid/src/elspeth/plugins/transforms/batch_stats.py:197-199`
- Overwrite write at `/home/john/elspeth-rapid/src/elspeth/plugins/transforms/batch_stats.py:213`

Concrete repro (executed in repo):

- Config: `group_by="count"`, `value_field="amount"`
- Output became: `{'count': 'A', 'sum': 30, 'batch_size': 2, 'mean': 15.0}`
  (`count` was overwritten by group label, not row count)

## Root Cause Hypothesis

No config-time or runtime guard prevents `group_by` from colliding with transform-owned output field names, so later assignment mutates semantic meaning of audit/output fields.

## Suggested Fix

Add validation in `BatchStatsConfig` to reject reserved `group_by` names (`count`, `sum`, `mean`, `batch_size`, `skipped_non_finite`, `batch_empty`) and fail fast at config load. Optionally also guard in `process()` as defense-in-depth.

## Impact

Incorrect aggregates are written as successful results, which can drive wrong downstream routing/analytics and compromise audit reliability (silent semantic corruption, not a crash).
