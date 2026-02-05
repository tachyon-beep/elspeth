# Test Audit: tests/integration/test_schema_validation_regression.py

**Auditor:** Claude
**Date:** 2026-02-05
**Batch:** 105-106

## Overview

This file contains regression tests proving the P0-2026-01-24 schema validation bug is fixed. Tests explicitly verify that schema validation now works when it was previously non-functional.

**Lines:** 150
**Test Functions:** 3
- `test_schema_validation_actually_works` - Canonical regression test
- `test_compatible_schemas_still_pass` - Verifies fix doesn't over-restrict
- `test_from_plugin_instances_exists` - API existence check

---

## Summary

| Category | Issues Found |
|----------|--------------|
| Defects | 0 |
| Test Path Integrity Violations | 0 |
| Overmocking | 0 |
| Missing Coverage | 0 |
| Tests That Do Nothing | 1 (MINOR) |
| Structural Issues | 0 |
| Inefficiency | 1 (MINOR) |

---

## Issues

### 1. [MINOR] API Existence Test Has Limited Value

**Location:** `test_from_plugin_instances_exists` (lines 138-150)

**Problem:** This test only verifies that `from_plugin_instances` exists and is callable:

```python
def test_from_plugin_instances_exists() -> None:
    """REGRESSION TEST: Verify new from_plugin_instances() API exists."""
    from elspeth.core.dag import ExecutionGraph

    assert hasattr(ExecutionGraph, "from_plugin_instances")
    assert callable(ExecutionGraph.from_plugin_instances)
```

**Assessment:** This test has limited value because:
1. If `from_plugin_instances` is deleted, other tests would fail more descriptively
2. The test doesn't verify the method works correctly
3. The comment mentions "from_config() will be deleted in Plan 4 Task 11 cleanup" - if that's done, this test becomes vestigial

**Recommendation:** Consider removing this test or replacing it with a test that verifies the method's signature or behavior. The other schema validation tests already implicitly verify this API exists and works.

---

### 2. [MINOR] Redundant Temp File Pattern

**Location:** Tests use manual try/finally cleanup (lines 61-78, 123-135)

**Problem:** Same pattern as `test_schema_validation_end_to_end.py` - could use `tmp_path` fixture.

---

## Strengths

### Canonical Regression Test

`test_schema_validation_actually_works` is well-designed as a regression test:

```python
def test_schema_validation_actually_works() -> None:
    """REGRESSION TEST: Prove schema validation detects incompatibilities.

    Before fix: Validation passed even with incompatible schemas
    After fix: Validation fails correctly

    This is the canonical test proving P0-2026-01-24 is resolved.
    """
```

The test:
1. Clearly documents the before/after behavior
2. Uses a specific incompatible configuration that would have passed before
3. Asserts both exit code and error content

### Complementary Positive Test

`test_compatible_schemas_still_pass` ensures the fix doesn't break valid configurations:

```python
def test_compatible_schemas_still_pass() -> None:
    """REGRESSION TEST: Ensure compatible pipelines still work.

    Verify fix doesn't over-restrict - compatible schemas should still pass.
    """
```

This is important - regression test suites should verify both:
1. The bug is fixed (negative case)
2. Valid behavior still works (positive case)

### Uses CLI End-to-End

Tests invoke the CLI directly via `CliRunner`, testing the full validation path:

```python
runner = CliRunner()
result = runner.invoke(app, ["validate", "--settings", str(config_file)])
assert result.exit_code != 0
assert "field_c" in result.output.lower()
```

### Clear Error Assertions

The regression test verifies specific error content:

```python
# CRITICAL ASSERTION: Must fail validation
assert result.exit_code != 0, "Validation should detect incompatibility"

# CRITICAL ASSERTION: Must mention the missing field
assert "field_c" in result.output.lower(), "Error should mention missing field"

# OPTIONAL: Could also check for "schema" keyword
assert "schema" in result.output.lower() or "missing" in result.output.lower()
```

---

## Verdict

**PASSES AUDIT** - This is a well-designed regression test file. The canonical regression test is properly structured to verify the P0-2026-01-24 fix, and the complementary positive test ensures valid configurations still work. The API existence test is of limited value but not harmful.
