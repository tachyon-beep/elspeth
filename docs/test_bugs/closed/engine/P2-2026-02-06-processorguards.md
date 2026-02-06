# Test Bug Report: Rewrite weak assertions in processor_guards

## Summary

- This test file covers processor safety guards including the MAX_WORK_QUEUE_ITERATIONS limit. While the intent is valid (preventing infinite loops in pathological DAGs), the test quality is mixed. Some tests are meaningful behavioral tests, but others are purely structural or tautological checks that provide limited value.

## Severity

- Severity: minor
- Priority: P2
- Verdict: **REWRITE**

## Reporter

- Name or handle: Test Audit
- Date: 2026-02-06
- Audit file: docs/test_audit/tests_engine_test_processor_guards.audit.md

## Test File

- **File:** `tests/engine/test_processor_guards`
- **Lines:** 263
- **Test count:** 5

## Findings

- **Lines 70-76: test_max_work_queue_iterations_constant_value**: - This test only asserts that a constant equals 10,000. If someone changes the constant, the test fails but that's the expected behavior when changing configuration. This is a tautology - the test provides zero defect detection value. It's documentation masquerading as a test.
- **Lines 169-182: test_normal_processing_completes_without_hitting_guard**: - This test contains NO executable test code. It's purely assertions about the constant value: ```python assert MAX_WORK_QUEUE_ITERATIONS > 10 assert MAX_WORK_QUEUE_ITERATIONS > 1000 ``` There's no actual processing tested. The docstring claims it's a "sanity check" but it tests nothing about normal processing behavior.
- **Lines 250-263: test_guard_constant_is_reasonable**: - Another test that only asserts constant values. Three assertions about the same constant (>= 1000, <= 100,000, == 10,000). Completely redundant with other tests and provides no behavioral verification.
- **Lines 78-167: test_work_queue_exceeding_limit_raises_runtime_error**: - This test re-implements the work queue loop logic from processor.py instead of testing the actual processor behavior. The patching approach (`patch.object(processor, "_process_single_token")`) creates a test that could pass even if the production code's guard is broken. The test manually implements the guard check at line 158-159, which means it's testing the test's own implementation, not the production code's guard.
- **Lines 184-248: test_iteration_guard_exists_in_process_row**: - This is the only test that actually exercises the production code path with real transforms. However, it only tests the happy path (guard doesn't fire) rather than the guard actually firing.
- **Lines 32-64: Helper functions**: - `_make_pipeline_row()` and `_make_observed_contract()` are duplicated from other test files.


## Verdict Detail

**REWRITE** - 3 of 5 tests provide essentially zero value (constant equality checks). The main guard test re-implements production logic rather than testing it. Recommend:
1. Delete `test_max_work_queue_iterations_constant_value`, `test_normal_processing_completes_without_hitting_guard`, and `test_guard_constant_is_reasonable`
2. Rewrite `test_work_queue_exceeding_limit_raises_runtime_error` to actually trigger the production guard (e.g., by creating a transform that forks infinitely, or by using a lower but still realistic limit)
3. Keep `test_iteration_guard_exists_in_process_row` as a baseline sanity check

## Proposed Fix

- [x] Tests have specific, non-permissive assertions
- [x] Each test verifies the exact expected behavior
- [x] No "or 'error' in output" fallback patterns
- [x] Tests fail when actual behavior differs from expected

## Resolution

**Date:** 2026-02-06

**Actions taken:**

1. **Deleted** `test_max_work_queue_iterations_constant_value` - Pure tautology (asserts constant == 10000)
2. **Deleted** `test_guard_constant_is_reasonable` - Pure tautology (asserts constant in range and equals 10000)
3. **Kept** `test_work_queue_exceeding_limit_raises_runtime_error` - Actually calls production `process_row()` with mocked `_process_single_token` to inject bug scenario; verifies guard fires
4. **Kept** `test_production_processing_with_multiple_transforms` - Runs 10 real transforms through production code; verifies all execute correctly
5. **Kept** `test_iteration_guard_exists_in_process_row` - Simple baseline test with single transform

**Result:** 5 tests reduced to 3 meaningful behavioral tests. All tests pass.

**Note:** The audit mentioned `test_normal_processing_completes_without_hitting_guard` but the file contained `test_production_processing_with_multiple_transforms` - this test was already improved since the audit and actually runs real code through 10 transforms. Similarly, `test_work_queue_exceeding_limit_raises_runtime_error` was already correctly calling production code (just mocking the internal method to create the bug scenario).

## Tests

- Run after fix: `.venv/bin/python -m pytest tests/engine/test_processor_guards -v`

## Notes

- Source audit: `docs/test_audit/tests_engine_test_processor_guards.audit.md`
