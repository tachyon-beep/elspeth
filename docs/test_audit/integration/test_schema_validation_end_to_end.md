# Test Audit: tests/integration/test_schema_validation_end_to_end.py

**Auditor:** Claude
**Date:** 2026-02-05
**Batch:** 105-106

## Overview

This file contains end-to-end integration tests for schema validation using the CLI `validate` command. Tests verify that schema compatibility is properly validated at DAG construction time.

**Lines:** 403
**Test Functions:** 7 (module-level functions and one function using `plugin_manager` fixture)

---

## Summary

| Category | Issues Found |
|----------|--------------|
| Defects | 0 |
| Test Path Integrity Violations | 0 |
| Overmocking | 0 |
| Missing Coverage | 0 |
| Tests That Do Nothing | 0 |
| Structural Issues | 1 (MINOR) |
| Inefficiency | 1 (MINOR) |

---

## Issues

### 1. [MINOR] Redundant Temporary File Cleanup Pattern

**Location:** All CLI-based tests (lines 58-68, 111-121, etc.)

**Problem:** Tests use manual try/finally for temp file cleanup:

```python
with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
    f.write(config_yaml)
    config_file = Path(f.name)

try:
    result = runner.invoke(app, ["validate", "--settings", str(config_file)])
    # assertions...
finally:
    config_file.unlink()
```

**Recommendation:** Use `tmp_path` pytest fixture or `delete=True` with context manager for cleaner code:

```python
def test_compatible_pipeline_passes_validation(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(config_yaml)
    result = runner.invoke(app, ["validate", "--settings", str(config_file)])
    # assertions - no cleanup needed
```

---

### 2. [MINOR] Copy-Paste Pattern in Config YAML

**Problem:** Multiple tests have similar YAML configurations with minor variations. This is acceptable for readability but could be DRY-er.

**Assessment:** The repetition is acceptable because:
1. Each test documents its specific scenario inline
2. Config differences are clear and intentional
3. Shared fixtures might obscure what each test is testing

---

## Strengths

### Excellent Test Organization

1. **Two-Phase Validation Testing:** `test_two_phase_validation_separates_self_and_compatibility_errors` clearly demonstrates Phase 1 (self-validation) vs Phase 2 (compatibility) validation
2. **Uses Production CLI:** Tests invoke `elspeth validate` command through `CliRunner`
3. **Uses Production Graph Construction:** `test_two_phase_validation...` uses `ExecutionGraph.from_plugin_instances()` (correct path)

### Clear Test Scenarios

Each test clearly documents what it validates:

- `test_compatible_pipeline_passes_validation` - Compatible schemas pass
- `test_transform_chain_incompatibility_detected` - Incompatible transform chain fails
- `test_aggregation_output_incompatibility_detected` - Dynamic schema validation is skipped (correctly)
- `test_dynamic_schemas_skip_validation` - Dynamic schemas don't cause errors
- `test_aggregation_incoming_edge_uses_input_schema` - Aggregation input validation works
- `test_aggregation_outgoing_edge_uses_output_schema` - Dynamic output schema validation skipped

### Proper Two-Phase Testing

`test_two_phase_validation_separates_self_and_compatibility_errors` (lines 340-403) is particularly well-designed:

```python
# PHASE 1 should fail: Malformed schema in plugin config
bad_self_config = {
    "path": "test.csv",
    "schema": {"mode": "fixed", "fields": ["invalid syntax!!!"]},
    # ...
}

with pytest.raises(PluginConfigError, match="Invalid field spec"):
    # Fails during plugin construction (PHASE 1)
    source_cls = plugin_manager.get_source_by_name("csv")
    source_cls(bad_self_config)

# PHASE 2 should fail: Well-formed schemas, incompatible connection
# ... uses ExecutionGraph.from_plugin_instances() correctly
with pytest.raises(ValueError, match=r"Missing fields.*email"):
    ExecutionGraph.from_plugin_instances(...)
```

### Correct Use of Production Paths

The test at line 396 uses `ExecutionGraph.from_plugin_instances()` which is the correct production path:

```python
with pytest.raises(ValueError, match=r"Missing fields.*email"):
    ExecutionGraph.from_plugin_instances(
        source=plugins["source"],
        transforms=plugins["transforms"],
        sinks=plugins["sinks"],
        aggregations=plugins["aggregations"],
        gates=list(config.gates),
        default_sink=config.default_sink,
    )
```

---

## Verdict

**PASSES AUDIT** - This is a well-designed test file. It tests schema validation end-to-end using the production CLI and graph construction APIs. The tests clearly document what scenarios they cover, and the two-phase validation test is particularly thorough.
