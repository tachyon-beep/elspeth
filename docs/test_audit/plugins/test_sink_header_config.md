# Audit: tests/plugins/test_sink_header_config.py

## Summary
Tests for sink header mode configuration parsing. Focused, well-structured tests covering all header modes and precedence rules.

## Findings

### 1. Strong Tests - Complete Mode Coverage

**Location:** Lines 12-133

**Issue:** None - positive finding.

**Quality:** Tests cover all header modes:
- NORMALIZED (default)
- ORIGINAL
- CUSTOM (dict mapping)

And all configuration paths:
- `headers: normalized/original/{mapping}`
- `restore_source_headers: true`
- `display_headers: {mapping}`

### 2. Strong Tests - Precedence Rules

**Location:** Lines 85-109, 166-207

**Issue:** None - positive finding.

**Quality:** Tests verify that `headers` takes precedence over legacy options. Critical for backwards compatibility.

### 3. Weak Exception Type Assertion

**Location:** Lines 139-151, 180-192

**Issue:** Tests catch generic `Exception`:
```python
with pytest.raises(Exception) as exc_info:
    SinkPathConfig.from_dict(...)
assert "invalid" in str(exc_info.value).lower()
```

Should catch specific exception type (ValueError or ValidationError).

**Severity:** Low - tests work but could hide exception type changes.

### 4. Missing Test - Headers Mode Serialization

**Location:** N/A

**Issue:** Tests verify parsing FROM config but not serialization TO config. If SinkPathConfig needs to round-trip, this is a gap.

**Severity:** Low - may not be needed.

### 5. Missing Test - Schema Interaction

**Location:** N/A

**Issue:** All tests include `"schema": {"mode": "observed"}` but don't test interaction between schema mode and headers mode.

**Severity:** Low - likely orthogonal concerns.

## Missing Coverage

1. **Invalid header mapping types** - what if mapping value is int instead of str?
2. **Header mode with different sink types** - CSV vs JSON vs database
3. **Runtime application** - tests parse config but don't verify headers are applied correctly to output
4. **Unicode header names** - special characters in header mappings

## Structural Issues

### Good Organization
Two focused test classes:
- TestSinkHeaderConfig - happy path parsing
- TestSinkHeaderConfigValidation - edge cases and errors

## Verdict

**Overall Quality:** Good

Focused, complete coverage of configuration parsing. Main gaps:
- No runtime verification that headers actually appear in output
- Generic exception catching

## Recommendations

1. **Use specific exception types** in pytest.raises() calls
2. **Add integration test** verifying headers appear correctly in sink output
3. Consider **parameterized tests** for the repetitive parsing tests
4. **Add invalid mapping type test** - ensure bad config values are rejected
