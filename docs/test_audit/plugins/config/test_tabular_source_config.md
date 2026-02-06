# Test Audit: test_tabular_source_config.py

**File:** `tests/plugins/config/test_tabular_source_config.py`
**Lines:** 173
**Batch:** 119

## Summary

This test file validates the `TabularSourceDataConfig` configuration class, which handles validation for tabular data source options like field normalization, column specifications, and field mappings.

## Test Classes

| Class | Test Count | Purpose |
|-------|------------|---------|
| `TestTabularSourceDataConfigValidation` | 12 | Field normalization config validation |

## Findings

### 1. POSITIVE: Good Error Case Coverage

The tests thoroughly cover validation error cases:
- `normalize_fields=True` with `columns` (incompatible)
- `field_mapping` without enabling feature
- Python keywords in column names
- Invalid identifiers in columns
- Duplicate column names
- Python keywords in field mapping values

**Verdict:** Well-designed error boundary testing.

### 2. POSITIVE: Clear Test Structure

Each test has:
- Descriptive name matching the scenario
- Single responsibility (one assertion per test)
- Clear docstrings explaining expected behavior

### 3. MINOR: Repeated Import Inside Methods

**Location:** Lines 14, 29, 44, 57, 71, 85, 100, 116, 133, 147, 163
**Issue:** `TabularSourceDataConfig` is imported inside each test method rather than at module level.

```python
def test_normalize_with_columns_raises(self) -> None:
    """normalize_fields=True with columns raises error."""
    from elspeth.plugins.config_base import TabularSourceDataConfig  # Repeated 11 times
```

**Impact:** Minor inefficiency; imports are cached but the pattern is unusual. May be intentional to isolate import failures.

**Severity:** Low (stylistic)

### 4. POTENTIAL GAP: Missing Edge Cases

**Missing tests for:**
- Empty `columns` list (should this be allowed?)
- `field_mapping` with keys that don't exist in data (runtime vs config time validation?)
- Very long column names (potential identifier length limits)
- Unicode characters in column names
- `normalize_fields=False` explicitly with `columns` (should work)

**Severity:** Low - these may be validated elsewhere or be acceptable edge cases.

### 5. MINOR: Test Path Integrity

**Status:** Compliant

These tests directly test the config validation class via `from_dict()`, which is the production code path. No manual construction bypassing production code.

### 6. POSITIVE: Regex Matches for Error Messages

Tests use regex patterns for error message matching:
```python
pytest.raises(PluginConfigError, match=r"valid.*identifier")
pytest.raises(PluginConfigError, match=r"[Dd]uplicate")
```

This is more robust than exact string matching.

## Recommendations

1. **Optional:** Move import to module level for consistency with other test files
2. **Optional:** Add edge case tests for empty columns list and explicit `normalize_fields=False`

## Risk Assessment

| Category | Risk Level |
|----------|------------|
| Defects | None identified |
| Overmocking | None (no mocks used) |
| Missing Coverage | Low - edge cases only |
| Tests That Do Nothing | None |
| Structural Issues | Minor (repeated imports) |

## Verdict

**PASS** - Well-designed config validation tests. Minor stylistic improvements possible but no functional issues.
