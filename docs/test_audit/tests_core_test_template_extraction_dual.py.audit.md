# Test Audit: tests/core/test_template_extraction_dual.py

**Lines:** 97
**Test count:** 7
**Audit status:** PASS

## Summary

This test file validates the `extract_jinja2_fields_with_names` function, which extracts field references from Jinja2 templates and resolves them against a schema contract. The tests are well-organized, cover the key scenarios (known fields, unknown fields, mixed cases, original vs normalized name resolution), and use appropriate fixtures.

## Findings

### Info

- **Lines 13-24**: The fixture creates a realistic `SchemaContract` with field mappings that include original names with special characters (e.g., `'Amount USD'`), which is a good edge case.
- **Lines 26-55**: Tests verify bidirectional resolution - normalized names map to originals and vice versa, with deduplication.
- **Lines 56-76**: Proper handling of unknown fields (returns field as written with `resolved: False`) and the no-contract case are both tested.
- **Lines 77-97**: Edge cases for mixed known/unknown fields and original-name-only templates are covered.

## Verdict

**KEEP** - This is a focused, well-written test file. It tests a single utility function with appropriate coverage of the various input scenarios and edge cases. No issues found.
