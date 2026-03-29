## Summary

Checkpoint compatibility can falsely approve resume against a semantically different graph because `validate()` only compares node config and a topology hash that ignores node role and schema contracts.

## Severity

- Severity: major
- Priority: P1

## Location

- File: [/home/john/elspeth/src/elspeth/core/checkpoint/compatibility.py](/home/john/elspeth/src/elspeth/core/checkpoint/compatibility.py)
- Line(s): 61-81
- Function/Method: `CheckpointCompatibilityValidator.validate`

## Evidence

`validate()` treats compatibility as:

```python
current_node_info = current_graph.get_node_info(checkpoint.node_id)
current_config_hash = stable_hash(current_node_info.config)

if checkpoint.checkpoint_node_config_hash != current_config_hash:
    ...
current_topology_hash = self.compute_full_topology_hash(current_graph)
if checkpoint.upstream_topology_hash != current_topology_hash:
    ...
```

Source: [/home/john/elspeth/src/elspeth/core/checkpoint/compatibility.py#L61](/home/john/elspeth/src/elspeth/core/checkpoint/compatibility.py#L61)

But the topology hash it relies on only serializes `node_id`, `plugin_name`, `config_hash`, and edges:

```python
topology_data = {
    "nodes": sorted([
        {
            "node_id": n,
            "plugin_name": graph.get_node_info(n).plugin_name,
            "config_hash": stable_hash(graph.get_node_info(n).config),
        }
        for n in nx_graph.nodes()
    ], key=lambda x: x["node_id"]),
    "edges": sorted([...]),
}
```

Source: [/home/john/elspeth/src/elspeth/core/canonical.py#L211](/home/john/elspeth/src/elspeth/core/canonical.py#L211)

The graph carries more execution semantics than that. `NodeInfo` stores `node_type`, `input_schema`, `output_schema`, `input_schema_config`, and `output_schema_config` as first-class fields:

Source: [/home/john/elspeth/src/elspeth/core/dag/models.py#L83](/home/john/elspeth/src/elspeth/core/dag/models.py#L83)

Those schema fields are populated during graph build and used for DAG contract validation:

- Builder attaches schemas/contracts to each node: [/home/john/elspeth/src/elspeth/core/dag/builder.py#L235](/home/john/elspeth/src/elspeth/core/dag/builder.py#L235)
- Graph validates edge compatibility from those schemas: [/home/john/elspeth/src/elspeth/core/dag/graph.py#L873](/home/john/elspeth/src/elspeth/core/dag/graph.py#L873)
- Sink execution enforces current sink input schema and required fields at runtime: [/home/john/elspeth/src/elspeth/engine/executors/sink.py#L206](/home/john/elspeth/src/elspeth/engine/executors/sink.py#L206)

The audit layer also records node type and schema contracts as meaningful node metadata, which is strong evidence they are part of the pipeline’s probative configuration, not incidental details:

Source: [/home/john/elspeth/src/elspeth/core/landscape/data_flow_repository.py#L923](/home/john/elspeth/src/elspeth/core/landscape/data_flow_repository.py#L923)

There is test coverage for config, plugin name, edge label, and routing mode differences, but no coverage for node-type or schema-contract differences affecting checkpoint compatibility:

Source: [/home/john/elspeth/tests/integration/checkpoint/test_topology_validation.py#L224](/home/john/elspeth/tests/integration/checkpoint/test_topology_validation.py#L224)

What the code does:
It can return `can_resume=True` when the current graph has different schemas or node roles, as long as `config`, `plugin_name`, and edges hash the same.

What it should do:
It should reject resume whenever the current graph’s execution semantics differ from the checkpointed graph, including schema contracts and node role, because resumed rows will otherwise be processed under a different contract than earlier rows in the same `run_id`.

## Root Cause Hypothesis

The validator defines “same pipeline” too narrowly. It delegates almost all semantic comparison to `compute_full_topology_hash()`, but that hash was implemented as a structural/config fingerprint rather than a full execution-contract fingerprint. As a result, `validate()` omits fields that the rest of the engine treats as authoritative for behavior and auditability.

## Suggested Fix

Extend compatibility validation in this file so it compares execution semantics, not just config hash plus the current topology hash.

Concrete options:
1. Add explicit checks in `validate()` for `current_node_info.node_type`, `input_schema`, `output_schema`, `input_schema_config`, and `output_schema_config`.
2. Preferably, store and compare a stronger checkpoint fingerprint that includes those fields for every node, then use that here.

A minimal shape would be to compute a per-node semantic fingerprint in this module before accepting resume, including:
- `node_type`
- `plugin_name`
- `stable_hash(config)`
- normalized schema contract data or schema JSON for input/output
- schema config contract data such as `required_fields` and `guaranteed_fields`

Add a regression test showing that a graph with unchanged `plugin_name`/`config`/edges but changed schema contract is rejected by `CheckpointCompatibilityValidator`.

## Impact

Resume can silently continue a run under a different execution contract from the one that produced earlier outputs. That breaks the checkpoint subsystem’s stated invariant that one `run_id` maps to one configuration, and it risks mixed-contract outputs within the same audit trail. In practice this can surface as resumed rows being validated, routed, or written differently than pre-crash rows without checkpoint compatibility stopping the run.
