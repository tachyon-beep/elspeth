# Test Audit: tests/engine/test_coalesce_contract_bug.py

**Lines:** 83
**Test count:** 1 active test function (2 commented out)
**Audit status:** ISSUES_FOUND

## Summary

This file documents a known P2 bug where coalesce with `merge="nested"` or `merge="select"` strategies creates data with a structure that doesn't match the merged contract. The active test correctly demonstrates the bug by showing that PipelineRow access fails for both the nested keys and the original field names. However, the test is currently serving as documentation of a known bug rather than regression protection.

## Findings

### 🔴 Critical

1. **Test Passes When Bug Exists (Lines 25-83)** - The test `test_pipeline_row_nested_access_demonstrates_bug` is designed to PASS while the bug exists and fail when fixed. This inverts normal test semantics. The docstring explains this, but it means CI will start failing when someone fixes the bug unless they know to update this test. This is a maintenance trap.

2. **Commented Out Integration Tests (Lines 13-22)** - Two integration tests are commented out with a note "pending decision on test fixtures". These would provide actual regression coverage but are disabled:
   ```python
   # def test_coalesce_nested_with_downstream_transform_fails(tmp_path, mock_clock):
   #     """Reproduce P2: nested merge creates data with branch keys, but contract has original fields."""
   #     pass
   ```

### 🟡 Warning

1. **No Bug Ticket Reference** - The P2 bug is described but there's no reference to a bug tracking ticket (e.g., `# Bug: P2-2026-XX-XX`). This makes it hard to track when the bug should be fixed.

2. **Test Only Verifies Failure Mode, Not Expected Behavior** - The test demonstrates what goes wrong but doesn't define what the correct behavior should be in a testable way. A proper test would have assertions for the expected post-fix behavior that are currently skipped/xfailed.

### 🔵 Info

1. **Good Bug Documentation** - The docstrings clearly explain:
   - What the bug is (contract/data mismatch for nested merge)
   - Why it happens (SchemaContract.merge() doesn't account for nesting)
   - What the expected fix should do

2. **Unit Test Level** - This test operates at the unit level (SchemaContract and PipelineRow) rather than requiring full pipeline infrastructure, which is appropriate for demonstrating the contract mismatch.

## Verdict

**REWRITE** - This test file needs to be restructured to provide proper regression coverage. The current test that "passes when the bug exists" is an anti-pattern that will cause CI failures when the bug is fixed. Recommended changes:

1. Mark the current test with `@pytest.mark.xfail(reason="P2 bug: nested merge contract mismatch", strict=True)` and invert the assertions to show expected behavior
2. Enable the commented integration tests with proper fixtures
3. Add a bug ticket reference for tracking
4. When the bug is fixed, the xfail tests will start passing (strict=True will fail if they unexpectedly pass, alerting the fixer to remove the marker)
