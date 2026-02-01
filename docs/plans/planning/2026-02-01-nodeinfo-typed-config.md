# Design: Type NodeInfo.config with Discriminated Union

**Status:** Planning
**Created:** 2026-02-01
**Updated:** 2026-02-01 (post-review)
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
| Coalesce | Synthesized | Yes (`branches`, `policy`, `merge`, `schema`, etc.) |

**Key insight:** Plugin configs are opaque (we don't control their shape), but framework-synthesized configs (Gate, Aggregation, Coalesce) are fully controlled by us.

## Solution: Discriminated Union of Typed Dataclasses

### Typed Config Dataclasses

```python
# contracts/node_config.py
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, TypeVar, TypeAlias, overload

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
    required_input_fields: list[str] | None = None  # Promoted from options

@dataclass(frozen=True, slots=True)
class CoalesceNodeConfig:
    """Coalesce nodes: fully framework-controlled."""
    branches: list[str]
    policy: str
    merge: str
    schema: dict[str, Any]  # Schema from first branch (computed during construction)
    timeout_seconds: float | None = None
    quorum_count: int | None = None
    select_branch: str | None = None
```

### Union Type

```python
NodeConfig: TypeAlias = (
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


# Overloads for better mypy inference
@overload
def narrow_config(
    config: NodeConfig, expected: type[SourceNodeConfig], node_id: str, node_type: str
) -> SourceNodeConfig: ...

@overload
def narrow_config(
    config: NodeConfig, expected: type[SinkNodeConfig], node_id: str, node_type: str
) -> SinkNodeConfig: ...

@overload
def narrow_config(
    config: NodeConfig, expected: type[TransformNodeConfig], node_id: str, node_type: str
) -> TransformNodeConfig: ...

@overload
def narrow_config(
    config: NodeConfig, expected: type[GateNodeConfig], node_id: str, node_type: str
) -> GateNodeConfig: ...

@overload
def narrow_config(
    config: NodeConfig, expected: type[AggregationNodeConfig], node_id: str, node_type: str
) -> AggregationNodeConfig: ...

@overload
def narrow_config(
    config: NodeConfig, expected: type[CoalesceNodeConfig], node_id: str, node_type: str
) -> CoalesceNodeConfig: ...

@overload
def narrow_config(
    config: NodeConfig, expected: type[T], node_id: str, node_type: str
) -> T: ...

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
    """Serialize NodeConfig to dict for Landscape storage.

    Performance: Called once per node during graph construction.
    NOT on the hot path (not called per row).
    """
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
@dataclass(slots=True)  # Add slots for memory efficiency
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

## Critical: Single-Phase Construction Refactor

### The Problem

The current `from_plugin_instances()` constructs nodes in phases:
1. Create nodes with initial config
2. Add edges between nodes
3. Propagate schemas (coalesce gets schema from upstream branches)

This causes a **mutation at dag.py:789**:
```python
graph.get_node_info(coalesce_id).config["schema"] = first_schema
```

With `frozen=True` dataclasses, this mutation would crash.

### The Solution: Compute Before Create

Refactor `from_plugin_instances()` to compute all schemas BEFORE creating nodes:

```python
def from_plugin_instances(
    cls,
    source: SourceProtocol,
    transforms: list[TransformProtocol],
    sinks: dict[str, SinkProtocol],
    gates: list[GateSettings] | None = None,
    coalesce_settings: list[CoalesceSettings] | None = None,
    ...
) -> ExecutionGraph:
    """Build execution graph with typed, frozen configs.

    Construction happens in explicit phases:
    1. Compute topology (edges, branch mappings) - no nodes created yet
    2. Compute schemas for all nodes based on topology
    3. Create nodes with complete, frozen configs
    """
    graph = cls()

    # PHASE 1: Compute topology without creating nodes
    topology = _compute_dag_topology(
        source=source,
        transforms=transforms,
        sinks=sinks,
        gates=gates,
        coalesce_settings=coalesce_settings,
    )

    # PHASE 2: Compute schemas (now we know all connections)
    schemas = _compute_node_schemas(topology)

    # PHASE 3: Create nodes with complete configs
    for node_def in topology.nodes:
        config = _build_typed_config(node_def, schemas.get(node_def.id))
        graph.add_node(
            node_def.id,
            node_type=node_def.node_type,
            plugin_name=node_def.plugin_name,
            config=config,  # Frozen and complete
            ...
        )

    # PHASE 4: Add edges (nodes are immutable, only graph structure changes)
    for edge in topology.edges:
        graph.add_edge(edge.source, edge.target, ...)

    return graph
```

### Why This is the Right Fix

1. **Objects complete at creation** - No "fix up later" pattern
2. **Immutability preserved** - `frozen=True` works correctly
3. **Explicit phases** - Construction logic is clearer
4. **Follows CLAUDE.md** - "Schemas are immutable after graph construction"
5. **Consistent with RuntimeConfig pattern** - Same approach as `RuntimeRetryConfig.from_settings()`

### Topology Helper Types

```python
@dataclass
class NodeDefinition:
    """Node metadata computed during topology phase."""
    id: NodeID
    node_type: str
    plugin_name: str
    plugin_config: dict[str, Any] | None  # For plugin nodes
    framework_fields: dict[str, Any]  # For framework-synthesized nodes

@dataclass
class EdgeDefinition:
    """Edge metadata computed during topology phase."""
    source: NodeID
    target: NodeID
    edge_type: str  # "continue", "route", "fork", etc.

@dataclass
class DAGTopology:
    """Complete DAG structure before node creation."""
    nodes: list[NodeDefinition]
    edges: list[EdgeDefinition]
    branch_to_coalesce: dict[str, str]  # branch_name -> coalesce_id
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
2. **Add topology helper types** (`core/dag.py` or `contracts/`) - zero blast radius
3. **Refactor `from_plugin_instances()` to single-phase construction** - critical step
   - Extract `_compute_dag_topology()`
   - Extract `_compute_node_schemas()`
   - Extract `_build_typed_config()`
   - Remove post-construction schema mutation at line 789
4. **Update NodeInfo type annotation** - tests will fail
5. **Update construction sites** - now use typed config creation
6. **Update access sites in dag.py** - schema/options/required_input_fields reads
7. **Update orchestrator access sites** - Landscape recording, sink path, CSV export
8. **Update plugin initialization** - pass `plugin_config`, not full config
9. **Add tests** - unit tests, integration tests, round-trip tests

## Files to Modify

| File | Change Type | Scope |
|------|-------------|-------|
| `contracts/node_config.py` | **NEW** | ~150 lines (configs + helpers + overloads) |
| `core/dag.py` | Modify | NodeInfo + refactor `from_plugin_instances()` (~200 lines touched) |
| `engine/orchestrator.py` | Modify | ~3-5 access sites including CSV export at line 1740 |
| `plugins/base.py` | Modify | Gate init (~2 sites) |
| `tests/contracts/test_node_config.py` | **NEW** | ~80 lines |
| `tests/core/test_dag_typed_config.py` | **NEW** | ~100 lines (single-phase construction tests) |

## Testing Strategy

### Layer 1: Static Analysis (mypy)
- Wrong config type passed to `graph.add_node()`
- Accessing `.routes` on a `SourceNodeConfig`
- Missing required fields in config construction

### Layer 2: Unit Tests for Config Types
- Construction with required/optional fields
- `narrow_config()` success and mismatch cases
- `config_to_dict()` round-trip
- Frozen config prevents mutation (raises `FrozenInstanceError`)
- Empty list vs None semantics for optional fields

### Layer 3: Integration Tests - Production Path
- `ExecutionGraph.from_plugin_instances()` creates correctly typed configs
- Config-driven gates (from `GateSettings`) get `GateNodeConfig`
- Coalesce nodes have schema computed during construction (not mutated after)
- Use production factories per CLAUDE.md test path integrity rule

### Layer 4: Landscape Round-Trip Test (CRITICAL)
```python
def test_typed_configs_survive_landscape_storage(landscape_db):
    """Verify typed NodeConfigs serialize to Landscape correctly."""
    graph = ExecutionGraph.from_plugin_instances(...)
    run_id = orchestrator.execute(graph)

    # Read back from Landscape
    nodes = landscape.get_nodes(run_id)
    for node in nodes:
        config_dict = json.loads(node.config_json)
        assert isinstance(config_dict, dict)
        # Verify structure matches expected fields for node type
```

### Layer 5: Existing Test Suite
- Run full suite - any `node.config["field"]` access will fail, revealing missed sites
- Verify CSV export still works (orchestrator.py:1740 accesses `sink.config["path"]`)

## What We Gain

- **Compile-time safety:** mypy catches field access on wrong node types
- **Typo prevention:** Field names caught at construction time
- **Self-documenting:** Reading the dataclass shows exactly what each node type stores
- **Explicit boundary:** Clear what's framework-controlled vs plugin-opaque
- **Immutability guarantee:** Frozen configs can't be accidentally mutated
- **Single-phase construction:** Objects complete at creation, no "fix up later"

## Risks and Mitigations

| Risk | Severity | Mitigation |
|------|----------|------------|
| Single-phase refactor more complex than expected | Medium | Topology helpers make phases explicit; can test each phase independently |
| Missed access sites in orchestrator | Low | Layer 5 testing catches all dict accesses |
| Landscape serialization breaks | Low | Layer 4 round-trip test catches this |
| CSV export path access breaks | Medium | Explicitly test CSV export; update to use `plugin_config["path"]` |

## Estimated Effort

4-6 hours total:
- Typed config dataclasses: 1 hour
- Single-phase construction refactor: 2-3 hours
- Access site updates: 1 hour
- Testing: 1 hour

## Review Feedback Addressed

This design incorporates feedback from the 4-perspective review:

1. **Architecture:** Added `schema` to `CoalesceNodeConfig` (was missing)
2. **Python Engineering:** Added `@overload` for `narrow_config()`, `TypeAlias` for union, `slots=True` for `NodeInfo`
3. **Quality Assurance:** Added Landscape round-trip test, addressed mutation conflict with single-phase construction
4. **Systems Thinking:** Chose Option B (refactor) over Option A (remove frozen) for architectural correctness
