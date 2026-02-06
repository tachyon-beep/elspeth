# Test Audit: tests/property/core/test_templates_properties.py

## Overview
Property-based tests for Jinja2 template field extraction.

**File:** `tests/property/core/test_templates_properties.py`
**Lines:** 410
**Test Classes:** 8

## Findings

### PASS - Comprehensive Template Parsing Coverage

**Strengths:**
1. **Attribute access (row.field) tested** - Single, multiple, duplicates
2. **Item access (row["field"]) tested** - Including fields with dashes
3. **Namespace filtering tested** - Custom namespaces, other namespaces ignored
4. **Return type verified** - Always frozenset (immutable)
5. **Control structures tested** - if/else/for blocks traverse correctly
6. **Dynamic keys correctly ignored** - row[variable] not extracted

### Minor Issues

**1. Low Priority - Redundant assume() in mixed access test (Lines 131-143)**
```python
@given(field1=bracket_field_names, field2=bracket_field_names)
def test_mixed_access_styles_both_extracted(self, field1: str, field2: str) -> None:
    assume(field1 != field2)
    assume(field1.isidentifier())  # For dot notation
```
- The second assume is necessary because bracket_field_names allows non-identifiers
- Correct usage

**2. Observation - with_details consistency tests (Lines 340-387)**
```python
def test_details_keys_match_simple_extraction(self, field: str) -> None:
    simple = extract_jinja2_fields(template)
    details = extract_jinja2_fields_with_details(template)
    assert set(details.keys()) == simple
```
- Tests that both extraction methods return consistent results
- Good for API consistency verification

**3. Good Pattern - Error handling tests (Lines 395-410)**
```python
def test_malformed_template_raises(self) -> None:
    from jinja2 import TemplateSyntaxError
    with pytest.raises(TemplateSyntaxError):
        extract_jinja2_fields("{{ row.field")  # Unclosed
```
- Verifies proper error propagation for invalid templates

### Coverage Assessment

| Extraction Type | Tested | Notes |
|-----------------|--------|-------|
| Single attribute (row.field) | YES | |
| Multiple attributes | YES | |
| Duplicate attributes | YES | Deduplicated |
| Single item (row["field"]) | YES | |
| Fields with dashes | YES | |
| Mixed dot and bracket | YES | |
| Custom namespace | YES | |
| Different namespace ignored | YES | |
| Return type frozenset | YES | |
| Empty template | YES | Empty frozenset |
| No namespace access | YES | Empty frozenset |
| Frozenset immutable | YES | |
| If block fields | YES | |
| If-else all branches | YES | |
| For loop fields | YES | |
| Dynamic keys ignored | YES | row[variable] |
| Idempotent extraction | YES | |
| Order independence | YES | |
| with_details consistency | YES | |
| Attr access labeled 'attr' | YES | |
| Item access labeled 'item' | YES | |
| Mixed access records both | YES | |
| Malformed template error | YES | |
| Unclosed block error | YES | |

## Verdict: PASS

Comprehensive template extraction testing with good coverage of Jinja2 AST traversal edge cases. The dynamic key exclusion test is particularly important for documenting this intentional limitation.
