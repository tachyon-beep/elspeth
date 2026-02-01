# Design: Type NodeInfo.config with Discriminated Union

**Status:** Planning
**Created:** 2026-02-01
**Goal:** Replace `NodeInfo.config: dict[str, Any]` with typed dataclasses to catch integration bugs at compile time

## Problem Statement

`NodeInfo.config` is currently `dict[str, Any]`, which provides no type safety:
- Field name typos discovered at runtime, not compile time
- No documentation of what fields each node type stores
- Integration issues between graph construction and access sites go undetected

## Analysis

NodeInfo.config stores heterogeneous data depending on node type:

| Node Type | Config Origin | Fields Known to Framework? |
|-----------|---------------|---------------------------|
| Source | Plugin's config | No (opaque) |
| Sink | Plugin's config | No (opaque) |
| Transform | Plugin's config + `schema` | Partially (`schema` only) |
| Gate | Synthesized | Yes (`condition`, `routes`, `schema`, `fork_to`) |
| Aggregation | Synthesized | Yes (`trigger`, `output_mode`, `options`, `schema`) |
| Coalesce | Synthesized | Yes (`branches`, `policy`, `merge`, etc.) |

**Key insight:** Plugin configs are opaque (we don't control their shape), but framework-synthesized configs (Gate, Aggregation, Coalesce) are fully controlled by us.

## Solution: Discriminated Union of Typed Dataclasses

### Typed Config Dataclasses

```python
# contracts/node_config.py
from dataclasses import dataclass, asdict
from typing import Any, TypeVar

@dataclass(frozen=True, slots=True)
class SourceNodeConfig:
    """Source nodes carry opaque plugin config."""
    plugin_config: dict[str, Any]

@dataclass(frozen=True, slots=True)
class SinkNodeConfig:
    """Sink nodes carry opaque plugin config."""
    plugin_config: dict[str, Any]

@dataclass(frozen=True, slots=True)
class TransformNodeConfig:
    """Transform nodes: plugin config + framework-added schema."""
    plugin_config: dict[str, Any]
    schema: dict[str, Any]
    required_input_fields: list[str] | None = None

@dataclass(frozen=True, slots=True)
class GateNodeConfig:
    """Gate nodes: framework-controlled routing config."""
    routes: dict[str, str]
    schema: dict[str, Any]
    condition: str | None = None      # Only for config-driven gates
    fork_to: list[str] | None = None
    plugin_config: dict[str, Any] | None = None  # Only for plugin gates

@dataclass(frozen=True, slots=True)
class AggregationNodeConfig:
    """Aggregation nodes: fully framework-controlled."""
    trigger: dict[str, Any]  # TriggerSettings.model_dump()
    output_mode: str
    options: dict[str, Any]
    schema: dict[str, Any]

@dataclass(frozen=True, slots=True)
class CoalesceNodeConfig:
    """Coalesce nodes: fully framework-controlled."""
    branches: list[str]
    policy: str
    merge: str
    timeout_seconds: float | None = None
    quorum_count: int | None = None
    select_branch: str | None = None
```

### Union Type

```python
NodeConfig = (
    SourceNodeConfig
    | SinkNodeConfig
    | TransformNodeConfig
    | GateNodeConfig
    | AggregationNodeConfig
    | CoalesceNodeConfig
)
```

### Type Narrowing Helper

```python
T = TypeVar("T", bound=NodeConfig)

class NodeConfigTypeMismatch(TypeError):
    """Raised when node config doesn't match expected type for node_type."""
    def __init__(self, node_id: str, node_type: str, expected: type, actual: type) -> None:
        super().__init__(
            f"Node {node_id} has node_type='{node_type}' but config is "
            f"{actual.__name__}, expected {expected.__name__}"
        )
        self.node_id = node_id
        self.node_type = node_type
        self.expected = expected
        self.actual = actual


def narrow_config(config: NodeConfig, expected: type[T], node_id: str, node_type: str) -> T:
    """Narrow config to expected type, raising if mismatch.

    This is a type guard for accessing node-specific config fields.
    A mismatch indicates a bug in graph construction.
    """
    if isinstance(config, expected):
        return config
    raise NodeConfigTypeMismatch(node_id, node_type, expected, type(config))
```

### Serialization Helper

```python
def config_to_dict(config: NodeConfig) -> dict[str, Any]:
    """Serialize NodeConfig to dict for Landscape storage."""
    return asdict(config)
```

### Schema Access Helper

```python
def get_node_schema(node: NodeInfo) -> dict[str, Any]:
    """Extract schema from any node that has one."""
    config = node.config
    if isinstance(config, (TransformNodeConfig, GateNodeConfig,
                           AggregationNodeConfig, CoalesceNodeConfig)):
        return config.schema
    if isinstance(config, (SourceNodeConfig, SinkNodeConfig)):
        raise ValueError(f"Node {node.node_id} ({node.node_type}) has no schema field")
    raise NodeConfigTypeMismatch(node.node_id, node.node_type, NodeConfig, type(config))
```

### NodeInfo Update

```python
# core/dag.py
@dataclass
class NodeInfo:
    node_id: NodeID
    node_type: str  # Discriminator: "source" | "transform" | "gate" | ...
    plugin_name: str
    config: NodeConfig  # <- Changed from dict[str, Any]
    input_schema: type[PluginSchema] | None = None
    output_schema: type[PluginSchema] | None = None
    input_schema_config: SchemaConfig | None = None
    output_schema_config: SchemaConfig | None = None
```

## Access Patterns

### Direct Attribute Access After Narrowing

```python
def process_gate(node: NodeInfo) -> None:
    config = narrow_config(node.config, GateNodeConfig, node.node_id, node.node_type)

    # mypy now knows config.routes exists
    for route, destination in config.routes.items():
        ...
```

### Landscape Recording

```python
# orchestrator.py
from elspeth.contracts.node_config import config_to_dict

self._landscape.record_node(..., config=config_to_dict(node.config), ...)
```

### Plugin Config Access

```python
# Sink path access
config = narrow_config(sink_node.config, SinkNodeConfig,
                       sink_node.node_id, sink_node.node_type)
path = config.plugin_config["path"]  # Plugin-specific field remains opaque
```

## Implementation Order

1. **Add the new types** (`contracts/node_config.py`) - zero blast radius
2. **Update NodeInfo type annotation** - tests will fail
3. **Update construction sites in dag.py** - `from_plugin_instances()`
4. **Update access sites in dag.py** - schema/options/required_input_fields reads
5. **Update orchestrator access sites** - Landscape recording, sink path
6. **Update plugin initialization** - pass `plugin_config`, not full config
7. **Add tests** - unit tests for types, integration tests for production path

## Files to Modify

| File | Change Type | Scope |
|------|-------------|-------|
| `contracts/node_config.py` | **NEW** | ~100 lines |
| `core/dag.py` | Modify | NodeInfo + ~15 construction/access sites |
| `engine/orchestrator.py` | Modify | ~3-5 access sites |
| `plugins/base.py` | Modify | Gate init (~2 sites) |
| `tests/contracts/test_node_config.py` | **NEW** | ~50 lines |

## Testing Strategy

### Layer 1: Static Analysis (mypy)
- Wrong config type passed to `graph.add_node()`
- Accessing `.routes` on a `SourceNodeConfig`
- Missing required fields in config construction

### Layer 2: Unit Tests for Config Types
- Construction with required/optional fields
- `narrow_config()` success and mismatch cases
- `config_to_dict()` round-trip

### Layer 3: Integration Tests - Production Path
- `ExecutionGraph.from_plugin_instances()` creates correctly typed configs
- Use production factories per CLAUDE.md test path integrity rule

### Layer 4: Existing Test Suite
- Run full suite - any `node.config["field"]` access will fail, revealing missed sites

## What We Gain

- **Compile-time safety:** mypy catches field access on wrong node types
- **Typo prevention:** Field names caught at construction time
- **Self-documenting:** Reading the dataclass shows exactly what each node type stores
- **Explicit boundary:** Clear what's framework-controlled vs plugin-opaque

## Estimated Effort

2-3 hours
