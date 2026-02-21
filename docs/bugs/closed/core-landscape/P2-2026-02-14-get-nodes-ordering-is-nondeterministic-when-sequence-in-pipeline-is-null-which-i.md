## Summary

`get_nodes()` ordering is nondeterministic when `sequence_in_pipeline` is `NULL`, which is the current production registration path.

## Severity

- Severity: major
- Priority: P2

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/core/landscape/_graph_recording.py`
- Line(s): 220-226
- Function/Method: `get_nodes`

## Evidence

Current query orders only by sequence:

```python
.order_by(nodes_table.c.sequence_in_pipeline.nullslast())
```

(`/home/john/elspeth-rapid/src/elspeth/core/landscape/_graph_recording.py:225`)

But orchestrator does not pass `sequence` when registering nodes:
- `/home/john/elspeth-rapid/src/elspeth/engine/orchestrator/core.py:1113-1123`

So nodes commonly have `NULL` sequence; SQL row order among ties is unspecified.

Export signing depends on record emission order:
- `/home/john/elspeth-rapid/src/elspeth/core/landscape/exporter.py:130-151`
- `/home/john/elspeth-rapid/src/elspeth/core/landscape/exporter.py:203-204`

Nondeterministic node order can change signed export hash.

## Root Cause Hypothesis

Ordering logic assumes sequence is populated/unique, but caller behavior leaves it unset; no secondary deterministic sort key is applied.

## Suggested Fix

Add stable tie-breakers in `get_nodes()` and keep `NULL` handling:

```python
.order_by(
    nodes_table.c.sequence_in_pipeline.nullslast(),
    nodes_table.c.registered_at,
    nodes_table.c.node_id,
)
```

Optionally also enforce sequence assignment at registration call sites.

## Impact

Signed exports for the same run can become order-dependent on backend/query plan, undermining deterministic verification expectations.

## Triage

- Status: open
- Source report: `docs/bugs/generated/core/landscape/_graph_recording.py.md`
- Finding index in source report: 3
- Beads: pending
