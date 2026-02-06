# Test Audit: test_contract_aware_template.py

**File:** `tests/plugins/llm/test_contract_aware_template.py`
**Lines:** 185
**Auditor:** Claude
**Date:** 2026-02-05

## Summary

This file tests Jinja2 template rendering with contract-aware PipelineRow access. Tests verify that templates can access row data using both normalized names (dot access) and original names (bracket access), enabling backwards-compatible templates when source field names change.

## Findings

### 1. GOOD: Comprehensive Access Pattern Tests

**Positive:** Tests cover all access patterns:
- Normalized dot access: `row.amount_usd` (line 51)
- Normalized bracket access: `row["amount_usd"]` (line 65)
- Original bracket access: `row["'Amount USD'"]` (line 79)
- Mixed access styles (line 93)

### 2. GOOD: Jinja2 Feature Tests

**Positive:** Tests verify PipelineRow works with Jinja2 features:
- Conditionals: `{% if row["'Amount USD'"] > 50 %}` (line 107)
- Iteration: `{% for k in row %}` (line 121)
- `in` operator: `'amount_usd' in row` (line 139)
- Filters: `{{ row['Customer Name'] | upper }}` (line 181)
- `get()` with default (line 167)

### 3. GOOD: StrictUndefined Error Test

**Positive:** `test_undefined_field_raises` (line 146) verifies that accessing undefined fields raises `UndefinedError`, which is the expected secure behavior.

### 4. STRUCTURAL: Tests Are Actually Testing PipelineRow, Not Templates

**Severity:** Info
**Issue:** The file is named `test_contract_aware_template.py` but it's really testing PipelineRow's Jinja2 compatibility, not template processing.
**Impact:** Minor naming confusion.
**Recommendation:** Consider renaming to `test_pipeline_row_jinja2.py` or `test_contract_template_access.py`.

### 5. MISSING: LLM Transform Integration

**Severity:** Medium
**Issue:** Tests verify PipelineRow works with raw Jinja2, but don't test actual LLM transform template rendering.
**Impact:** Possible gap if LLM transforms use different template configuration (different Environment, filters, etc.).
**Recommendation:** Add tests that verify contract access through actual transform template rendering.

### 6. GOOD: Contract Field Configuration

**Positive:** The fixture at lines 22-32 creates a realistic contract with:
- Quoted original name: `"'Amount USD'"`
- Space in original name: `"Customer Name"`
- Hyphenated original name: `"ORDER-ID"`

These represent real-world messy source data.

### 7. INCOMPLETE: No Nested Data Tests

**Severity:** Low
**Issue:** All test data is flat. No tests for nested dicts or lists.
**Impact:** Unknown behavior for `row.nested.field` or `row.items[0]`.
**Recommendation:** Add tests for nested data access patterns.

## Missing Coverage

1. **LLM transform template rendering** - Tests raw Jinja2, not actual transform
2. **Nested data access** - No `row.nested.field` patterns
3. **Special characters in values** - No tests for values containing `{{ }}` or other Jinja2 syntax
4. **None values** - No tests for handling None in contract fields
5. **Template compilation caching** - No performance tests

## Structural Issues

1. **File naming** - Name suggests template testing but tests PipelineRow
2. **Single test class** - All tests in `TestJinja2Integration`, could be split by concern

## Overall Assessment

**Rating:** Good
**Verdict:** Tests thoroughly verify that PipelineRow is compatible with Jinja2's sandboxed environment and supports both normalized and original field name access. This is critical for template-based LLM transforms. The main gap is testing the integration with actual LLM transform template rendering rather than raw Jinja2.
