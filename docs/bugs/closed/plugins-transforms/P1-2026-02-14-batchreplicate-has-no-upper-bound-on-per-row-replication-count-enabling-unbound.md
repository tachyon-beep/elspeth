## Summary

`BatchReplicate` has no upper bound on per-row replication count, enabling unbounded row explosion and potential memory/CPU exhaustion in transform-mode aggregation.

## Severity

- Severity: minor
- Priority: P2
- Triaged: downgraded from P1 — operational resource safety concern, not data corruption or audit integrity issue

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/plugins/transforms/batch_replicate.py`
- Line(s): `39-43`, `163-183`
- Function/Method: `BatchReplicateConfig` and `BatchReplicate.process`

## Evidence

Configuration and runtime checks only enforce a lower bound (`>=1`), not an upper bound:

- Config: `default_copies` has `ge=1` only (`batch_replicate.py:39-43`)
- Runtime: `if raw_copies < 1` quarantine; otherwise accepted (`batch_replicate.py:163-175`)
- Expansion loop is directly proportional to `copies` (`batch_replicate.py:177-183`)

Engine then materializes all outputs for token expansion:

- `/home/john/elspeth-rapid/src/elspeth/engine/processor.py:707-710`

Runtime verification:

- Input row with `copies=20000` returns success with `20000` output rows.

There is no guardrail in the target plugin to prevent pathological replication sizes.

## Root Cause Hypothesis

The plugin validates only correctness of sign/type, not operational safety bounds. This leaves a resource-amplification path entirely controlled by row data.

## Suggested Fix

Add an explicit max bound in target plugin config and enforce it per row, e.g.:

- `max_copies_per_row: int = Field(default=1000, ge=1)`
- If `raw_copies > max_copies_per_row`, quarantine that row (or return `TransformResult.error` for all-invalid case as today)

Also validate `default_copies <= max_copies_per_row` in config validation, and add tests for oversized values.

## Impact

A single high `copies` value can cause very large in-memory output lists, slow hashing/expansion, and potential OOM crashes, leading to failed runs and incomplete processing under adversarial or malformed input distributions.
