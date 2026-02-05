# Test Audit: tests/core/test_dag_schema_propagation.py

**Lines:** 476
**Test count:** 12 test methods across 6 test classes
**Audit status:** PASS

## Summary

This test file validates that computed `_output_schema_config` attributes from transform plugins are correctly propagated through `from_plugin_instances()` to NodeInfo, and that `_get_schema_config_from_node()` correctly prioritizes these computed configs over raw config dict parsing. The tests address a specific P1-2026-01-31 bug fix where gate nodes were short-circuiting on raw schema guarantees instead of walking upstream to find computed guarantees.

## Findings

### 🔵 Info

1. **Lines 22-63 (Mock classes):** Well-designed mock classes that simulate real transform behavior. `MockTransformWithSchemaConfig` has a computed `_output_schema_config` while `MockTransformWithoutSchemaConfig` only has raw config dict schema. The mocks have appropriate attributes (`name`, `input_schema`, `output_schema`, `config`).

2. **Lines 65-113 (TestOutputSchemaConfigPropagation):** Tests the core propagation mechanism. Verifies that:
   - Transforms with `_output_schema_config` have it stored in NodeInfo (lines 68-91)
   - Transforms without the attribute have `None` in NodeInfo (lines 93-113)
   This uses `from_plugin_instances()` which is the production path.

3. **Lines 116-187 (TestGetSchemaConfigFromNodePriority):** Tests the priority logic directly on ExecutionGraph with `add_node()`. Verifies:
   - `output_schema_config` parameter takes precedence over config dict (lines 119-147)
   - Falls back to config dict when no `output_schema_config` (lines 149-168)
   - Returns None when neither source has schema (lines 170-187)

4. **Lines 190-302 (TestGuaranteedFieldsWithSchemaConfig):** Tests the integration between `_get_guaranteed_fields()` and contract validation:
   - Guaranteed fields are extracted correctly (lines 193-220)
   - Audit fields are NOT included in guaranteed fields (lines 219-220) - important distinction
   - Contract validation uses computed schema (lines 222-261)
   - Dependency on audit-only fields is rejected (lines 263-302)

5. **Lines 305-358 (TestAggregationSchemaConfigPropagation):** Tests that aggregation transforms also have their `_output_schema_config` propagated. Uses real `AggregationSettings` and `TriggerConfig` from production code.

6. **Lines 360-475 (TestGateSchemaConfigInheritance):** Tests for P1-2026-01-31 bug fix. Validates that:
   - Gates inherit computed guarantees from upstream transforms (lines 367-425)
   - Chained gates all inherit from original transform (lines 427-475)
   The docstrings clearly explain the bug scenario and expected behavior.

### 🟡 Warning

1. **Lines 22-63 (Mock classes use type: ignore):** The mock classes are minimal and rely on `type: ignore[arg-type]` when passed to `from_plugin_instances()`. While this works, the mocks could be made more protocol-compliant to avoid type ignores. However, this is a minor issue since the tests are testing NodeInfo propagation, not full plugin behavior.

2. **Lines 349 (node_type string comparison):** The test at line 349 uses `n.node_type == "aggregation"` which compares NodeType enum to string. This works because NodeType values are strings, but it's slightly fragile if the enum representation changes. Consider using `NodeType.AGGREGATION` for robustness.

### Notes on Coverage

The test file addresses a specific architectural concern: ensuring computed schema information from plugins (which may add fields dynamically) flows correctly through the DAG system. This is important for:
- LLM transforms that add `response_usage`, `response_model` fields
- Batch transforms that add audit fields
- Any transform that computes its output schema at instantiation time

The P1-2026-01-31 references indicate this addresses a real production bug.

## Verdict

**KEEP** - This is a focused, well-structured test file addressing a specific and important feature: computed schema config propagation. The tests cover both the happy path and edge cases (no schema, fallback to config dict, audit fields exclusion). The gate inheritance tests are particularly valuable as they document and prevent regression of a real bug.
