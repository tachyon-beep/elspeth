# Test Audit: test_capacity_errors.py

**File:** `tests/plugins/llm/test_capacity_errors.py`
**Lines:** 58
**Auditor:** Claude
**Date:** 2026-02-05

## Summary

This file tests HTTP status code classification for capacity errors (429, 503, 529) and the `CapacityError` exception class. Tests verify which HTTP codes indicate server capacity issues vs other errors.

## Findings

### 1. GOOD: Clear Classification Tests

**Positive:** Tests at lines 8-41 explicitly verify:
- 429 (Too Many Requests) is capacity
- 503 (Service Unavailable) is capacity
- 529 (Azure overloaded) is capacity
- 500, 400, 401, 200 are NOT capacity

This prevents accidental changes to retry behavior.

### 2. GOOD: Tests Both Function and Constant

**Positive:** Tests verify both `is_capacity_error(code)` function and `CAPACITY_ERROR_CODES` constant, ensuring they stay in sync.

### 3. GOOD: Exception Tests

**Positive:** Tests at lines 44-58 verify:
- CapacityError stores status_code
- CapacityError is always retryable (`retryable=True`)

### 4. INCOMPLETE: Limited Status Code Coverage

**Severity:** Low
**Issue:** Only tests a handful of status codes. Many others exist (502 Bad Gateway, 504 Gateway Timeout, etc.).
**Impact:** Unknown behavior for untested codes.
**Recommendation:** Add tests for:
- 502 Bad Gateway (typically capacity-related)
- 504 Gateway Timeout (typically capacity-related)
- 509 Bandwidth Limit Exceeded

### 5. MISSING: Edge Cases

**Severity:** Low
**Issue:** No tests for:
- `is_capacity_error(None)`
- `is_capacity_error("429")` (string instead of int)
- CapacityError with None status_code
**Impact:** Unknown behavior for malformed inputs.
**Recommendation:** If function should reject non-int, add tests to verify.

### 6. STRUCTURAL: Very Small File

**Severity:** Info
**Issue:** 58 lines is appropriate for the scope. Tests are focused and readable.
**Impact:** Positive - easy to maintain.

## Missing Coverage

1. **Additional HTTP status codes** - 502, 504, 509
2. **Negative codes or zero** - Should they be handled?
3. **CapacityError inheritance** - Is it an LLMClientError subclass?
4. **Integration with retry logic** - No test showing engine uses CapacityError for retry decisions

## Structural Issues

None significant.

## Overall Assessment

**Rating:** Good
**Verdict:** Small, focused test file that correctly verifies capacity error classification. Tests are clear and would catch regressions in retry behavior. Minor improvements could add more status code coverage. The file appropriately tests a simple utility without over-engineering.
