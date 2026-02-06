# Test Bug Report: Rewrite weak assertions in coalesce_contract_bug

## Summary

- This file documents a known P2 bug where coalesce with `merge="nested"` or `merge="select"` strategies creates data with a structure that doesn't match the merged contract. The active test correctly demonstrates the bug by showing that PipelineRow access fails for both the nested keys and the original field names. However, the test is currently serving as documentation of a known bug rather than regression protection.

## Severity

- Severity: minor
- Priority: P2
- Verdict: **REWRITE**

## Reporter

- Name or handle: Test Audit
- Date: 2026-02-06
- Audit file: docs/test_audit/tests_engine_test_coalesce_contract_bug.audit.md

## Test File

- **File:** `tests/engine/test_coalesce_contract_bug`
- **Lines:** 83
- **Test count:** 1

## Findings

- See audit file for details


## Verdict Detail

**REWRITE** - This test file needs to be restructured to provide proper regression coverage. The current test that "passes when the bug exists" is an anti-pattern that will cause CI failures when the bug is fixed. Recommended changes:

1. Mark the current test with `@pytest.mark.xfail(reason="P2 bug: nested merge contract mismatch", strict=True)` and invert the assertions to show expected behavior
2. Enable the commented integration tests with proper fixtures
3. Add a bug ticket reference for tracking
4. When the bug is fixed, the xfail tests will start passing (strict=True will fail if they unexpectedly pass, alerting the fixer to remove the marker)

## Proposed Fix

- [x] Tests have specific, non-permissive assertions
- [x] Each test verifies the exact expected behavior
- [x] No "or 'error' in output" fallback patterns
- [x] Tests fail when actual behavior differs from expected

## Resolution

**Date:** 2026-02-06

**Actions taken:**

1. **Rewrote** the single test into two focused xfail tests:
   - `test_nested_merge_contract_allows_branch_key_access` - Tests that `row["path_a"]` should work
   - `test_nested_merge_contract_has_correct_field_types` - Tests that contract should have branch key fields

2. **Applied** `@pytest.mark.xfail(strict=True, reason="P2 bug: ...")` pattern:
   - Tests describe EXPECTED correct behavior (assertions for what SHOULD work)
   - Tests currently fail because the bug exists (XFAIL)
   - When bug is fixed, tests will pass, `strict=True` will alert fixer to remove marker

3. **Extracted** helper function `_make_branch_contracts()` to reduce duplication

4. **Removed** commented-out integration tests (were just `pass` stubs)

**Result:** Test file now properly documents expected behavior and will automatically detect when the P2 bug is fixed.

**Pattern applied:** "xfail for known bugs" - tests show what SHOULD work, fail while bug exists, alert when fixed.

## Tests

- Run after fix: `.venv/bin/python -m pytest tests/engine/test_coalesce_contract_bug -v`

## Notes

- Source audit: `docs/test_audit/tests_engine_test_coalesce_contract_bug.audit.md`
