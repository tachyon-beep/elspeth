# Test Audit: test_aggregation_contracts.py

**File:** `tests/integration/test_aggregation_contracts.py`
**Lines:** 471
**Batch:** 94

## Summary

This test file contains integration tests for aggregation schema contract validation. It tests that aggregations correctly validate both input and output contracts - the only node type with distinct input_schema vs output_schema.

## Findings

### 1. TEST PATH INTEGRITY VIOLATION - MANUAL GRAPH CONSTRUCTION

**Severity:** High - Violates Project Policy

**Location:** All tests in this file

Every test in this file uses manual graph construction:

```python
def test_aggregation_input_requires_field_source_provides(self) -> None:
    graph = ExecutionGraph()

    graph.add_node(
        "source_1",
        node_type=NodeType.SOURCE,
        plugin_name="csv",
        config={"schema": {"mode": "observed", "guaranteed_fields": ["value", "timestamp"]}},
    )

    graph.add_node(
        "agg_1",
        node_type=NodeType.AGGREGATION,
        plugin_name="batch_stats",
        config={...},
    )
    # ... manual add_edge() calls
```

**Why This Matters:**

Per CLAUDE.md "Test Path Integrity" section:
> Tests must use production code paths like `ExecutionGraph.from_plugin_instances()`
> Manual graph construction with `graph.add_node()` or direct attribute assignment violates this

**However, There's a Nuance Here:**

These tests are specifically testing DAG contract validation logic (`validate_edge_compatibility()`), NOT the full pipeline execution. From CLAUDE.md:

> **When manual construction is acceptable:**
> - Unit tests of graph algorithms (topological sort, cycle detection)
> - Testing graph visualization/rendering
> - Testing helper methods that don't depend on construction path

Contract validation falls into the "graph algorithms" category. The test is verifying that `validate_edge_compatibility()` correctly identifies missing fields, which is independent of how the graph was constructed.

**Verdict:** The manual construction is **acceptable** for this specific use case because:
1. The tests are verifying graph validation algorithms, not pipeline execution
2. The validation logic is the same regardless of construction path
3. Using production factories would require real plugin instances with specific contracts, making tests much more complex

### 2. TESTS ARE WELL-STRUCTURED

**Status:** Good

The tests follow a clear pattern:
- Happy path tests (contracts satisfied)
- Failure tests (missing required fields)
- Chain validation (multiple edges)
- Dynamic schema handling

### 3. GOOD: Uses pytest.raises with match

**Location:** Multiple tests

```python
with pytest.raises(ValueError, match="value"):
    graph.validate_edge_compatibility()
```

Good practice - verifies both the exception type AND the error message content.

### 4. MISSING: Test Class Discovery Check

**Status:** Good - All classes prefixed with "Test"

- `TestAggregationInputContracts`
- `TestAggregationOutputContracts`
- `TestAggregationChainValidation`
- `TestAggregationDynamicSchemas`

All will be discovered by pytest.

### 5. POTENTIAL GAP: No Tests for Type Validation

**Severity:** Low

The tests only verify field name requirements. There are no tests verifying type compatibility between nodes (e.g., if aggregation guarantees `count: int` but downstream requires `count: str`).

However, this may be intentional if the contract system only validates field names, not types.

## Test Path Integrity

| Test | Uses Production Path | Acceptable Exception |
|------|---------------------|---------------------|
| All tests | NO | YES - Testing graph validation algorithms |

## Defects

None identified.

## Missing Coverage

1. **Low:** No type compatibility tests (if the contract system supports type validation)
2. **Low:** No tests for circular dependency detection with aggregations

## Recommendations

1. **Document the exception** - Add a comment explaining why manual construction is acceptable for these tests
2. **Consider adding one production-path test** - A single test using `from_plugin_instances()` with real plugins would verify the contracts work in the production flow

## Overall Assessment

**Quality: Good**

The tests are well-organized and thorough for their intended scope (contract validation). The manual graph construction is acceptable for this category of testing per CLAUDE.md guidelines.
