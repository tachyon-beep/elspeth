## Summary

Nested coalesce nodes in `builder.py` always publish all branch keys as present, even for partial-arrival policies (`best_effort`, `quorum`, `first`), so the DAG contract overstates what the runtime can actually emit.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth/src/elspeth/core/dag/builder.py
- Line(s): 941-948
- Function/Method: `build_execution_graph`

## Evidence

`builder.py` synthesizes the nested coalesce schema without considering policy or runtime partial arrival:

```python
# src/elspeth/core/dag/builder.py:941-948
else:
    # Nested merge: output has branch names as top-level fields, each
    # containing the branch's row data as a nested dict.  Since the type
    # system only supports flat types, declare branch fields as "any".
    graph.get_node_info(coalesce_id).config["schema"] = {
        "mode": "flexible",
        "fields": [f"{branch}: any" for branch in branch_to_schema],
    }
```

That schema makes every branch field required by default. `ExecutionGraph.get_effective_guaranteed_fields()` then treats nested coalesces as guaranteed according to that config:

```python
# src/elspeth/core/dag/graph.py:1523-1529
if merge_strategy in ("nested", "select"):
    return self.get_guaranteed_fields(node_id)
```

And `SchemaConfig` explicitly says required declared fields are implicitly guaranteed:

```python
# src/elspeth/contracts/schema.py:474-478
if self.fields is not None:
    declared_required = frozenset(f.name for f in self.fields if f.required)
    return explicit | declared_required
```

But the runtime coalesce contract does not require missing branches for partial-arrival policies. It marks each branch required only if that branch actually arrived:

```python
# src/elspeth/engine/coalesce_executor.py:679-685
branch_fields = tuple(
    FieldContract(
        original_name=branch_name,
        normalized_name=branch_name,
        python_type=object,
        required=branch_name in pending.branches,
```

The existing unit test locks in that runtime behavior:

```python
# tests/unit/engine/test_coalesce_contract_bug.py:75-85
"""When a branch doesn't arrive (quorum/best_effort), its field is not required."""
...
assert required["path_b"] is False  # Didn't arrive
```

I also verified the builder path directly: constructing a `best_effort` + `nested` coalesce produces `{'mode': 'flexible', 'fields': ['branch_a: any', 'branch_b: any']}` and `graph.get_effective_guaranteed_fields(...) == {'branch_a', 'branch_b'}`. That is stricter than what the executor can actually produce when one branch times out or never arrives.

## Root Cause Hypothesis

The builder is encoding nested coalesce output as a static schema based only on configured branches, but nested coalesce output is policy-sensitive and, for partial-arrival policies, data-shape-sensitive at runtime. The code ignores that nuance and defaults to required branch fields, which turns “possible branch key” into “guaranteed branch key.”

## Suggested Fix

Make nested coalesce schema generation policy-aware and align it with the runtime contract shape.

A safe fix in `builder.py` is:

```python
required = coal_config.policy == "require_all"
graph.get_node_info(coalesce_id).config["schema"] = {
    "mode": "fixed",
    "fields": [f"{branch}: any" if required else f"{branch}: any?" for branch in coal_config.branches],
}
```

That does two important things:

1. Uses `fixed`, matching the executor’s nested contract shape.
2. Marks branch keys optional for `best_effort`, `quorum`, and `first`, so `get_effective_guaranteed_fields()` no longer falsely advertises them as guaranteed.

A regression test should cover a nested coalesce with `best_effort` or `quorum` and assert that downstream guaranteed fields do not include branches that may be absent.

## Impact

Build-time DAG validation can currently approve downstream nodes that depend on branch keys which may legally be absent at runtime. That leads to false contract guarantees, possible downstream row failures/quarantines, and inaccurate audit metadata for the coalesce node’s published schema. In ELSPETH terms, the graph is asserting a stronger output contract than the engine actually honors.
