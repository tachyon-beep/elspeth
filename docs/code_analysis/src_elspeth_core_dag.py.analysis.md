# Analysis: src/elspeth/core/dag.py

**Lines:** 1,364
**Role:** DAG construction and validation. Compiles pipeline configurations into directed acyclic graphs using NetworkX. Defines `ExecutionGraph` which handles node creation, edge wiring, fork/join topology, schema contract validation, topological sorting, and cycle detection. The `from_plugin_instances()` factory is the production entry point.
**Key dependencies:**
- Imports: `networkx`, `elspeth.contracts` (EdgeInfo, RoutingMode, check_compatibility, SchemaConfig, PluginSchema, type aliases), `elspeth.core.config` (AggregationSettings, CoalesceSettings, GateSettings), `elspeth.plugins.protocols` (SourceProtocol, TransformProtocol, SinkProtocol, GateProtocol), `elspeth.core.canonical` (canonical_json)
- Imported by: `elspeth.engine.orchestrator.core`, `elspeth.cli`, `elspeth.core.canonical`, `elspeth.core.checkpoint`, 100+ test files
**Analysis depth:** FULL

## Summary

The DAG module is well-structured and demonstrates careful attention to error handling, validation ordering, and audit integrity. The `from_plugin_instances()` factory method is the critical production path and contains thorough validation for fork/join topology, duplicate branches, and schema compatibility. However, there are several issues: a validation ordering gap where schema compatibility checks run before structural validation (cycle detection, reachability), mutable `NodeInfo` contradicting its immutability claim, protocol-violating `getattr` usage for `_output_schema_config`, and a `config["schema"]` key dependency that is implicit and undocumented in the contract chain. No data corruption or security vulnerabilities were found.

## Critical Findings

### [810 vs CLI:424] Schema validation runs before structural validation

**What:** `validate_edge_compatibility()` is called at line 810 inside `from_plugin_instances()`, but the structural `validate()` method (which checks for cycles, exactly-one-source, at-least-one-sink, reachability) is called separately by the CLI at line 424 of `cli.py`. This means schema compatibility validation runs on a graph that has not been verified to be acyclic or structurally valid.

**Why it matters:** The recursive methods `_get_effective_producer_schema()` (line 1019) and `_get_effective_guaranteed_fields()` (line 1313) walk backwards through the graph via incoming edges. If a cycle exists in the graph (which hasn't been checked yet), these recursive methods will enter infinite recursion, causing a stack overflow crash. While `from_plugin_instances()` constructs graphs in a linear chain pattern that cannot produce cycles through its own logic, a future code change that introduces cycle-capable wiring before the schema validation call would hit this silently.

**Evidence:**
```python
# Line 810 (inside from_plugin_instances):
graph.validate_edge_compatibility()  # Runs FIRST - no cycle check yet

# Line 812:
return graph

# CLI line 424 (after from_plugin_instances returns):
graph.validate()  # Runs SECOND - checks cycles, reachability, etc.
```

The recursive walk in `_get_effective_producer_schema`:
```python
# Line 1055-1056: Recursive call with no cycle guard
for from_id, _, _ in incoming:
    schema = self._get_effective_producer_schema(from_id)  # Could infinite-loop
```

### [467, 535, 567, 797, 800] Implicit `config["schema"]` contract across all node types

**What:** Multiple lines access `node.config["schema"]` as a bare dict key lookup (KeyError on missing). This assumes every source, transform, and aggregation config dict contains a `"schema"` key. The contract chain is: user YAML -> `SourceSettings.options` (raw dict) -> `source.config` (stored in `BaseSource.__init__`) -> `node.config["schema"]` in DAG construction. There is no validation that the `"schema"` key exists before access.

**Why it matters:** If a source plugin is instantiated with a config dict that lacks a `"schema"` key (e.g., a custom source that doesn't use `DataPluginConfig`), the DAG construction will crash with an unhelpful `KeyError: 'schema'` at line 467. The existing plugin base classes (`DataPluginConfig`) require schema, but the protocol (`SourceProtocol`) does not declare this constraint. This means the contract is enforced by convention (all current plugins use `DataPluginConfig`), not by the type system.

**Evidence:**
```python
# Line 467 - First gate's attempt to read upstream schema
upstream_schema = graph.get_node_info(prev_node_id).config["schema"]

# Line 535 - Aggregation reads transform schema
"schema": transform_config["schema"],

# Line 567 - Config gate reads upstream schema
"schema": graph.get_node_info(prev_node_id).config["schema"],

# Line 797 - Coalesce reads branch schema
first_schema = graph.get_node_info(first_from_node).config["schema"]
```

Per the CLAUDE.md Three-Tier Trust Model, `source.config` is the raw user-provided config dict (Tier 3 external data that crossed the trust boundary at plugin construction). By the time DAG reads `config["schema"]`, it's treating it as Tier 1 (crash on missing), but the contract that guarantees its presence is not enforced at the protocol level.

## Warnings

### [42-66] NodeInfo dataclass is mutable despite immutability claim

**What:** `NodeInfo` is a plain `@dataclass` (not `frozen=True`) with a mutable `config: dict[str, Any]` field. The docstring claims "Schemas are immutable after graph construction" but nothing enforces this. Line 807 deliberately mutates `config` after initial construction: `graph.get_node_info(coalesce_id).config["schema"] = first_schema`.

**Why it matters:** The docstring creates a false contract. Other engineers (or AI assistants) reading the docstring may assume immutability is enforced and write code that depends on it. The mutation at line 807 proves the dataclass cannot be frozen without refactoring the coalesce schema population logic. This is a consistency issue between documentation and implementation.

**Evidence:**
```python
@dataclass  # NOT frozen=True
class NodeInfo:
    """Schemas are immutable after graph construction."""  # False claim
    config: dict[str, Any] = field(default_factory=dict)  # Mutable

# Line 807 - Mutation after construction
graph.get_node_info(coalesce_id).config["schema"] = first_schema
```

### [480, 542] `getattr` with default violates CLAUDE.md prohibition

**What:** Lines 480 and 542 use `getattr(transform, "_output_schema_config", None)` to optionally extract computed schema config from transforms. The attribute `_output_schema_config` is NOT declared in `TransformProtocol` (checked in `protocols.py`) and NOT set in `BaseTransform` (checked in `base.py`). Only LLM transforms set it.

**Why it matters:** The CLAUDE.md explicitly prohibits defensive `getattr` patterns that hide bugs. While this is a legitimate case of an optional capability (not all transforms compute output schema configs), the proper fix per the project's standards is to either: (a) add `_output_schema_config: SchemaConfig | None` to the `TransformProtocol` with a default of `None` in `BaseTransform`, or (b) create a narrower protocol for transforms that compute schemas. The current approach means if a transform has a typo in the attribute name (e.g., `_output_schema_cfg`), the error is silently swallowed.

**Evidence:**
```python
# Line 480
output_schema_config = getattr(transform, "_output_schema_config", None)

# Line 542
agg_output_schema_config = getattr(transform, "_output_schema_config", None)
```

Neither `TransformProtocol` nor `BaseTransform` declares this attribute. Only `src/elspeth/plugins/llm/base.py` sets it (line 254).

### [421, 434, 455, 530] `type: ignore[attr-defined]` suppressions for protocol-declared attribute

**What:** Four lines suppress mypy `attr-defined` errors when accessing `.config` on plugin instances, even though `config: dict[str, Any]` IS declared in all plugin protocols (`SourceProtocol`, `TransformProtocol`, `SinkProtocol`).

**Why it matters:** These suppressions may be masking a real type system issue. If mypy cannot see `config` on the protocol, it may indicate that the protocol's `config` attribute declaration conflicts with the `__init__(self, config: ...)` parameter (a known mypy Protocol quirk). However, suppressing with `type: ignore` means if the protocol ever changes to remove `config`, these accesses would silently pass type checking while potentially crashing at runtime. Each suppression should have a comment explaining WHY mypy cannot see the attribute.

**Evidence:**
```python
source_config = source.config  # type: ignore[attr-defined]  # No explanation
sink_config = sink.config  # type: ignore[attr-defined]  # No explanation
transform_config = transform.config  # type: ignore[attr-defined]  # No explanation
```

### [114-127] `get_nx_graph()` exposes internal mutable state without protection

**What:** `get_nx_graph()` returns the internal `MultiDiGraph` directly, allowing callers to mutate the graph and bypass all `ExecutionGraph` invariants (edge label uniqueness, node info population, routing maps, etc.).

**Why it matters:** The docstring warns against direct manipulation, but the method returns the actual object, not a copy. The only current caller in production code (`canonical.py:199`) uses it read-only for topology hashing. However, this is a ticking time bomb: any future caller that modifies the returned graph would corrupt the `ExecutionGraph`'s internal state silently, potentially causing audit trail inconsistencies. For a system built on auditability, this access pattern is dangerous.

**Evidence:**
```python
def get_nx_graph(self) -> MultiDiGraph[str]:
    """Warning: Direct graph manipulation should be avoided."""
    return self._graph  # Returns actual mutable internal state
```

### [772-774] Missing edge to default sink when gates exist but no gate has continue route

**What:** Line 772-774 only connects the final pipeline node to the default sink when `not gates`. If gates exist but NONE of them have a `continue` route, the final non-gate node before the gates has already been wired to the first gate (line 582), and that gate routes exclusively to sinks. However, the last pipeline node (which may be the last gate) would have no "continue" edge to the default sink.

**Why it matters:** This is not a bug in the current logic since the `validate()` method would catch unreachable sinks. However, the conditional `if not gates` is fragile. It assumes that if any gate exists, the gate continue-route wiring (lines 748-770) handles all connectivity to the default sink. If a pipeline has gates where ALL routes go to specific sinks (no "continue" routes), AND the default sink is not explicitly targeted by any gate route, the default sink becomes unreachable. The `validate()` method would catch this, but the error message would be about unreachable nodes rather than a more helpful "no route to default sink" message.

## Observations

### [390-418] Node ID determinism depends on canonical JSON stability

The `node_id()` inner function uses `canonical_json(config)` followed by SHA-256 truncated to 48 bits (12 hex chars) for node ID generation. The 48-bit hash provides approximately 2^24 (16 million) resistance to birthday collisions. For typical pipelines with fewer than 100 nodes, this is adequate. However, the determinism guarantee depends on `canonical_json()` producing identical output for semantically identical configs across different Python versions and platforms. This is handled by RFC 8785, but worth noting as a dependency.

### [59] `node_type` is a string, not an enum

`NodeInfo.node_type` is typed as `str` with valid values documented in a comment: "source, transform, gate, aggregation, coalesce, sink". This is checked by string comparison throughout the module (e.g., lines 216, 279, 289, 926, 952, 957, 1042, 1340, 1348). A typo in any of these string comparisons would be a silent bug. The `NodeType` enum exists in `elspeth.contracts.enums` but is not used here.

### [1204-1239] `_get_schema_config_from_node` uses `config.get("schema")` (safe access)

This method correctly uses `.get("schema")` with a None fallback, unlike the direct `config["schema"]` accesses in `from_plugin_instances()`. This inconsistency suggests the safe pattern was applied later (for the contract validation helpers) while the original construction code retains the unsafe pattern. The two patterns should be consistent.

### [666-671] Duplicate fork branch detection is thorough

The check for duplicate fork branches using `Counter` is well-implemented and catches configuration errors early with clear error messages. This is good defensive validation at the configuration boundary.

### [698-718] Coalesce branch-gate validation is comprehensive

The validation that all coalesce-declared branches are actually produced by some fork gate is thorough and prevents silent configuration errors where a coalesce waits for branches that no gate will ever produce.

### [908-928] Edge validation iterates all edges then separately validates coalesce nodes

`validate_edge_compatibility()` first iterates all edges (line 922) and then separately iterates coalesce nodes (line 926-928). The per-edge validation skips coalesce target nodes (line 952-953). This two-phase approach is correct but the skip-then-validate pattern requires understanding both phases together. A comment cross-referencing the two phases would aid maintainability.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** Three items should be addressed before release:
1. Move `validate()` call (or at minimum the cycle check) to run BEFORE `validate_edge_compatibility()` inside `from_plugin_instances()`, preventing potential infinite recursion in the recursive schema walkers.
2. Add `_output_schema_config: SchemaConfig | None = None` to `TransformProtocol` and `BaseTransform` to eliminate the `getattr` usage and bring the code in line with the project's prohibition on defensive patterns.
3. Document or enforce the `config["schema"]` key requirement at the protocol level rather than relying on convention.

The remaining warnings (mutable NodeInfo, exposed internal graph, type: ignore suppressions) are lower priority but should be tracked for post-RC cleanup.

**Confidence:** HIGH -- Full file read with cross-reference to all major dependencies (protocols, schema config, config_base, cli_helpers, orchestrator, processor). The critical finding about validation ordering was verified by tracing the actual call chain from CLI through `from_plugin_instances()`.
