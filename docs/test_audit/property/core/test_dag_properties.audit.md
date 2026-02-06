# Audit: tests/property/core/test_dag_properties.py

## Overview
Property-based tests for DAG operations - topological sort, validation, acyclicity detection, and schema contract (guaranteed fields) validation.

**Lines:** 789
**Test Classes:** 8
**Test Methods:** 30+

## Audit Results

### 1. Defects
**PASS** - No defects found.

Tests correctly verify:
- Topological order respects all edges
- Source appears first, sinks appear last
- Validation rejects cycles, missing source/sink, duplicate edge labels
- Schema contract validation (guaranteed_fields vs required_input_fields)

### 2. Overmocking
**PASS** - No mocking used.

Tests directly exercise `ExecutionGraph` methods:
- `topological_order()`
- `validate()`
- `is_acyclic()`
- `validate_edge_compatibility()`

### 3. Missing Coverage
**MINOR** - Some gaps:

1. **Complex DAG structures**: Only tests linear, diamond, and multi-sink. No tests for:
   - Multiple diamonds in sequence
   - DAGs with 10+ nodes
2. **Edge attributes**: Tests edge labels but not other edge metadata
3. **Node removal**: No tests for graph mutation after construction

### 4. Tests That Do Nothing
**PASS** - All tests have meaningful assertions.

Good topological sort verification:
```python
for edge in graph.get_edges():
    from_idx = index_map[edge.from_node]
    to_idx = index_map[edge.to_node]
    assert from_idx < to_idx, (
        f"Edge {edge.from_node} -> {edge.to_node} violates topological order"
    )
```

### 5. Inefficiency
**MINOR** - Strategy complexity.

The `@st.composite` strategies (lines 38-110) are complex but necessary. However:

- `diamond_pipelines` and `multi_sink_pipelines` don't use the `draw` parameter meaningfully
- They draw `st.just(None)` to satisfy the composite requirement

**Recommendation:** These could be regular functions returning graphs, not strategies.

### 6. Structural Issues
**PASS** - Well organized.

Clear class separation:
- `TestTopologicalOrderProperties` - topo sort tests
- `TestValidationProperties` - validation success tests
- `TestValidationFailureProperties` - validation rejection tests
- `TestAcyclicityProperties` - cycle detection tests
- `TestGraphConsistencyProperties` - structural consistency
- `TestGuaranteedFieldsProperties` - schema contract tests

## Schema Contract Testing (Critical Section)

Lines 441-789 contain comprehensive schema contract tests:

1. **Superset guarantees satisfy requirements** - fundamental contract
2. **Missing fields detected** - validation catches violations
3. **Coalesce intersection property** - only common fields survive join
4. **Gate passthrough inheritance** - gates don't transform
5. **Empty guarantees fail any requirement**
6. **Empty requirements always satisfied**

These are critical for ELSPETH's DAG-time validation feature.

## Field Name Strategy

Uses ASCII-only field names for schema validation:
```python
ascii_field_names = st.text(
    min_size=1,
    max_size=10,
    alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ",
)
```

This is correct - schema validation requires valid Python identifiers.

## Summary

| Criterion | Status | Notes |
|-----------|--------|-------|
| Defects | PASS | No bugs found |
| Overmocking | PASS | No mocking needed |
| Missing Coverage | MINOR | Complex DAGs not tested |
| Tests That Do Nothing | PASS | Strong assertions |
| Inefficiency | MINOR | Unnecessary composite strategies |
| Structural Issues | PASS | Well organized |

**Overall:** EXCELLENT - Comprehensive DAG testing including critical schema contract validation. One of the most thorough property test files.
