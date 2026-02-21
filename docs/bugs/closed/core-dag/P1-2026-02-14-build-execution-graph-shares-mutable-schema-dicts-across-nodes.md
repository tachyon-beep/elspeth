## Summary

`build_execution_graph()` shares mutable `schema` dict objects across nodes and only shallow-freezes config, so post-build nested mutations can silently alter multiple nodes' contracts.

## Severity

- Severity: major
- Priority: P2 (downgraded from P1 during triage — aliasing is real but exhaustive search confirms no post-construction mutation exists; latent invariant violation, not active corruption)

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/core/dag/builder.py`
- Line(s): `147-161`, `578`, `898`, `907-914`
- Function/Method: `build_execution_graph` (`_best_schema_dict` + config freeze block)

## Evidence

`_best_schema_dict()` returns the original schema dict reference for nodes without `output_schema_config`:

```python
# builder.py
schema: dict[str, Any] = info.config["schema"]
return schema
```

That reference is assigned directly into downstream gate config in pass 1 and pass 2:

- `/home/john/elspeth-rapid/src/elspeth/core/dag/builder.py:578`
- `/home/john/elspeth-rapid/src/elspeth/core/dag/builder.py:898`

Then config is only shallow-wrapped with `MappingProxyType`:

- `/home/john/elspeth-rapid/src/elspeth/core/dag/builder.py:913-914`

Repro (executed): transform and gate `config["schema"]` had the same object id; mutating nested list through gate also mutated transform schema:

```text
same object? True
nested mutation succeeded
after transform {'mode': 'observed', 'guaranteed_fields': ['a', 'MUTATED']}
```

This means the "frozen config" invariant is not actually enforced for nested structures, and schema state is shared across nodes.

## Root Cause Hypothesis

Schema propagation reuses dict references instead of cloning, and final freeze uses top-level `MappingProxyType` only (no deep immutability). Shared nested dict/list structures remain writable and aliased.

## Suggested Fix

In `builder.py`:

1. Return a deep copy from `_best_schema_dict()` for both branches (`output_schema_config.to_dict()` and `info.config["schema"]`).
2. Deep-copy before assigning to node config at schema propagation points.
3. Replace shallow freeze with recursive freeze (dict -> `MappingProxyType`, list -> tuple) before finalizing node configs.

## Impact

- Silent contract drift after graph construction.
- One mutation can affect multiple nodes due aliasing.
- Audit/schema lineage can become inconsistent with original compiled DAG, violating immutability expectations for high-stakes traceability.
