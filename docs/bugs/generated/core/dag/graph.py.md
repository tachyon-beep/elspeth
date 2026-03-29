## Summary

Union and nested coalesce nodes compute explicit merged schema metadata during graph build, but downstream edge validation still treats those coalesces as fully dynamic, so incompatible sink/transform input schemas are silently accepted.

## Severity

- Severity: major
- Priority: P1

## Location

- File: [src/elspeth/core/dag/graph.py](/home/john/elspeth/src/elspeth/core/dag/graph.py)
- Line(s): 1077-1084, 1141-1170
- Function/Method: `ExecutionGraph._validate_single_edge()`, `ExecutionGraph.get_effective_producer_schema()`

## Evidence

[graph.py](/home/john/elspeth/src/elspeth/core/dag/graph.py#L1077) only performs type validation when `producer_schema` is not `None`:

```python
producer_schema = self.get_effective_producer_schema(from_node_id, _cache=_schema_cache)
consumer_schema = to_info.input_schema

if producer_schema is None or consumer_schema is None:
    return
```

But [graph.py](/home/john/elspeth/src/elspeth/core/dag/graph.py#L1141) hard-codes most coalesce nodes to return `None`:

```python
if node_info.node_type == NodeType.COALESCE:
    merge_strategy = node_info.config["merge"]
    if merge_strategy == "select":
        ...
        return result
    _cache[node_id] = None
    return None
```

That bypass happens even though the builder explicitly computes and stores a merged schema for coalesce outputs. In [builder.py](/home/john/elspeth/src/elspeth/core/dag/builder.py#L815), union coalesces get a merged `config["schema"]`, and nested coalesces also get an explicit schema shape:

```python
if coal_config.merge == "union":
    merged = {
        "mode": "flexible",
        "fields": [...],
    }
    graph.get_node_info(coalesce_id).config["schema"] = merged
...
else:
    graph.get_node_info(coalesce_id).config["schema"] = {
        "mode": "flexible",
        "fields": [f"{branch}: any" for branch in branch_to_schema],
    }
```

The repo already treats that stored coalesce schema as meaningful downstream metadata. [test_dag_schema_propagation.py](/home/john/elspeth/tests/unit/core/test_dag_schema_propagation.py#L630) asserts the coalesce node inherits computed schema fields:

```python
coalesce_schema_dict = coalesce_nodes[0].config["schema"]
assert "guaranteed_fields" in coalesce_schema_dict
```

So the current behavior is inconsistent:
- Builder says coalesce has an explicit output contract.
- Validator still says coalesce is dynamic and skips downstream type checks.

I did not find a regression test covering “explicit downstream sink/transform schema mismatch after a union/nested coalesce”; existing coalesce tests in [test_dag_contract_validation.py](/home/john/elspeth/tests/unit/core/test_dag_contract_validation.py#L663) focus on `required_fields`/guaranteed-field intersection, not downstream type compatibility.

## Root Cause Hypothesis

`get_effective_producer_schema()` was written with the assumption that coalesce nodes are not trustworthy type producers unless they are `select` merges. Later builder work added concrete coalesce schema synthesis into `config["schema"]`, but `graph.py` was not updated to convert or expose that schema as a real producer schema for edge validation. The result is a contract split: field-presence checks use coalesce metadata, but type checks do not.

## Suggested Fix

Teach `graph.py` to return an explicit producer schema for coalesce nodes when the builder has already synthesized one.

Options:
- Preferred: when the builder populates coalesce `config["schema"]`, also populate `NodeInfo.output_schema` or `output_schema_config` with an explicit schema object for `union`/`nested`, then have `get_effective_producer_schema()` use it.
- Alternatively: add a core-safe helper that converts `SchemaConfig.from_dict(node_info.config["schema"])` into a `PluginSchema` subclass and return that instead of `None`.

At minimum, this branch should change:

```python
if node_info.node_type == NodeType.COALESCE:
    ...
    _cache[node_id] = None
    return None
```

to use the synthesized coalesce schema for `union` and `nested`.

Regression tests to add:
- union coalesce producing `value: str` into sink requiring `value: int` must fail at `validate_edge_compatibility()`
- nested coalesce feeding a downstream consumer with incompatible explicit expectations must also fail early

## Impact

Invalid DAGs pass pre-run validation even though their downstream schemas are incompatible. The practical result is late failures in strict sinks/transforms instead of deterministic build-time rejection, which breaks the schema-contract guarantee and shifts a static contract error into runtime behavior. In a high-audit pipeline, that means operators get a configuration that “validated” but still fails only after data reaches execution.
