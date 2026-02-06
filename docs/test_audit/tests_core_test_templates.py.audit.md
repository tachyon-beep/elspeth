# Test Audit: tests/core/test_templates.py

**Lines:** 199
**Test count:** 23
**Audit status:** PASS

## Summary

This test file comprehensively validates the Jinja2 template field extraction utilities (`extract_jinja2_fields` and `extract_jinja2_fields_with_details`). Tests cover diverse template patterns including dot notation, bracket notation, conditionals, loops, filters, namespaces, nested access, and invalid syntax. The tests are thorough and well-documented.

## Findings

### Info

- **Lines 10-134** (`TestExtractJinja2Fields`, 19 tests): Comprehensive coverage of the basic extraction function:
  - Simple and complex field access patterns (dot, bracket, mixed)
  - Namespace handling (default `row`, custom namespaces, mixed namespaces)
  - Control flow extraction (conditionals extract all branches, loops)
  - Filter handling (filters don't affect extraction)
  - Edge cases (empty template, no references, duplicates, nested access)
  - Error handling (invalid syntax raises `TemplateSyntaxError`)
- **Lines 145-167**: Complex template test is an excellent integration-style test combining multiple patterns.
- **Lines 169-199** (`TestExtractJinja2FieldsWithDetails`, 4 tests): Tests the detailed extraction function that records access type (`attr` vs `item`). Good coverage of access type tracking and multiple accesses.
- **Import pattern**: All tests import inside methods. This is unconventional but harmless.

## Verdict

**KEEP** - Excellent test file with thorough coverage of template field extraction. The tests document expected behavior for various Jinja2 patterns and edge cases. Well-structured with two focused test classes.
