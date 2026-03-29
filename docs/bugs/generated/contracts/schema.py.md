## Summary

`SchemaConfig.to_dict()` can emit an explicit-schema dict that `SchemaConfig.from_dict()` rejects, so computed output schemas from field-adding transforms are not actually round-trippable and can crash downstream DAG schema parsing.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth/src/elspeth/contracts/schema.py
- Line(s): 414-420, 430-453
- Function/Method: `SchemaConfig.from_dict`, `SchemaConfig.to_dict`

## Evidence

`SchemaConfig.from_dict()` enforces that all contract lists on explicit schemas are subsets of declared `fields`:

```python
# /home/john/elspeth/src/elspeth/contracts/schema.py:414-420
declared_names = frozenset(names)
_validate_contract_fields_subset(guaranteed_fields, "guaranteed_fields", declared_names)
_validate_contract_fields_subset(required_fields, "required_fields", declared_names)
_validate_contract_fields_subset(audit_fields, "audit_fields", declared_names)
```

But production code intentionally constructs explicit `SchemaConfig` objects whose `guaranteed_fields` include transform-added output fields that are not present in `fields`:

```python
# /home/john/elspeth/src/elspeth/plugins/infrastructure/base.py:251-258
base_guaranteed = schema_config.guaranteed_fields or ()
return SchemaConfig(
    mode=schema_config.mode,
    fields=schema_config.fields,
    guaranteed_fields=tuple(set(base_guaranteed) | self.declared_output_fields),
    audit_fields=schema_config.audit_fields,
    required_fields=schema_config.required_fields,
)
```

There is even a unit test locking this behavior in for explicit schemas:

```python
# /home/john/elspeth/tests/unit/plugins/infrastructure/test_build_output_schema_config.py:52-58
base = SchemaConfig(mode="fixed", fields=fields, guaranteed_fields=None)
result = transform._build_output_schema_config(base)
assert result.mode == "fixed"
assert result.fields == fields
```

So a valid runtime `SchemaConfig` can serialize to a dict via `to_dict()`:

```python
# /home/john/elspeth/src/elspeth/contracts/schema.py:430-453
result = {
    "mode": self.mode,
    "fields": [f.to_dict() for f in self.fields] if self.fields else [],
}
...
result["guaranteed_fields"] = list(self.guaranteed_fields)
```

and then fail when reparsed.

That matters because the DAG builder explicitly serializes computed output schemas to dicts and later stores them as raw node config for pass-through nodes:

```python
# /home/john/elspeth/src/elspeth/core/dag/builder.py:181-183
if info.output_schema_config is not None:
    return copy.deepcopy(info.output_schema_config.to_dict())
```

```python
# /home/john/elspeth/src/elspeth/core/dag/builder.py:928-940
# Select merge: use selected branch's schema directly.
# _best_schema_dict() returns a SchemaConfig-compatible dict.
graph.get_node_info(coalesce_id).config["schema"] = branch_to_schema[select_branch]
```

Later, `ExecutionGraph` reparses that raw dict:

```python
# /home/john/elspeth/src/elspeth/core/dag/graph.py:1405-1413
if not isinstance(schema_dict, dict):
    raise GraphValidationError(...)
return SchemaConfig.from_dict(schema_dict)
```

For `merge == "select"`, coalesce schema queries call `get_guaranteed_fields()` on the coalesce node, which uses that reparsing path:

```python
# /home/john/elspeth/src/elspeth/core/dag/graph.py:1523-1529
if merge_strategy in ("nested", "select"):
    return self.get_guaranteed_fields(node_id)
```

So the code currently does this:
1. Create explicit `SchemaConfig` with extra `guaranteed_fields`.
2. Serialize it with `to_dict()`.
3. Treat the result as “SchemaConfig-compatible”.
4. Reparse it with `from_dict()`.
5. Crash on subset validation.

What it should do instead is preserve a representation that can be reparsed, or accept the representation it emits.

## Root Cause Hypothesis

`SchemaConfig` is serving two roles with incompatible invariants:

- User config parser: explicit schemas should reject typoed contract fields.
- Runtime/computed schema carrier: field-adding transforms preserve input `fields` while advertising new output guarantees via `guaranteed_fields`.

`from_dict()` only understands the first role, while `to_dict()` serializes objects from both roles without distinguishing them. That makes some in-memory `SchemaConfig` instances non-round-trippable.

## Suggested Fix

Make `SchemaConfig` internally self-consistent across parse/serialize paths.

One safe direction is:
- Keep strict subset validation for `required_fields` and `audit_fields` on explicit user configs.
- Stop requiring `guaranteed_fields` to be a subset of declared `fields` when parsing serialized/runtime schema dicts, because field-adding transforms legitimately guarantee fields beyond the base explicit schema.
- Add a regression test that round-trips an explicit `SchemaConfig` with transform-added `guaranteed_fields`, then exercises the coalesce `select` builder path.

If strict user-config typo detection must remain for `guaranteed_fields`, split the APIs:
- one parser for external config validation,
- one parser/constructor for internal round-trip/runtime schema dicts.

## Impact

Pipelines that combine explicit schemas with field-adding transforms can fail when their computed output schema is copied into raw DAG config and reparsed later, especially through pass-through schema propagation like coalesce `select`. The breakage is in contract propagation and DAG validation, so downstream nodes may become unbuildable even though the transform’s output contract was computed successfully. This undermines schema-contract reliability and can block valid pipelines from building or validating.
