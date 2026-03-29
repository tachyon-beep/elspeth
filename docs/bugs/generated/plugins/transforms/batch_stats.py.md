## Summary

`BatchStats` publishes an incomplete schema contract when `group_by` is configured: it consumes `group_by` at runtime and emits it on every successful result, but never declares it as a required input or guaranteed output.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth/src/elspeth/plugins/transforms/batch_stats.py
- Line(s): 82-109, 204-218
- Function/Method: `BatchStats.__init__`, `BatchStats.process`

## Evidence

[`batch_stats.py:82`](/home/john/elspeth/src/elspeth/plugins/transforms/batch_stats.py#L82) stores `group_by`, but [`batch_stats.py:90-109`](/home/john/elspeth/src/elspeth/plugins/transforms/batch_stats.py#L90) only declares aggregate fields:

```python
self._group_by = cfg.group_by
...
stat_fields: set[str] = {"count", "sum", "batch_size"}
if cfg.compute_mean:
    stat_fields.add("mean")
self.declared_output_fields = frozenset(stat_fields)
...
self._output_schema_config = self._build_output_schema_config(cfg.schema_config)
```

That means the computed output contract contains `count/sum/batch_size/mean` only. The DAG builder explicitly prefers this computed contract for downstream validation at [`core/dag/builder.py:169-187`](/home/john/elspeth/src/elspeth/core/dag/builder.py#L169):

```python
if info.output_schema_config is not None:
    return copy.deepcopy(info.output_schema_config.to_dict())
```

At runtime, though, [`batch_stats.py:204-218`](/home/john/elspeth/src/elspeth/plugins/transforms/batch_stats.py#L204) always reads and emits `group_by` when configured:

```python
if self._group_by:
    group_value = rows[0][self._group_by]
    for row in rows[1:]:
        val = row[self._group_by]
        if val != group_value:
            raise ValueError(...)
    result[self._group_by] = group_value
```

So the actual behavior is:

- Input contract: `group_by` is required, or `rows[0][self._group_by]` raises `KeyError`.
- Output contract: `group_by` is present on every successful result.

But the published DAG contract says neither of those things. The DAG validator only checks explicit `required_input_fields` from plugin config at [`core/dag/graph.py:1459-1473`](/home/john/elspeth/src/elspeth/core/dag/graph.py#L1459), and `BatchStats` never augments them for `group_by`:

```python
required_input = node_info.config.get("required_input_fields")
...
if node_info.node_type == NodeType.AGGREGATION:
    options = node_info.config["options"]
    ...
    if "required_input_fields" in options:
        required_input = options["required_input_fields"]
```

I also found no test coverage asserting that `group_by` propagates into `required_input_fields` or downstream `guaranteed_fields`; the existing unit tests only verify runtime success/failure and explicitly assert that `group_by` is *not* in `declared_output_fields`.

## Root Cause Hypothesis

`BatchStats` treats `group_by` as a passthrough convenience field rather than a first-class contract field. That works inside `process()`, but ELSPETH’s DAG validation and schema propagation rely on explicit declarations. Because `group_by` is omitted from those declarations, configuration-time validation understates both what the transform needs and what it guarantees.

## Suggested Fix

When `group_by` is configured, `BatchStats` should publish it in its contracts:

- Add `group_by` to the transform’s explicit required inputs.
- Add `group_by` to the output guarantees used for DAG propagation.

One safe approach is to compute separate contract sets instead of reusing `declared_output_fields` semantics blindly:

```python
required_inputs = set(cfg.required_input_fields or [])
if cfg.group_by is not None:
    required_inputs.add(cfg.group_by)

guaranteed_outputs = set(stat_fields)
if cfg.group_by is not None:
    guaranteed_outputs.add(cfg.group_by)
```

Then build `_output_schema_config` from `guaranteed_outputs`, and ensure the node config exposes the augmented `required_input_fields` for aggregation validation.

## Impact

Two integration failures follow from this mismatch:

- Invalid pipelines are accepted: upstream can omit `group_by`, DAG validation passes, then `BatchStats.process()` crashes with `KeyError` at runtime.
- Valid pipelines are rejected or forced into weaker contracts: downstream nodes cannot declare `group_by` as required even though `BatchStats` emits it on every successful batch.

This is a protocol/contract violation in the target file. It undermines configuration-time safety and pushes deterministic topology errors into runtime failures.
