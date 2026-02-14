## Summary

`get_node_states()` orders only by `step_index`, which makes retry attempt ordering non-deterministic and can surface attempt 1 before attempt 0.

## Severity

- Severity: minor
- Priority: P2

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/mcp/analyzers/queries.py`
- Line(s): 480
- Function/Method: `get_node_states`

## Evidence

Current ordering:

```python
# src/elspeth/mcp/analyzers/queries.py:480
query = query.order_by(node_states_table.c.step_index)
```

This ignores `attempt`, so rows with same `step_index` can come back in backend/insertion-dependent order.

Repository evidence that expected deterministic ordering includes attempt:
- `src/elspeth/core/landscape/_query_methods.py:96-102` orders by `(step_index, attempt)` and documents the retry-ordering fix.
- `tests/integration/audit/test_recorder_node_states.py:521-525` explicitly records prior bug: ordering only by step index is undefined and non-deterministic.

I also reproduced mismatch in-memory:
- MCP path (`queries.get_node_states`): `[(0, 1), (0, 0), (1, 0)]`
- Recorder canonical path (`get_node_states_for_token`): `[(0, 0), (0, 1), (1, 0)]`

## Root Cause Hypothesis

`get_node_states()` in the MCP analyzer did not carry forward the retry-ordering invariant already fixed in core recorder query methods.

## Suggested Fix

Order by at least `(step_index, attempt)`; for stronger determinism across tokens, include `token_id` too.

Example:

```python
query = query.order_by(
    node_states_table.c.step_index,
    node_states_table.c.attempt,
    node_states_table.c.token_id,
)
```

## Impact

MCP analysis can present retry history out of order, confusing failure triage and making paginated/automated comparisons unstable. This is an audit-read correctness issue (ordering semantics), not a write-path corruption issue.

## Triage

- Status: open
- Source report: `docs/bugs/generated/mcp/analyzers/queries.py.md`
- Finding index in source report: 2
- Beads: pending
