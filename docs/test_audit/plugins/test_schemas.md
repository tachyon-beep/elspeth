# Audit: tests/plugins/test_schemas.py

## Summary
Tests for plugin schema validation, compatibility checking, and type system behavior. Well-structured with good bug regression tests, but some outdated comments.

## Findings

### 1. Strong Tests - Bug Regression Coverage

**Location:** Lines 164-239, 318-382

**Issue:** None - positive finding.

**Quality:** Tests explicitly reference bug tickets:
- P1-2026-01-20-schema-compatibility-check-fails-on-optional-and-any
- P2-2026-01-21-strict-extra-fields
- P2-2026-01-31-schema-compatibility-ignores-strictness

This is excellent practice - tests serve as regression guards.

### 2. Strong Tests - Strict Schema Behavior

**Location:** Lines 318-382

**Issue:** None - positive finding.

**Quality:** Tests verify that strict schemas reject int->float coercion while permissive schemas allow it. Critical for Data Manifesto compliance.

### 3. Potential Flaky Assertion

**Location:** Lines 237-239

**Issue:** Test checks error message format:
```python
assert "int | None" in result.error_message or "Optional" not in result.error_message
```

This OR condition is confusing. If error_message contains neither "int | None" nor "Optional", the assertion passes, which seems wrong.

**Severity:** Medium - test may pass incorrectly.

### 4. Missing Edge Cases in Compatibility

**Location:** Lines 89-162

**Issue:** Compatibility tests don't cover:
- Cyclic type references
- Generic types (list[int], dict[str, int])
- Nested schemas
- Self-referential schemas

**Severity:** Medium - real schemas may use these patterns.

### 5. Weak Assertion Pattern

**Location:** Lines 75-76, 84-86

**Issue:** Tests check `len(errors) > 0` but don't verify error content:
```python
errors = validate_row({"x": "not int", "y": 2}, MySchema)
assert len(errors) > 0  # But what's the error?
```

Better to assert specific error field and message.

**Severity:** Low - tests work but could be more precise.

### 6. Test Truncation

**Location:** Line 382 (file appears truncated)

**Issue:** The file ends at line 382 but content appears complete based on the final test. However, there may be additional tests not visible.

**Severity:** Unknown - need to verify complete file was read.

## Missing Coverage

1. **Schema versioning** - compatibility across schema versions
2. **Schema serialization** - round-trip to/from config
3. **Nested schema validation** - objects within objects
4. **Array field validation** - list[int], list[PluginSchema]
5. **Union type complexity** - Union[A, B] where A and B are schemas
6. **Recursive schemas** - self-referential structures

## Structural Issues

### Good Organization
Test classes are well-named and focused:
- TestPluginSchema - basic validation
- TestSchemaValidation - utility functions
- TestSchemaCompatibility - type checking between schemas

## Verdict

**Overall Quality:** Good

Strong regression test coverage with explicit bug ticket references. Main areas for improvement:
- Fix the OR assertion logic
- Add generic/nested type coverage
- Strengthen error content assertions

## Recommendations

1. **Fix line 237-239 assertion** - the OR logic appears incorrect
2. **Add generic type tests** - list[int], dict[str, Any]
3. **Add nested schema tests** - schema containing another schema
4. **Strengthen error assertions** - verify error.field and error.message, not just error count
5. **Keep bug ticket references** - excellent practice for regression tracking
6. **Verify file completeness** - check if there are more tests after line 382
