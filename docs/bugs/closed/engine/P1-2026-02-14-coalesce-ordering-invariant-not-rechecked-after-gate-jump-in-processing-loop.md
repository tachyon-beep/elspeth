## Summary

Coalesce ordering invariant is checked only at token start, so a gate jump can move a branch token downstream of coalesce and silently bypass join handling.

## Severity

- Severity: major
- Priority: P2 (downgraded from P1 — requires unusual DAG topology: gate within fork branch with route target past coalesce node; DAG validation makes this unlikely in practice)

## Location

- File: /home/john/elspeth-rapid/src/elspeth/engine/processor.py
- Line(s): 1532-1550, 1562-1570, 1814-1819, 1272-1279
- Function/Method: `_process_single_token`, `_maybe_coalesce_token`

## Evidence

There is a one-time invariant check before entering the loop:

```python
if current_step > coalesce_step:
    raise OrchestrationInvariantError(...)
```

(`/home/john/elspeth-rapid/src/elspeth/engine/processor.py:1532-1550`)

Inside the loop, coalesce handling only triggers on exact node equality:

```python
or current_node_id != coalesce_node_id
```

(`/home/john/elspeth-rapid/src/elspeth/engine/processor.py:1272-1279`)

But gate routing can reassign traversal position mid-loop:

```python
elif outcome.next_node_id is not None:
    node_id = outcome.next_node_id
    continue
```

(`/home/john/elspeth-rapid/src/elspeth/engine/processor.py:1814-1819`)

No downstream-of-coalesce guard is re-run after this jump.

## Root Cause Hypothesis

The downstream-of-coalesce invariant was added for malformed initial work items, but not enforced after runtime control-flow jumps (`next_node_id`) within the same token traversal.

## Suggested Fix

Re-validate coalesce ordering whenever `node_id` changes in-loop (especially before/after assigning `outcome.next_node_id`). If `coalesce_name/coalesce_node_id` is set and target step is downstream of coalesce, raise `OrchestrationInvariantError` immediately.

## Impact

- Fork branch tokens can bypass coalesce unexpectedly.
- Sibling branches may remain pending/fail later while one branch escaped, producing inconsistent fork/join outcomes.
- Audit lineage for intended join behavior becomes misleading (branch continuation without expected coalesce checkpoint).
