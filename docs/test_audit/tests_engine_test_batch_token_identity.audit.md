# Test Audit: tests/engine/test_batch_token_identity.py

**Lines:** 365
**Test count:** 3 test functions
**Audit status:** PASS

## Summary

This is an excellent regression test file specifically designed to catch bug `elspeth-rapid-nd3` (token reuse in batch aggregation). The tests are identity-based rather than count-based, meaning they verify WHICH specific tokens have WHICH outcomes rather than just counting outcomes. This approach prevents false-positive tests where counts match but the wrong tokens get wrong outcomes.

## Findings

### Information

- **Lines 1-15**: The file header clearly documents the specific bug being tested (`elspeth-rapid-nd3`) and explains why identity-based testing is superior to count-based testing for this scenario.

- **Lines 31-34**: The tests use helper functions from `tests/helpers/audit_assertions.py` (`assert_all_batch_members_consumed`, `assert_output_token_distinct_from_inputs`) which promotes reusability and consistent assertion patterns.

- **Lines 95-185**: `test_all_batch_members_consumed_in_batch` is the core regression test. It processes 3 rows through batch aggregation and verifies:
  1. All input tokens have `CONSUMED_IN_BATCH` outcome
  2. The output token has a distinct token_id from all inputs
  3. The aggregation result is correct (sum = 60)

- **Lines 187-278**: `test_triggering_token_not_reused` specifically tests the bug scenario where the token that triggers the flush could be incorrectly reused as output. The comments on lines 267-272 clearly document the bug/fix relationship.

- **Lines 280-365**: `test_batch_members_correctly_recorded` verifies the audit trail by directly querying `batch_members_table` to ensure all input tokens are recorded. This tests audit completeness essential for lineage explanation.

### Design Notes

- **Lines 57-89**: The `SumTransform` is a minimal but complete implementation that properly:
  - Declares `is_batch_aware = True` and `creates_tokens = True`
  - Handles both list input (batch) and single row (passthrough)
  - Creates proper contracts for output rows

- The tests use real `RowProcessor` and `LandscapeRecorder` instances rather than mocking, ensuring production code paths are exercised.

- Each test has a clear, specific purpose and documents the invariant being verified.

## Verdict

**KEEP** - This is a model regression test file. It clearly documents the bug being prevented, uses identity-based assertions rather than count-based assertions, and exercises real production code paths. The tests are focused, well-documented, and serve as reliable protection against the specific bug they were designed to catch.
