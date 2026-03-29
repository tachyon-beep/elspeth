## Summary

Batch query methods in `query_repository.py` claim deterministic execution ordering, but their sort keys are not total, so run exports can emit routing events and calls in nondeterministic order when multiple tokens share the same `step_index`/`attempt`.

## Severity

- Severity: major
- Priority: P2

## Location

- File: `/home/john/elspeth/src/elspeth/core/landscape/query_repository.py`
- Line(s): 318-320, 356-358, 421-426, 450-454
- Function/Method: `get_routing_events_for_states`, `get_calls_for_states`, `get_all_routing_events_for_run`, `get_all_calls_for_run`

## Evidence

`QueryRepository` explicitly treats deterministic ordering as an audit requirement in nearby methods:

```python
# /home/john/elspeth/src/elspeth/core/landscape/query_repository.py:255-261
List of RoutingEvent models, ordered by ordinal then event_id
for deterministic export signatures.
...
.order_by(routing_events_table.c.ordinal, routing_events_table.c.event_id)
```

But the batch methods only sort by per-state execution fields, not by the owning state/token:

```python
# /home/john/elspeth/src/elspeth/core/landscape/query_repository.py:318-320
all_db_rows.sort(key=lambda r: (r.step_index, r.attempt, r.ordinal, r.event_id))

# /home/john/elspeth/src/elspeth/core/landscape/query_repository.py:356-358
all_db_rows.sort(key=lambda r: (r.step_index, r.attempt, r.call_index))

# /home/john/elspeth/src/elspeth/core/landscape/query_repository.py:421-426
.order_by(
    node_states_table.c.step_index,
    node_states_table.c.attempt,
    routing_events_table.c.ordinal,
    routing_events_table.c.event_id,
)

# /home/john/elspeth/src/elspeth/core/landscape/query_repository.py:450-454
.order_by(
    node_states_table.c.step_index,
    node_states_table.c.attempt,
    calls_table.c.call_index,
)
```

That is not a total order for a run. Different tokens routinely share the same `step_index` and `attempt`, and both `ordinal` and `call_index` restart from zero per state. When two states tie on those fields, SQL is free to return rows in any order.

That nondeterministic order is consumed directly by the exporter:

```python
# /home/john/elspeth/src/elspeth/core/landscape/exporter.py:353-364
all_routing_events = self._recorder.get_all_routing_events_for_run(run_id)
for event in all_routing_events:
    events_by_state[event.state_id].append(event)

all_calls = self._recorder.get_all_calls_for_run(run_id)
for call in all_calls:
    if call.state_id:
        calls_by_state[call.state_id].append(call)
```

So arbitrary database row order becomes export record order.

The repo already uses explicit tiebreakers elsewhere for this exact reason:

```python
# /home/john/elspeth/src/elspeth/core/landscape/data_flow_repository.py:1085-1093
# Tiebreakers (registered_at, node_id) ensure deterministic ordering
.order_by(
    nodes_table.c.sequence_in_pipeline.nullslast(),
    nodes_table.c.registered_at,
    nodes_table.c.node_id,
)
```

The current tests for the run-wide batch methods only check membership, not order, so this regression is not covered:

```python
# /home/john/elspeth/tests/unit/core/landscape/test_query_methods.py:788-792
events = recorder.get_all_routing_events_for_run("run-1")
assert len(events) == 2
assert {e.state_id for e in events} == {"state-1", "state-2"}

# /home/john/elspeth/tests/unit/core/landscape/test_query_methods.py:836-840
calls = recorder.get_all_calls_for_run("run-1")
assert len(calls) == 2
assert {c.state_id for c in calls} == {"state-1", "state-2"}
```

## Root Cause Hypothesis

The N+1 batching rewrite preserved only the old per-state ordering keys and did not add run-level tiebreakers. That is fine when querying one state, but incorrect once multiple states are merged into a single result set. The code implicitly assumes `(step_index, attempt, ordinal/event_id)` and `(step_index, attempt, call_index)` are globally unique within a run; they are not.

## Suggested Fix

Make the batch orderings total by including stable state/token tiebreakers.

Examples:

```python
# get_all_routing_events_for_run
.order_by(
    node_states_table.c.token_id,
    node_states_table.c.step_index,
    node_states_table.c.attempt,
    routing_events_table.c.state_id,
    routing_events_table.c.ordinal,
    routing_events_table.c.event_id,
)

# get_all_calls_for_run
.order_by(
    node_states_table.c.token_id,
    node_states_table.c.step_index,
    node_states_table.c.attempt,
    calls_table.c.state_id,
    calls_table.c.call_index,
    calls_table.c.call_id,
)
```

And mirror the same logic in the chunked Python sorts for `get_routing_events_for_states()` and `get_calls_for_states()` by selecting `node_states_table.c.token_id` and `calls_table.c.state_id` / `routing_events_table.c.state_id` as sort inputs.

Add tests with two different tokens in the same run that both have:
- the same `step_index`
- the same `attempt`
- `ordinal == 0` or `call_index == 0`

Then assert a stable returned order.

## Impact

Audit exports can change record order across runs against identical audit data, which breaks deterministic export signatures and weakens reproducibility guarantees. Nothing is lost from the database, but the exported audit stream can become unstable, making hash-based verification, snapshot comparison, and re-export consistency unreliable.
