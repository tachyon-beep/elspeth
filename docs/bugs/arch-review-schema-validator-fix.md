# Architecture Review: Schema Validator DAG-Aware Fix

**Proposed Fix:** P1-2026-01-21-schema-validator-ignores-dag-routing
**Reviewer:** axiom-system-architect:architecture-critic
**Date:** 2026-01-24
**Status:** ARCHITECTURE REVIEW

---

## Executive Summary

**Assessment:** The proposed fix is architecturally sound but incomplete. It correctly identifies the root cause (list-based validation vs. graph topology) and proposes the right solution (edge-based validation), but has three critical gaps that will cause problems during implementation.

**Critical Issues:** 2
**High Issues:** 1
**Recommendation:** Approve fix approach with mandatory changes before implementation.

---

## Proposed Fix Overview

**Current state:**
- `validate_pipeline_schemas()` accepts flat lists of plugin schemas
- Validates linear chain: source → transforms → ALL sinks from final transform
- Ignores ExecutionGraph edges and routing labels

**Proposed state:**
- `validate_pipeline_schemas()` accepts ExecutionGraph + node schema map
- Validates along actual edges: for each edge, verify producer output → consumer input compatibility
- Respects routing: sinks validated against their actual upstream nodes

---

## Architecture Assessment

### ✅ Strengths

1. **Root cause correct:** Identified temporal mismatch (validator predates DAG features) and interface mismatch (lists vs. graph)
2. **Solution aligns with contract:** Plugin protocol requires "compatibility between connected nodes" - edge-based validation delivers this
3. **Uses existing infrastructure:** Leverages `ExecutionGraph.get_edges()` instead of reinventing graph traversal
4. **Backwards compatibility plan:** Proposes keeping old function as `validate_pipeline_schemas_linear()` for transition

---

## Critical Issues

### ❌ CRITICAL #1: Gates Have No Output Schema

**Evidence:**

`src/elspeth/core/dag.py:331-351`
```python
graph.add_node(
    gid,
    node_type="gate",
    plugin_name=f"config_gate:{gate_config.name}",
    config=gate_node_config,
)
```

Gates are **routing nodes**, not transform nodes. They don't have `input_schema` or `output_schema` - they just evaluate conditions and route.

**Impact on proposed fix:**

Proposed code:
```python
producer_output = plugin_schemas.get(from_node, {}).output_schema
consumer_input = plugin_schemas.get(to_node, {}).input_schema
```

When `from_node` is a gate:
- `plugin_schemas.get(gate_id)` will have `output_schema = None` (gates don't transform data)
- Validation will skip the edge (lines: "Skip if either schema is None")
- **Gate → sink edges will NEVER be validated**

**This defeats the entire purpose of the fix.**

**Correct approach:**

Gates pass through data unchanged. For validation:
- Gate's effective output schema = gate's effective input schema
- Gate's effective input schema = schema of data flowing INTO the gate

Algorithm:
```python
def get_effective_producer_schema(node_id: str, graph: ExecutionGraph, schemas: dict) -> type[PluginSchema] | None:
    node_info = graph.get_node(node_id)

    if node_info.node_type == "gate":
        # Gates pass through - find upstream producer
        incoming_edges = graph.get_incoming_edges(node_id)
        if not incoming_edges:
            return None
        # All incoming edges should have same schema (validated separately)
        upstream_node = incoming_edges[0].from_node
        return get_effective_producer_schema(upstream_node, graph, schemas)

    return schemas[node_id].output_schema
```

**Severity:** CRITICAL - proposed fix will not catch the bugs it's designed to catch.

---

### ❌ CRITICAL #2: Aggregation Nodes Change Schema Mid-Pipeline

**Evidence:**

`src/elspeth/core/dag.py:301-330`
```python
graph.add_node(
    aid,
    node_type="aggregation",
    plugin_name=agg_config.plugin,
    config=agg_node_config,
)
```

Aggregation transforms are **stateful batch processors**:
- Input: individual rows with schema A
- Output: batch result with schema B (different from A)

Example: `BatchStats` aggregation
- Input: `{"value": float, "category": str}` (individual rows)
- Output: `{"mean": float, "count": int, "category": str}` (batch statistics)

**Impact on proposed fix:**

Aggregation nodes ARE in `config.transforms`, so they'll be in `plugin_schemas` map. But:
- Aggregation `input_schema` != aggregation `output_schema`
- Edge BEFORE aggregation validates against `input_schema`
- Edge AFTER aggregation validates against `output_schema`

Proposed code doesn't distinguish these cases - it just looks up `output_schema` for the producer.

**Correct approach:**

Aggregation nodes need special handling:
```python
if node_info.node_type == "aggregation":
    # Outgoing edges use output_schema (batch result)
    return schemas[node_id].output_schema
elif node_info.node_type in ("transform", "source"):
    return schemas[node_id].output_schema
```

But INCOMING edges to aggregation must validate against `input_schema`:
```python
# When validating edge
if consumer_node_info.node_type == "aggregation":
    consumer_schema = schemas[to_node].input_schema  # NOT output_schema
else:
    consumer_schema = schemas[to_node].input_schema
```

**Severity:** CRITICAL - aggregation pipelines will have false negatives or false positives.

---

### ❌ HIGH #3: Fork Edges Create Schema Fanout - Validation Incomplete

**Evidence:**

`src/elspeth/core/dag.py:363-387`
```python
if gate_config.fork_to:
    for branch in gate_config.fork_to:
        if branch in sink_ids:
            graph.add_edge(
                gid,
                sink_ids[branch],
                label=branch,
                mode=RoutingMode.COPY,  # ← COPY mode
            )
```

Fork gates use `RoutingMode.COPY` - the same token goes to multiple destinations.

**Schema validation implications:**

All fork destinations must be compatible with the SAME producer schema. But proposed validation just checks edges independently:

```python
for edge in graph.get_edges():
    # Validates each edge separately
```

**Missing validation:**

If fork destinations have **different** input schemas, all incompatible with producer:
- Each edge validation might pass (if producer has superset of fields)
- But fork semantics mean data must satisfy ALL destinations simultaneously
- Need to validate: producer schema ⊇ UNION(all fork destination required fields)

**Example failure case:**

```
Producer: {"id": int, "name": str, "value": float}
Fork to:
  - sink_a requires: {"id": int, "name": str}  ✓
  - sink_b requires: {"id": int, "value": float}  ✓
```

Both edges pass individually, but this is correct - producer HAS all fields.

**Actually, this is NOT a bug.** Edge-by-edge validation IS sufficient for forks because COPY mode sends full row to each destination.

**Revised assessment:** This is NOT an issue. Fork validation works correctly with edge-based approach.

---

## Medium Issues

### ⚠️ MEDIUM #1: Error Messages Will Be Cryptic

**Evidence:**

Proposed error format:
```python
errors.append(
    f"Edge {from_node} -> {to_node} (label='{edge.label}'): "
    f"producer missing required fields {missing}"
)
```

Actual node IDs from graph:
```python
node_id = f"{prefix}_{name}_{uuid.uuid4().hex[:8]}"
# Example: "sink_results_a3f7b9c1"
```

**User-facing error:**
```
Edge transform_field_mapper_b2e4d6f8 -> sink_results_a3f7b9c1 (label='continue'):
producer missing required fields {'score'}
```

**Users don't know node IDs.** They know plugin names and config names.

**Fix:**
```python
from_info = graph.get_node(from_node)
to_info = graph.get_node(to_node)

errors.append(
    f"Schema mismatch: {from_info.node_type} '{from_info.plugin_name}' "
    f"-> {to_info.node_type} '{to_info.plugin_name}' "
    f"(edge: {edge.label}): missing required fields {missing}"
)
```

Better output:
```
Schema mismatch: transform 'field_mapper' -> sink 'results' (edge: continue):
missing required fields {'score'}
```

**Severity:** MEDIUM - doesn't break functionality but creates poor UX.

---

### ⚠️ MEDIUM #2: No Validation for Circular Schema Dependencies

**While ExecutionGraph validates acyclicity, schema validation should verify NO circular schema dependencies.**

Wait - ExecutionGraph.validate() already checks `is_acyclic()`:

`src/elspeth/core/dag.py:125-133`
```python
if not self.is_acyclic():
    try:
        cycle = nx.find_cycle(self._graph)
        cycle_str = " -> ".join(f"{edge[0]}" for edge in cycle)
        raise GraphValidationError(f"Graph contains a cycle: {cycle_str}")
```

**This is already handled.** Not an issue.

---

## Low Issues

### ⚠️ LOW #1: Proposed Signature Breaks Type Safety

**Proposed:**
```python
plugin_schemas: dict[str, PluginSchemaInfo]
```

**Problem:** Dict allows runtime keyerrors. Should use typed container or validate keys exist.

**Better:**
```python
@dataclass
class ValidationContext:
    graph: ExecutionGraph
    schemas: dict[str, PluginSchemaInfo]

    def get_schema(self, node_id: str) -> PluginSchemaInfo:
        if node_id not in self.schemas:
            raise ValueError(f"No schema found for node {node_id}")
        return self.schemas[node_id]
```

**Severity:** LOW - runtime error vs. type error, but both are crashes.

---

## Cross-Cutting Concerns

### Testability

**Proposed test cases are good but incomplete:**

```python
def test_detects_gate_mid_pipeline_schema_mismatch():
def test_validates_fork_branches_independently():
def test_coalesce_validates_all_input_branches():
```

**Missing test cases:**

1. **Aggregation schema transitions:**
   ```python
   def test_aggregation_input_schema_validated_separately_from_output():
       """Edges INTO aggregation validate against input_schema,
          edges OUT OF aggregation validate against output_schema."""
   ```

2. **Multi-hop gate chains:**
   ```python
   def test_chained_gates_validate_transitively():
       """gate1 -> gate2 -> sink validates correctly."""
   ```

3. **Dynamic schemas (None) in graph:**
   ```python
   def test_dynamic_schema_skips_validation_for_edge():
       """If producer or consumer has None schema, skip edge."""
   ```

4. **Error message clarity:**
   ```python
   def test_error_messages_include_plugin_names_not_node_ids():
       """Validation errors reference config names, not UUIDs."""
   ```

---

## Mandatory Changes Before Implementation

### MUST FIX (CRITICAL)

1. **Handle gate nodes as pass-through for schema validation**
   - Gates have no schema transformation
   - Use upstream producer schema for gate → X edges
   - Add `get_effective_producer_schema()` helper

2. **Handle aggregation nodes with dual schemas**
   - Incoming edges validate against `input_schema`
   - Outgoing edges validate against `output_schema`
   - Update edge validation logic to check consumer node type

### SHOULD FIX (HIGH/MEDIUM)

3. **Improve error messages with plugin names**
   - Replace node IDs with human-readable plugin names
   - Include edge label context

4. **Add comprehensive test coverage**
   - Aggregation input/output schema validation
   - Chained gates
   - Dynamic schema handling
   - Error message format verification

---

## Approval Decision

**Status: CONDITIONAL APPROVAL**

**Approve IF:**
1. Critical #1 (gate schema handling) is fixed before implementation
2. Critical #2 (aggregation schema handling) is fixed before implementation
3. Test cases for both critical fixes are added

**Rationale:**

The core architectural approach (graph-aware edge-based validation) is correct and aligns with plugin protocol contract. The implementation details have gaps that will cause the fix to fail in production, but these are fixable with focused changes to the algorithm.

**Do NOT implement proposed solution as-written.** Fix critical issues first.

---

## Recommendation for Next Steps

1. **Update proposed fix to handle special node types:**
   - Add `get_effective_producer_schema()` for gates
   - Add consumer node type check for aggregations

2. **Write failing tests first (TDD):**
   - Create test pipeline: `source -> gate -> sink` where sink requires field gate doesn't add
   - Create test pipeline: `source -> aggregation -> sink` where sink requires batch output field
   - Verify both FAIL with current validator
   - Verify both PASS after fix

3. **Implement graph-aware validator with special node handling**

4. **Verify all new tests pass**

5. **Run full test suite to ensure no regressions**

---

## Evidence Summary

| Finding | Evidence Location | Severity |
|---------|------------------|----------|
| Gates have no output schema | `dag.py:331-351` | CRITICAL |
| Aggregations have dual schemas | `dag.py:301-330` | CRITICAL |
| Error messages use node IDs | Proposed code | MEDIUM |
| Missing test coverage | Proposed tests | MEDIUM |

---

## Appendix: Reference Implementation Sketch

```python
def validate_pipeline_schemas(
    graph: ExecutionGraph,
    plugin_schemas: dict[str, PluginSchemaInfo],
) -> list[str]:
    """Validate schema compatibility along graph edges."""
    errors = []

    for edge in graph.get_edges():
        # Get node info
        from_info = graph.get_node(edge.from_node)
        to_info = graph.get_node(edge.to_node)

        # Get effective producer schema (handles gates as pass-through)
        producer_schema = _get_effective_producer_schema(
            edge.from_node, from_info, graph, plugin_schemas
        )

        # Get consumer schema (handles aggregation dual schemas)
        consumer_schema = _get_effective_consumer_schema(
            edge.to_node, to_info, plugin_schemas
        )

        # Skip if either is None (dynamic schema)
        if producer_schema is None or consumer_schema is None:
            continue

        # Validate compatibility
        missing = _get_missing_required_fields(producer_schema, consumer_schema)
        if missing:
            errors.append(
                f"Schema mismatch: {from_info.node_type} '{from_info.plugin_name}' "
                f"-> {to_info.node_type} '{to_info.plugin_name}' "
                f"(edge: {edge.label}): producer missing required fields {missing}"
            )

    return errors


def _get_effective_producer_schema(
    node_id: str,
    node_info: NodeInfo,
    graph: ExecutionGraph,
    schemas: dict[str, PluginSchemaInfo],
) -> type[PluginSchema] | None:
    """Get effective output schema for a node.

    Gates are pass-through - return upstream producer schema.
    Aggregations, transforms, sources return their output_schema.
    """
    if node_info.node_type == "gate":
        # Gate is pass-through - find upstream producer
        incoming = graph.get_incoming_edges(node_id)
        if not incoming:
            return None
        # Recursively get upstream schema
        upstream_node = incoming[0].from_node
        upstream_info = graph.get_node(upstream_node)
        return _get_effective_producer_schema(upstream_node, upstream_info, graph, schemas)

    # Source, transform, aggregation have output_schema
    if node_id not in schemas:
        return None
    return schemas[node_id].output_schema


def _get_effective_consumer_schema(
    node_id: str,
    node_info: NodeInfo,
    schemas: dict[str, PluginSchemaInfo],
) -> type[PluginSchema] | None:
    """Get effective input schema for a node.

    Aggregations have separate input_schema (for individual rows).
    All other nodes use input_schema.
    """
    if node_id not in schemas:
        return None
    return schemas[node_id].input_schema
```

**This reference implementation handles both critical issues.**
