## Summary

`NodeInfo` claims graph node configs are frozen, but `models.py` leaves `config` as a mutable nested `dict`, so post-build mutations can silently change audited node configuration after node IDs were already derived from the original payload.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth/src/elspeth/core/dag/models.py
- Line(s): 83-115
- Function/Method: `NodeInfo.__post_init__`

## Evidence

`NodeInfo` is documented as immutable audit metadata, but the implementation never freezes its container field:

```python
@dataclass(frozen=True, slots=True)
class NodeInfo:
    ...
    config: NodeConfig = field(default_factory=dict)
    ...
    def __post_init__(self) -> None:
        if len(self.node_id) > _NODE_ID_MAX_LENGTH:
            ...
```

Source: `/home/john/elspeth/src/elspeth/core/dag/models.py:83-115`

The rest of the DAG layer assumes this object is safe to freeze only later, and only shallowly:

```python
# Freeze all NodeInfo configs now that schema resolution is complete.
# ...
# Note: This is a shallow freeze (top-level only).
for _, attrs in graph._graph.nodes(data=True):
    info = attrs["info"]
    if isinstance(info.config, dict):
        object.__setattr__(info, "config", MappingProxyType(info.config))
```

Source: `/home/john/elspeth/src/elspeth/core/dag/builder.py:963-975`

That shallow wrapper does not protect nested structures such as `config["schema"]["fields"]`, and for sources/sinks the graph stores the plugin’s original config object by reference:

```python
source_config = source.config
...
graph.add_node(..., config=source_config, ...)
...
sink_config = sink.config
graph.add_node(..., config=sink_config, ...)
```

Source: `/home/john/elspeth/src/elspeth/core/dag/builder.py:193-215`

Plugins themselves retain those mutable dicts directly:

```python
self.config = config
```

Source: `/home/john/elspeth/src/elspeth/plugins/infrastructure/base.py:191`, `/home/john/elspeth/src/elspeth/plugins/infrastructure/base.py:496`, `/home/john/elspeth/src/elspeth/plugins/infrastructure/base.py:683`

Node IDs are hashed from the original config during graph construction:

```python
config_str = canonical_json(config)
config_hash = hashlib.sha256(config_str.encode()).hexdigest()[:12]
```

Source: `/home/john/elspeth/src/elspeth/core/dag/builder.py:148-167`

But the Landscape later records `node_info.config` again as canonical JSON and a fresh hash:

```python
config_json = canonical_json(config)
config_hash = stable_hash(config)
```

Source: `/home/john/elspeth/src/elspeth/core/landscape/data_flow_repository.py:939-973`

So a nested mutation after graph build but before node registration changes the persisted audit config without changing the already-issued `node_id`. That breaks the “frozen after construction” guarantee in `models.py` and can make the audit trail report a config that was not the config used to derive graph identity.

## Root Cause Hypothesis

`NodeInfo` is a frozen dataclass in name only. `models.py` stores a mutable `dict[str, Any]` and performs no deep-freeze in `__post_init__`, even though the rest of the system treats node metadata as immutable audit state. The later shallow `MappingProxyType` patch in the builder protects only top-level assignment, not nested mutation or aliasing to plugin-owned config objects.

## Suggested Fix

Make `NodeInfo` enforce true deep immutability in `models.py` instead of relying on the builder’s shallow post-processing.

A concrete direction:

```python
from collections.abc import Mapping
from elspeth.contracts.freeze import freeze_fields

@dataclass(frozen=True, slots=True)
class NodeInfo:
    ...
    config: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        freeze_fields(self, "config")
        if len(self.node_id) > _NODE_ID_MAX_LENGTH:
            ...
```

Then adjust consumers that need mutable JSON-like structures to use `deep_thaw()` or explicit copies at the point of use rather than keeping mutable state inside `NodeInfo`. That keeps the invariant in the model where it belongs and prevents aliasing from plugin-owned config dicts.

## Impact

Audit integrity is weakened. A plugin or any in-process code that mutates nested config after graph construction can change the configuration persisted in Landscape while leaving the precomputed `node_id` unchanged. That creates a mismatch between graph identity, checkpoint/determinism assumptions, and the recorded node configuration, which is exactly the sort of “frozen metadata drift” the audit model is supposed to prevent.
