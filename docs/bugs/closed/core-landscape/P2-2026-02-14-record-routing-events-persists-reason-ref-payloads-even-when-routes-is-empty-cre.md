## Summary

`record_routing_events()` persists `reason_ref` payloads even when `routes` is empty, creating unreferenced payload blobs during normal `continue` gate execution.

## Severity

- Severity: minor
- Priority: P2

## Location

- File: /home/john/elspeth-rapid/src/elspeth/core/landscape/_node_state_recording.py
- Line(s): 324-333
- Function/Method: `record_routing_events`

## Evidence

In `record_routing_events`, payload is stored before confirming there are any routes to persist:

```python
# _node_state_recording.py
reason_ref = None
if reason is not None and self._payload_store is not None:
    reason_bytes = canonical_json(reason).encode("utf-8")
    reason_ref = self._payload_store.store(reason_bytes)

with self._db.connection() as conn:
    for ordinal, route in enumerate(routes):
        conn.execute(routing_events_table.insert().values(...))
```

If `routes=[]`, no `routing_events` rows are inserted but payload may already be written.

This is reachable in normal flow for gate `continue` decisions:
- `/home/john/elspeth-rapid/src/elspeth/engine/executors/gate.py:126-136`
- `/home/john/elspeth-rapid/src/elspeth/engine/executors/gate.py:387-400`

`continue_()` has no destinations, so `_record_routing()` passes an empty list to `record_routing_events(...)`.

Retention only discovers payload refs via DB reference columns (including `routing_events.reason_ref`), so unreferenced blobs are not discoverable for purge:
- `/home/john/elspeth-rapid/src/elspeth/core/retention/purge.py:119-123`
- `/home/john/elspeth-rapid/src/elspeth/core/retention/purge.py:224-234`

## Root Cause Hypothesis

The method treats “persist reason payload” as unconditional when `reason` exists, instead of conditional on “at least one routing event will be written.”

## Suggested Fix

Short-circuit before any hashing/payload persistence when no routes exist:

```python
if not routes:
    return []
```

Place this at the top of `record_routing_events`, before computing `reason_hash` or storing `reason_ref`.

## Impact

- Payload store accumulates blobs with no lineage/reference.
- Purge logic cannot find these refs from audit tables.
- Storage drift and audit-data-to-payload inconsistency increase over time.

## Triage

- Status: open
- Source report: `docs/bugs/generated/core/landscape/_node_state_recording.py.md`
- Finding index in source report: 1
- Beads: pending
