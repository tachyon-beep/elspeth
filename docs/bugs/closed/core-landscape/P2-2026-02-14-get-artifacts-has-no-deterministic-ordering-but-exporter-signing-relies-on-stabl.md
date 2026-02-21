## Summary

`get_artifacts()` has no deterministic ordering, but exporter signing relies on stable record order; artifact record sequence can vary by backend/query plan.

## Severity

- Severity: minor
- Priority: P2

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/core/landscape/_batch_recording.py`
- Line(s): 413, 418
- Function/Method: `get_artifacts`

## Evidence

Artifacts query has no `order_by(...)`:

- `/home/john/elspeth-rapid/src/elspeth/core/landscape/_batch_recording.py:413`
- `/home/john/elspeth-rapid/src/elspeth/core/landscape/_batch_recording.py:418`

Exporter signs records in iteration order and includes a running hash/manifest:

- `/home/john/elspeth-rapid/src/elspeth/core/landscape/exporter.py:127`
- `/home/john/elspeth-rapid/src/elspeth/core/landscape/exporter.py:130`
- `/home/john/elspeth-rapid/src/elspeth/core/landscape/exporter.py:513`

Other recorder queries in this subsystem explicitly enforce deterministic ordering for signature stability, but artifacts do not.

## Root Cause Hypothesis

Deterministic-ordering convention was applied to rows/tokens/batches but omitted for artifacts.

## Suggested Fix

Add deterministic ordering in `get_artifacts()`:

- `order_by(artifacts_table.c.created_at, artifacts_table.c.artifact_id)`

and update docstring to state deterministic order guarantee.

## Impact

- Signed export `final_hash` can differ across environments for identical data.
- Reproducibility and audit comparison workflows become brittle.

## Triage

- Status: open
- Source report: `docs/bugs/generated/core/landscape/_batch_recording.py.md`
- Finding index in source report: 3
- Beads: pending
