# Audit: tests/plugins/test_validation.py

## Summary
Tests for `PluginConfigValidator` class. Comprehensive coverage of validation for all plugin types (sources, transforms, sinks, gates).

## Findings

### 1. Strong Tests - Plugin Type Coverage

**Location:** Entire file

**Issue:** None - positive finding.

**Quality:** Tests cover all plugin types:
- Sources (csv, json, null, azure_blob)
- Transforms (passthrough, field_mapper)
- Sinks (csv, database, azure_blob)
- Gates (threshold - expected to fail)

### 2. Strong Tests - Schema Validation

**Location:** Lines 240-329

**Issue:** None - positive finding.

**Quality:** Schema validation tests cover:
- Valid modes (observed, fixed, flexible)
- Invalid mode rejection
- Missing fields rejection
- Empty fields rejection
- Invalid field type rejection
- Malformed field spec rejection

### 3. Tests Use Free Functions

**Location:** Lines 8-190

**Issue:** Tests are written as module-level functions, not in test classes:
```python
def test_validator_accepts_valid_source_config():
```

This is valid pytest, but inconsistent with other test files that use classes.

**Severity:** Low - style inconsistency, no functional impact.

### 4. Magic Strings for Plugin Names

**Location:** Throughout file

**Issue:** Plugin names are hardcoded strings:
```python
validator.validate_source_config("csv", config)
validator.validate_transform_config("passthrough", config)
```

If plugin names change, tests break without clear indication why.

**Severity:** Low - plugin names are stable, but could use constants.

### 5. Test Gate Behavior Assumption

**Location:** Lines 102-116

**Issue:** Test assumes gate validation will raise because "no gate plugins exist yet":
```python
# No gate plugins exist in codebase yet, so this should raise
with pytest.raises(ValueError) as exc_info:
    validator.validate_gate_config("threshold", config)
```

If gates are added, this test will start failing.

**Severity:** Medium - test documents temporary state, not permanent behavior.

### 6. Inconsistent Error Assertions

**Location:** Lines 33-35 vs 144-146

**Issue:** Some tests check specific error fields:
```python
assert "path" in errors[0].field
assert "required" in errors[0].message.lower()
```

Others just check error count:
```python
assert len(errors) == 1
```

**Severity:** Low - inconsistent precision.

### 7. Missing Test - Multiple Validation Errors

**Location:** N/A

**Issue:** Tests only verify single errors. No test for config with multiple problems (e.g., wrong type AND missing field).

**Severity:** Medium - real configs may have multiple issues.

## Missing Coverage

1. **Multiple simultaneous validation errors** - config with several problems
2. **Nested config validation** - deeply nested options
3. **Cross-field validation** - fields that depend on each other
4. **Custom validators** - if plugins define custom validation
5. **Error message formatting** - verify errors are human-readable

## Structural Issues

### Inconsistent Test Structure
Mix of free functions and no test classes. Consider organizing into classes:
- TestSourceValidation
- TestTransformValidation
- TestSinkValidation
- TestSchemaValidation

## Verdict

**Overall Quality:** Good

Comprehensive validation coverage with good negative testing. Main issues:
- Gate test documents temporary state
- Inconsistent assertion patterns
- No multiple-error testing

## Recommendations

1. **Update gate test** when gate plugins are added
2. **Add multiple-error test** - verify all problems are reported
3. **Organize into test classes** for consistency with other test files
4. **Standardize assertion patterns** - always check field and message
5. **Consider test parameterization** for repetitive plugin type tests
