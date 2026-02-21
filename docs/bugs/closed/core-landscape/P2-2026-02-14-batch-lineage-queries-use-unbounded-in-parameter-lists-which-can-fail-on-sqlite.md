## Summary

Batch lineage queries use unbounded `IN (...)` parameter lists, which can fail on SQLite bind-variable limits for large state sets.

## Severity

- Severity: major
- Priority: P2

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/core/landscape/_query_methods.py`
- Line(s): 237, 263
- Function/Method: `get_routing_events_for_states`, `get_calls_for_states`

## Evidence

Both methods issue single unchunked `IN` queries:

```python
.where(routing_events_table.c.state_id.in_(state_ids))
```

(`/home/john/elspeth-rapid/src/elspeth/core/landscape/_query_methods.py:237`)

```python
.where(calls_table.c.state_id.in_(state_ids))
```

(`/home/john/elspeth-rapid/src/elspeth/core/landscape/_query_methods.py:263`)

These are fed directly from lineage state collection:

```python
state_ids = [s.state_id for s in node_states]
routing_events = recorder.get_routing_events_for_states(state_ids)
calls = recorder.get_calls_for_states(state_ids)
```

(`/home/john/elspeth-rapid/src/elspeth/core/landscape/lineage.py:157-159`)

The repo already acknowledges SQLite bind limits and chunks elsewhere:

```python
# SQLite's SQLITE_MAX_VARIABLE_NUMBER defaults to 999. We chunk IN clauses
```

(`/home/john/elspeth-rapid/src/elspeth/core/checkpoint/recovery.py:32-34`)

## Root Cause Hypothesis

The N+1-query optimization consolidated per-state queries into a single `IN` query but omitted the existing SQLite-safe chunking pattern used in other subsystems.

## Suggested Fix

In `_query_methods.py`, chunk `state_ids` (for example, size 500), execute multiple queries, merge results, and apply deterministic sort before returning.

## Impact

For tokens with large numbers of states (deep DAG + retries), `explain()` lineage retrieval can fail with database parameter-limit errors, breaking audit explainability for affected runs.

## Triage

- Status: open
- Source report: `docs/bugs/generated/core/landscape/_query_methods.py.md`
- Finding index in source report: 2
- Beads: pending
