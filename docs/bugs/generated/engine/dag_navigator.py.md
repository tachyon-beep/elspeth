## Summary

Continuation routing in `dag_navigator.py` leaks raw `KeyError` for missing coalesce/branch topology instead of raising an `OrchestrationInvariantError` with execution context.

## Severity

- Severity: minor
- Priority: P2

## Location

- File: [src/elspeth/engine/dag_navigator.py](/home/john/elspeth/src/elspeth/engine/dag_navigator.py)
- Line(s): 131-132, 280
- Function/Method: `create_work_item()`, `create_continuation_work_item()`

## Evidence

In `create_work_item()`, name-to-node resolution does a bare mapping lookup:

```python
if resolved_coalesce_node_id is None and resolved_coalesce_name is not None:
    resolved_coalesce_node_id = self._coalesce_node_ids[resolved_coalesce_name]
```

Source: [src/elspeth/engine/dag_navigator.py](/home/john/elspeth/src/elspeth/engine/dag_navigator.py):130-132

In `create_continuation_work_item()`, fork-child branch routing does the same:

```python
first_node = self._branch_first_node[branch_name]
```

Source: [src/elspeth/engine/dag_navigator.py](/home/john/elspeth/src/elspeth/engine/dag_navigator.py):273-281

Those paths are exercised in production code, not just tests. For example, aggregation/deaggregation continuations and fork children call them here:

- [src/elspeth/engine/processor.py](/home/john/elspeth/src/elspeth/engine/processor.py):682-686
- [src/elspeth/engine/processor.py](/home/john/elspeth/src/elspeth/engine/processor.py):811-815
- [src/elspeth/engine/processor.py](/home/john/elspeth/src/elspeth/engine/processor.py):1640-1644
- [src/elspeth/engine/processor.py](/home/john/elspeth/src/elspeth/engine/processor.py):1887-1890

The rest of `DAGNavigator` already treats bad topology as an invariant violation with contextual errors, e.g. unknown coalesce node IDs and missing next-node entries:

- [src/elspeth/engine/dag_navigator.py](/home/john/elspeth/src/elspeth/engine/dag_navigator.py):135-142
- [src/elspeth/engine/dag_navigator.py](/home/john/elspeth/src/elspeth/engine/dag_navigator.py):174-177
- [src/elspeth/engine/dag_navigator.py](/home/john/elspeth/src/elspeth/engine/dag_navigator.py):182-187

So the current behavior is inconsistent: some topology faults become rich invariant errors, while these two become opaque `KeyError`s with no token/node/branch context.

## Root Cause Hypothesis

`DAGNavigator` assumes `_coalesce_node_ids` and `_branch_first_node` are always complete, so two lookups were left as direct dict indexing. That assumption is reasonable for the happy path, but this file is also the topology-invariant boundary for the processor. When upstream traversal metadata drifts or a branch/coalesce mapping is missing, these code paths bypass the file’s normal invariant-reporting contract and fail with low-context exceptions.

## Suggested Fix

Wrap both lookups in `try/except KeyError` and re-raise `OrchestrationInvariantError` with the relevant runtime context.

Helpful context to include:

- `token.token_id`
- `current_node_id`
- `branch_name`
- `coalesce_name`
- known keys from `_coalesce_node_ids` / `_branch_first_node`

## Impact

A malformed continuation path aborts mid-run with an opaque `KeyError` instead of an actionable orchestration invariant. That does not silently corrupt data, but it does make high-stakes failure analysis materially harder on fork, deaggregation, and aggregation-flush paths, and weakens the engine’s “crash loudly and informatively” contract.
