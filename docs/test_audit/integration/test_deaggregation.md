# Test Audit: test_deaggregation.py

**File:** `tests/integration/test_deaggregation.py`
**Lines:** 411
**Batch:** 99

## Summary

This file tests the deaggregation (JSONExplode) pipeline end-to-end, including audit trail verification for token expansion.

## Audit Results

### 1. Defects

| Issue | Severity | Location |
|-------|----------|----------|
| Duplicate plugin instantiation | Medium | Lines 231-243 |

The `run_pipeline` fixture creates plugins twice:
1. First via `instantiate_plugins_from_config(settings)` (line 230)
2. Then again manually (lines 241-243):
```python
source = JSONSource(dict(settings.source.options))
transform = JSONExplode(dict(settings.transforms[0].options))
sink = JSONSink(dict(settings.sinks["output"].options))
```

This creates a mismatch - the graph is built with one set of plugin instances, but `PipelineConfig` receives different instances. This could lead to subtle bugs.

| Issue | Severity | Location |
|-------|----------|----------|
| Unused TYPE_CHECKING import | Low | Line 411 |

The `if __name__ == "__main__":` block imports `LandscapeDB` but only for type annotation that's already handled by the TYPE_CHECKING import pattern elsewhere.

### 2. Overmocking

**NONE** - Tests use real plugins and real database.

### 3. Missing Coverage

| Gap | Severity | Description |
|-----|----------|-------------|
| Empty array handling | Medium | No test for order with `"items": []` |
| Null array handling | Medium | No test for order with `"items": null` |
| Non-array items field | Medium | No test for order with items as non-array value |
| Single-item expansion | Low | No test for expansion of single-element arrays |

### 4. Tests That Do Nothing

**NONE** - All tests verify meaningful outcomes.

### 5. Inefficiency

| Issue | Severity | Location |
|-------|----------|----------|
| Duplicate input_data fixture | Medium | Lines 25-44 and 142-161 |

Two identical `input_data` fixtures are defined in different test classes. Should be module-level or conftest.

| Issue | Severity | Location |
|-------|----------|----------|
| test_preserves_item_order unused fixture | Low | Line 112 |

`plugin_manager` fixture is requested but not used in the test.

### 6. Structural Issues

| Issue | Severity | Location |
|-------|----------|----------|
| Type annotation workaround | Low | Lines 409-411 |

The `if __name__ == "__main__":` block is a workaround for type annotations. Should use `TYPE_CHECKING` block instead (which is already imported).

### 7. Test Path Integrity

**MOSTLY COMPLIANT** - The `run_pipeline` fixture uses `ExecutionGraph.from_plugin_instances()`:
```python
graph = ExecutionGraph.from_plugin_instances(
    source=plugins["source"],
    transforms=plugins["transforms"],
    sinks=plugins["sinks"],
    ...
)
```

However, the subsequent manual plugin instantiation (lines 241-243) creates a discrepancy between graph construction and pipeline execution.

## Verdict: NEEDS IMPROVEMENT

The tests verify the correct behavior but have a significant bug where plugins are instantiated twice with different instances. The duplicate fixture definitions also indicate copy-paste code.

## Recommendations

1. **CRITICAL**: Fix the duplicate plugin instantiation in `run_pipeline` - use the same plugin instances for both graph construction and PipelineConfig
2. Consolidate duplicate `input_data` fixtures to module level or conftest
3. Remove unused `plugin_manager` fixture parameter from `test_preserves_item_order`
4. Add tests for edge cases: empty arrays, null arrays, non-array values
5. Fix the type annotation workaround at end of file
