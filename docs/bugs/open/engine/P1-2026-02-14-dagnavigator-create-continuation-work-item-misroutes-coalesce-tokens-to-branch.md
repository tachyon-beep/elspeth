## Summary

`DAGNavigator.create_continuation_work_item()` misroutes any token with `coalesce_name` back to the branch's first node, which causes backward jumps/reprocessing for non-fork continuations (notably deaggregation and aggregation flush paths).

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth-rapid/src/elspeth/engine/dag_navigator.py
- Line(s): 258-273
- Function/Method: `DAGNavigator.create_continuation_work_item`

## Evidence

In `create_continuation_work_item`, `coalesce_name` is treated as "this is a fresh fork child," and routing ignores `current_node_id`:

```python
if coalesce_name is not None:
    ...
    first_node = self._branch_first_node[branch_name]
    return self.create_work_item(... current_node_id=first_node, ...)
```

Source: `/home/john/elspeth-rapid/src/elspeth/engine/dag_navigator.py:258-273`

But processor passes `coalesce_name` for continuations that are **not** fresh fork children:

- Deaggregation children in branch paths:
  `/home/john/elspeth-rapid/src/elspeth/engine/processor.py:1721-1727`
- Aggregation flush continuations:
  `/home/john/elspeth-rapid/src/elspeth/engine/processor.py:632-636`
  `/home/john/elspeth-rapid/src/elspeth/engine/processor.py:735-739`

Expanded children keep `branch_name`, so they trigger this branch-start jump:
`/home/john/elspeth-rapid/src/elspeth/engine/tokens.py:387`

This means a token already at/after a branch transform can be sent backward to branch start, causing repeated execution (and potentially repeated expansion) instead of advancing to `resolve_next_node(current_node_id)`.

## Root Cause Hypothesis

`coalesce_name` is overloaded as both:
1. "token belongs to a coalescing branch" (metadata), and
2. "token is at fork entry and needs branch-start routing" (control-flow signal).

`create_continuation_work_item()` conflates these, so all coalescing continuations are forced to branch start.

## Suggested Fix

In `create_continuation_work_item()`, only use `branch_first_node[branch_name]` when continuation originates from a fork gate context; otherwise continue from `resolve_next_node(current_node_id)` while preserving coalesce metadata.

Example direction (in target file):

- If `coalesce_name is not None` and `current_node_id` is a gate node (fork origin), route to branch first node.
- Else route to `resolve_next_node(current_node_id)` and keep `coalesce_name/coalesce_node_id` on the `WorkItem`.

Also add regression tests covering:
- deaggregation (`creates_tokens=True`) inside fork→coalesce branch,
- aggregation flush inside fork→coalesce branch,
ensuring children advance forward, not back to branch start.

## Impact

- Duplicate transform execution and repeated external calls on the same logical branch path.
- Possible exponential token growth/infinite-loop-like behavior until iteration guard trips.
- Incorrect audit lineage semantics (same branch segment reprocessed unexpectedly), undermining traceability guarantees.
