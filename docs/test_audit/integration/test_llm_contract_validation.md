# Test Audit: test_llm_contract_validation.py

**File:** `/home/john/elspeth-rapid/tests/integration/test_llm_contract_validation.py`
**Lines:** 349
**Batch:** 100-101

## Summary

Integration tests for LLM transform schema contract validation, verifying that template field requirements are caught at DAG construction time before processing begins.

## Audit Findings

### 1. CRITICAL: Test Path Integrity Violation - Manual Graph Construction

**Severity:** High
**Location:** Lines 124-156, 163-199, 204-243, 253-298, 304-349

All tests in `TestDAGContractValidationWithLLMConfig` and `TestMultiTransformChain` use manual graph construction:

```python
graph = ExecutionGraph()

graph.add_node(
    "source_1",
    node_type=NodeType.SOURCE,
    plugin_name="csv",
    config={"schema": {"mode": "observed", "guaranteed_fields": ["id"]}},
)

graph.add_node(
    "llm_1",
    node_type=NodeType.TRANSFORM,
    ...
)

graph.add_edge("source_1", "llm_1", label="continue")
```

Per CLAUDE.md's "Test Path Integrity" section, this is a violation:
- Manual `graph.add_node()` bypasses `ExecutionGraph.from_plugin_instances()`
- Direct attribute assignment skips production validation logic
- BUG-LINEAGE-01 hid for weeks due to exactly this pattern

**Recommendation:** Tests should use `ExecutionGraph.from_plugin_instances()` with real or properly mocked plugin instances.

### 2. ANALYSIS: Violation Impact Assessment

The manual construction here IS testing `validate_edge_compatibility()`, which is a real method. However:
- It doesn't test how nodes are constructed from plugin instances
- It doesn't verify `from_plugin_instances()` correctly extracts `required_input_fields` from plugin config
- If `from_plugin_instances()` had a bug mapping config to graph nodes, these tests would pass

**Partial Mitigation:** These tests could be considered "algorithm tests" for the validation logic itself, if there are separate integration tests using `from_plugin_instances()`. Verify this coverage exists elsewhere.

### 3. GOOD: LLMConfig Validation Tests

**Location:** `TestLLMContractValidationBasics`, `TestLLMTemplateFieldDeclarationRequired`

These tests properly exercise the production `LLMConfig.from_dict()` method:

```python
config = LLMConfig.from_dict({
    "schema": {"mode": "observed"},
    "model": "gpt-4",
    "template": "Hello {{ row.customer_name }}",
    "required_input_fields": ["customer_name"],
})
```

This is the correct pattern - using production factory methods.

### 4. COVERAGE: Missing Tests

**Severity:** Medium

Missing coverage for:
- Template with deeply nested `row` references: `{{ row.data.nested.field }}`
- Template with array access: `{{ row.items[0] }}`
- Template with filters: `{{ row.name | upper }}`
- Template with complex Jinja2 logic: `{% for item in row.items %}...{% endfor %}`
- Circular field dependencies between transforms
- Fork/join scenarios with different field guarantees on each path

### 5. GOOD: Error Message Verification

Tests properly verify error messages contain helpful information:

```python
error = str(exc_info.value)
assert "customer_name" in error
assert "amount" in error
assert "required_input_fields" in error
```

### 6. STRUCTURAL: Test Class Naming Consistency

**Severity:** Minor

Class names are consistent and discoverable:
- `TestLLMContractValidationBasics`
- `TestLLMTemplateFieldDeclarationRequired`
- `TestDAGContractValidationWithLLMConfig`
- `TestMultiTransformChain`

All properly prefixed with `Test`.

### 7. COVERAGE: No Runtime Validation Tests

**Severity:** Medium

Tests only cover configuration-time validation. Missing:
- Runtime behavior when row is missing a declared required field
- Error messages/handling at processing time
- Quarantine behavior for schema violations

### 8. GOOD: Explicit Opt-Out Test

Test `test_explicit_empty_list_allows_opt_out` documents important behavior:
```python
"required_input_fields": [],  # Explicit: "I accept runtime risk"
```

This ensures the escape hatch works as designed.

## Test Path Integrity

**Status:** VIOLATION

The DAG validation tests use manual `graph.add_node()` and `graph.add_edge()` instead of `ExecutionGraph.from_plugin_instances()`. While these test the validation algorithm itself, they don't exercise the production graph construction path.

Per CLAUDE.md:
> Manual `graph.add_node()` / `graph._field = value` bypasses validation

**Exception Consideration:** These tests could be acceptable as "algorithm unit tests" IF:
1. There are separate integration tests using `from_plugin_instances()`
2. Those tests cover the same contract validation scenarios

## Recommendations

1. **High Priority:** Add companion integration tests using `ExecutionGraph.from_plugin_instances()` with real plugin instances to verify end-to-end contract validation
2. **Medium Priority:** Add tests for complex template patterns (nested access, filters, loops)
3. **Medium Priority:** Add runtime validation tests (what happens when row is missing required field?)
4. **Low Priority:** Consider renaming current tests to clarify they're testing the algorithm, not the integration
5. **Documentation:** If keeping manual construction tests, add docstring explaining why (algorithm-level testing) and reference to companion integration tests
