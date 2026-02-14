## Summary

`get_edge_map()` silently overwrites duplicate `(from_node_id, label)` entries instead of crashing on Tier-1 anomalies.

**CLOSED -- False positive.** edges table has UniqueConstraint("run_id", "from_node_id", "label") (schema.py:106). DB prevents duplicates; dict assignment is safe.

## Severity

- Severity: major
- Priority: CLOSED (false positive — UniqueConstraint prevents duplicates)

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/core/landscape/_graph_recording.py`
- Line(s): 325-328
- Function/Method: `get_edge_map`

## Evidence

Current implementation:

```python
edge_map: dict[tuple[str, str], str] = {}
for edge in edges:
    edge_map[(edge.from_node_id, edge.label)] = edge.edge_id
```

(`/home/john/elspeth-rapid/src/elspeth/core/landscape/_graph_recording.py:325-328`)

If duplicates exist (data corruption/tampering), the later row overwrites the earlier one with no error.

This map is then used in resume to attach routing events to edge IDs:
- `/home/john/elspeth-rapid/src/elspeth/engine/orchestrator/core.py:2074-2075`
- `/home/john/elspeth-rapid/src/elspeth/engine/executors/gate.py:377-383`

So overwrite can misattribute routing lineage.

## Root Cause Hypothesis

The method assumes DB uniqueness constraints are always pristine and does not enforce Tier-1 "crash on anomaly" behavior when materializing a key-indexed map.

## Suggested Fix

Detect duplicates during map construction and raise `ValueError` with run/key/context.

Example direction:

```python
key = (edge.from_node_id, edge.label)
if key in edge_map:
    raise ValueError(...)
edge_map[key] = edge.edge_id
```

## Impact

Corrupted duplicate edges can produce incorrect routing-event lineage instead of a hard integrity failure, violating auditability guarantees.
