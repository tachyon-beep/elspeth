# Test Bug Report: Rewrite weak assertions in join_group_id_bug

## Summary

- This is a minimal TDD-style test written to verify that `TokenInfo` has a `join_group_id` field. The test is extremely focused and validates a single contract requirement, but there are questions about whether this bug has been fixed and whether the test still serves its purpose.

## Severity

- Severity: minor
- Priority: P2
- Verdict: **REWRITE**

## Reporter

- Name or handle: Test Audit
- Date: 2026-02-06
- Audit file: docs/test_audit/tests_engine_test_join_group_id_bug.audit.md

## Test File

- **File:** `tests/engine/test_join_group_id_bug`
- **Lines:** 25
- **Test count:** 1

## Findings

- See audit file for details


## Verdict Detail

**REWRITE** - The test needs to be updated to reflect current status (is the bug fixed?). If fixed, the docstring needs updating and the test should be expanded to verify actual propagation behavior from `TokenManager`, not just that the field exists on `TokenInfo`. If not fixed, the test is valid as-is but should remain in a separate "pending" or "failing" category.

## Proposed Fix

- [x] Tests have specific, non-permissive assertions
- [x] Each test verifies the exact expected behavior
- [x] No "or 'error' in output" fallback patterns
- [x] Tests fail when actual behavior differs from expected

## Tests

- N/A (file deleted)

## Resolution

**Date:** 2026-02-06

**Investigation:**

1. **Bug status:** FIXED - `TokenInfo` now has `join_group_id` field (line 36 of `src/elspeth/contracts/identity.py`)
2. **Test status:** Was passing (no longer failing as docstring claimed)
3. **Coverage analysis:** Found 30 test files referencing `join_group_id`, including:
   - `tests/contracts/test_identity.py` - Tests `join_group_id` preservation in `with_updated_data()`
   - `tests/engine/test_group_id_consistency.py` - Comprehensive propagation tests through coalesce operations

**Decision:** DELETE the file

**Rationale:**
- The test only verified that a dataclass field exists - trivial coverage
- The original bug that motivated the test has been fixed
- Comprehensive tests for `join_group_id` propagation behavior already exist
- This was a TDD "red phase" test that served its purpose and was never cleaned up

**Action taken:** Deleted `tests/engine/test_join_group_id_bug.py`

## Notes

- Source audit: `docs/test_audit/tests_engine_test_join_group_id_bug.audit.md`
