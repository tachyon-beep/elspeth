# Test Audit: tests/core/landscape/test_helpers.py

**Lines:** 69
**Test count:** 6
**Audit status:** PASS

## Summary

This test file covers the landscape helper functions (`now()`, `generate_id()`, `coerce_enum()`). Tests are minimal but appropriate for the simple utility functions being tested. Each test verifies the core behavior without over-engineering.

## Findings

### 🔵 Info

1. **Lines 21-25**: `test_returns_current_time` uses a timing window assertion (`before <= result <= after`) which is the correct way to test time-related functions without flaky tests.

2. **Lines 47-50**: `test_returns_unique_ids` generates 100 IDs and verifies uniqueness. This is a reasonable sample size for statistical confidence without making the test slow.

3. **Line 66-69**: `test_crashes_on_invalid_string` correctly tests that `coerce_enum` raises `ValueError` on invalid input, consistent with CLAUDE.md Tier 1 trust model (audit data must crash on anomalies).

## Verdict

**KEEP** - This is a concise, focused test file. The coverage is appropriate for simple utility functions. No overmocking, no defects, and the tests are meaningful. The file could potentially be expanded to test more edge cases (e.g., `now()` with mocked time, `generate_id()` format validation), but the current tests are sufficient for the functions' simplicity.
