# Test Audit: test_base.py

**File:** `tests/plugins/llm/test_base.py`
**Lines:** 666
**Auditor:** Claude
**Date:** 2026-02-05

## Summary

This file tests `BaseLLMTransform` and `LLMConfig`, the base classes for all LLM transforms. Tests cover config validation, transform lifecycle, error handling, and schema behavior.

## Findings

### 1. GOOD: Comprehensive Config Validation Tests

**Positive:** Lines 74-272 thoroughly test config validation including:
- Required fields (template, model, schema)
- Template syntax validation
- Temperature bounds (0.0-2.0)
- max_tokens positive constraint
- Lookup fields for template source metadata

### 2. GOOD: Test Factory Pattern

**Positive:** `create_test_transform_class()` (lines 39-71) creates concrete subclasses for testing abstract `BaseLLMTransform`. This is the correct approach for testing abstract classes.

### 3. STRUCTURAL: Heavy Use of `required_input_fields: []` Opt-out

**Severity:** Low
**Issue:** Nearly every test config includes `"required_input_fields": []` to opt-out of field validation.
**Impact:** Tests may not reflect real-world usage where fields are declared.
**Recommendation:** Add dedicated tests for required_input_fields validation. Consider a fixture that provides common test configs.

### 4. OVERMOCKING: Mock Client Stored on Context

**Severity:** Medium
**Issue:** Lines 64-69 store the mock client on `ctx._test_llm_client`, a dynamically-added attribute.
**Impact:** Tests rely on implementation detail of the test helper, not production code behavior.
**Mitigation:** This is contained to the test helper and clearly documented. Acceptable for testing.

### 5. GOOD: Error Propagation Tests

**Positive:** Tests clearly distinguish between:
- Non-retryable errors returning `TransformResult.error()` (line 389)
- Retryable errors (RateLimitError) propagating as exceptions (lines 411-434)
- Generic retryable LLMClientError propagating (lines 581-606)

This correctly tests the engine retry contract.

### 6. INCOMPLETE: No Test for Successful Response Parsing Edge Cases

**Severity:** Medium
**Issue:** `test_successful_transform_returns_enriched_row` only tests happy path with valid response.
**Impact:** Missing coverage for:
- Empty string response
- Very long response
- Response with special characters
**Recommendation:** Add parametrized tests for edge cases.

### 7. POTENTIAL DEFECT: Schema Coercion Test May Be Incorrect

**Severity:** Low
**Issue:** `test_schema_created_with_no_coercion` (lines 628-643) tests that the *input* schema rejects string-for-int, but the test name suggests testing output schema behavior.
**Impact:** Test may be testing the wrong thing, or name is misleading.
**Recommendation:** Clarify whether this tests input or output schema behavior.

### 8. GOOD: Dynamic Schema Coverage

**Positive:** `test_dynamic_schema_accepts_any_fields` (lines 645-666) verifies that observed schema mode allows arbitrary fields, critical for LLM transforms that add dynamic fields.

## Missing Coverage

1. **Batch transform behavior** - BaseLLMTransform batch processing not tested here
2. **Concurrent processing** - No tests for thread safety or concurrent calls
3. **Template variable escaping** - No tests for special characters in template variables
4. **Large row data** - No tests for memory behavior with large input rows
5. **Unicode handling** - No tests for non-ASCII content in templates/responses

## Structural Issues

1. **File length** - 666 lines is manageable but could be split by concern (config vs processing)
2. **Repeated test patterns** - Many tests follow "create transform, call method, assert result" pattern that could be extracted

## Overall Assessment

**Rating:** Good
**Verdict:** Solid foundational tests for the base LLM transform class. Config validation is thorough. Error handling tests correctly verify the retry contract. Main gaps are edge case testing and batch processing coverage.
