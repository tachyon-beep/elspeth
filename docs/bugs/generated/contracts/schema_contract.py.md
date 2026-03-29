## Summary

`PipelineRow` only shallow-freezes row data, so nested `dict`/`list` values remain mutable and can be changed after the row is supposedly made immutable, violating audit integrity.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth/src/elspeth/contracts/schema_contract.py
- Line(s): 541-548, 563-583, 634-640, 717-728
- Function/Method: `PipelineRow.__init__`

## Evidence

`PipelineRow` claims Tier 1 immutability, but its constructor only wraps a shallow copy of the top-level dict:

```python
if type(data) is not dict:
    raise TypeError(...)
self._data = types.MappingProxyType(data.copy())
```

Source: [schema_contract.py](/home/john/elspeth/src/elspeth/contracts/schema_contract.py#L541)

That protects only `row["field"] = ...`. It does not freeze nested containers. `__getitem__` returns the stored object directly:

```python
normalized = self._contract.resolve_name(key)
return self._data[normalized]
```

Source: [schema_contract.py](/home/john/elspeth/src/elspeth/contracts/schema_contract.py#L575)

So a transform can do `row["payload"]["status"] = "changed"` or `row["items"].append(...)` and mutate the row in place even though `PipelineRow` is documented as immutable. The same shallow behavior is preserved when exporting:

```python
return dict(self._data)
```

Source: [schema_contract.py](/home/john/elspeth/src/elspeth/contracts/schema_contract.py#L640)

The repository already has a standard recursive freeze/thaw utility for exactly this problem:

```python
def deep_freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({k: deep_freeze(v) for k, v in value.items()})
    if isinstance(value, list):
        return tuple(deep_freeze(item) for item in value)
```

Source: [freeze.py](/home/john/elspeth/src/elspeth/contracts/freeze.py#L23)

Other audit-facing payload types use that utility:

```python
freeze_fields(self, "data")
```

Source: [row_data.py](/home/john/elspeth/src/elspeth/core/landscape/row_data.py#L74)

```python
freeze_fields(self, "row_data")
...
"row_data": deep_thaw(self.row_data),
```

Source: [aggregation_checkpoint.py](/home/john/elspeth/src/elspeth/contracts/aggregation_checkpoint.py#L54)

The engine also explicitly assumes `PipelineRow` immutability when copying tokens across branches:

```python
PipelineRow.__deepcopy__ preserves contract reference (immutable).
# CRITICAL: Use deepcopy to prevent nested mutable objects from being
# shared across forked children.
```

Source: [tokens.py](/home/john/elspeth/src/elspeth/engine/tokens.py#L235)

What the code does now:
- Freezes only the outer mapping.
- Returns nested mutable objects by reference.
- Lets callers mutate row state after creation without going through `update_row_data()`.

What it should do:
- Deep-freeze nested containers on construction.
- Deep-thaw on `to_dict()`/checkpoint export so serialized output stays JSON-like.

## Root Cause Hypothesis

`PipelineRow` implemented immutability with `MappingProxyType(data.copy())`, which looks immutable at the surface but bypasses ELSPETH’s established `deep_freeze`/`deep_thaw` contract for audit payloads. The result is a shallow wrapper masquerading as a Tier 1 immutable record.

## Suggested Fix

Use recursive freezing in `PipelineRow` and recursive thawing on export.

Example shape:

```python
from elspeth.contracts.freeze import deep_freeze, deep_thaw

self._data = deep_freeze(data)

def to_dict(self) -> dict[str, Any]:
    thawed = deep_thaw(self._data)
    assert isinstance(thawed, dict)
    return thawed
```

Also update `to_checkpoint_format()` and copy helpers to export via `deep_thaw(...)` rather than `dict(self._data)`.

Add regressions proving that:
- Mutating the original nested input after `PipelineRow(...)` does not affect the row.
- `row["nested"]["x"] = ...` and `row["items"].append(...)` fail or are impossible.
- `to_dict()` still returns plain `dict`/`list` structures.

## Impact

Nested pipeline payloads can be silently mutated after audit recording and after token creation. That can make the in-memory row diverge from the recorded row, allow plugins to alter data without producing a new token state, and break the assumption that branch copies are isolated immutable snapshots. This is an audit-trail violation, not just an API cleanliness issue.
