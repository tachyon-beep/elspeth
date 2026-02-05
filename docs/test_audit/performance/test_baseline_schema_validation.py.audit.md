# Test Audit: tests/performance/test_baseline_schema_validation.py

**Audit Date:** 2026-02-05
**Auditor:** Claude Code
**Test File:** `/home/john/elspeth-rapid/tests/performance/test_baseline_schema_validation.py`
**Lines:** 200

## Summary

Performance baseline tests measuring validation time and plugin instantiation overhead. These tests establish timing baselines to ensure architectural changes don't degrade performance.

## Findings

### 1. POSITIVE: Proper Use of Production Code Paths

**Location:** Lines 118-126, 182-190

**Good Practice:** Tests correctly use `ExecutionGraph.from_plugin_instances()` and `instantiate_plugins_from_config()`:
```python
plugins = instantiate_plugins_from_config(config)
graph = ExecutionGraph.from_plugin_instances(
    source=plugins["source"],
    transforms=plugins["transforms"],
    sinks=plugins["sinks"],
    aggregations=plugins["aggregations"],
    gates=list(config.gates),
    default_sink=config.default_sink,
)
graph.validate()
```

This follows Test Path Integrity principles perfectly.

### 2. MEDIUM: Timing Assertions May Be Fragile on CI/Slow Systems

**Location:** Lines 70, 130, 195

**Issue:** Fixed timing thresholds like `< 100ms` or `< 200ms` may fail intermittently on:
- CI systems with resource contention
- Virtual machines with variable performance
- Systems under heavy load

**Example:**
```python
assert instantiation_time < 0.100, f"Plugin instantiation took {instantiation_time * 1000:.2f}ms (expected < 100ms)"
```

**Recommendation:** Consider:
1. Using `pytest.mark.performance` marker (already present - good!)
2. Adding CI-aware multipliers for timing thresholds
3. Running multiple iterations and using statistical measures (median, p95)
4. Using `pytest-benchmark` for proper performance testing

### 3. LOW: Temp File Cleanup in Finally Block Could Mask Test Failures

**Location:** Lines 57-75, 109-135, 173-200

**Issue:** Each test uses `try/finally` to clean up temp files:
```python
try:
    # ... test code ...
finally:
    config_file.unlink()
```

**Impact:** If `unlink()` fails, it could mask the original assertion error.

**Recommendation:** Use `tempfile.NamedTemporaryFile(delete=True)` or pytest's `tmp_path` fixture which handles cleanup automatically.

### 4. LOW: Print Statements in Tests

**Location:** Lines 72, 132, 197

**Issue:** Tests use `print()` for timing output:
```python
print(f"\nPlugin instantiation: {instantiation_time * 1000:.2f}ms")
```

**Impact:** Output is only visible with `-s` flag. Better to use logging or pytest's reporting.

**Recommendation:** Use `pytest-benchmark` which automatically reports timing, or log with `logging.info()`.

### 5. INFO: No Warm-up Iterations

**Location:** All timing tests

**Issue:** Each test runs only once. First runs often include JIT compilation, module imports, and other one-time costs that inflate measurements.

**Recommendation:** Consider adding warm-up iterations or using `pytest-benchmark` which handles this automatically.

### 6. INFO: Code Duplication Across Tests

**Location:** Lines 22-55, 82-107, 142-171

**Issue:** Similar YAML config is repeated three times with minor variations.

**Recommendation:** Extract common config to a fixture or module-level constant:
```python
def _make_config(transforms_count=1):
    return f"""
    source:
      plugin: csv
      ...
    transforms:
      {transforms_yaml(transforms_count)}
    ...
    """
```

## Test Path Integrity

**Status:** PASS

The tests properly use:
- `instantiate_plugins_from_config()` - production plugin instantiation
- `ExecutionGraph.from_plugin_instances()` - production graph construction
- `graph.validate()` - production validation

No manual graph construction or attribute manipulation.

## Verdict

**PASS**

These are well-structured performance baseline tests that correctly use production code paths. The main concerns are:
1. Timing thresholds may be fragile in CI environments (mitigated by `@pytest.mark.performance` marker)
2. Code duplication could be reduced

The tests serve their purpose of establishing performance baselines for the schema validation refactor.
