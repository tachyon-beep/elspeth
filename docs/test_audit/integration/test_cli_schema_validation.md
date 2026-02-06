# Test Audit: test_cli_schema_validation.py

**File:** `tests/integration/test_cli_schema_validation.py`
**Lines:** 106
**Batch:** 98

## Summary

This file tests CLI schema validation for incompatible pipeline configurations via both `run` and `validate` commands.

## Audit Results

### 1. Defects

| Issue | Severity | Location |
|-------|----------|----------|
| Assertion is too loose | Medium | Lines 53-54, 102-103 |

The assertions check for either "schema" OR "field_b" in output:
```python
assert "schema" in result.output.lower() or "field_b" in result.output.lower()
```

This is too permissive. If the error message accidentally contains "schema" for an unrelated reason, the test would pass even if the actual schema validation failed. Should check for specific error patterns.

### 2. Overmocking

**NONE** - Tests use real CLI invocation.

### 3. Missing Coverage

| Gap | Severity | Description |
|-----|----------|-------------|
| No positive test case | Medium | Both tests only check failure - no test that valid schema passes |
| No specific error message verification | Medium | Tests don't verify the actual schema incompatibility reason |
| Missing input file | Medium | Config references `test_input.csv` but it's never created - relies on schema validation failing before file access |

### 4. Tests That Do Nothing

**NONE** - Tests do check exit codes and output.

### 5. Inefficiency

| Issue | Severity | Location |
|-------|----------|----------|
| Duplicate config YAML | Medium | Both tests have nearly identical config - could be a fixture |
| Manual temp file cleanup | Low | Could use pytest tmp_path fixture |

### 6. Structural Issues

| Issue | Severity | Location |
|-------|----------|----------|
| Tests are functions not classes | Low | Unlike other files, these are bare functions - inconsistent style |

### 7. Test Path Integrity

**COMPLIANT** - Uses real CLI invocation through Typer test runner.

## Verdict: NEEDS IMPROVEMENT

The tests verify basic functionality but have weak assertions and missing positive test cases.

## Recommendations

1. Add more specific assertion patterns for schema validation errors
2. Add test cases for valid schema configurations
3. Create the input file or explicitly test that missing file is handled after schema validation
4. Extract common config to a fixture
5. Wrap in test class for consistency with other test files
