# Test Audit: tests/engine/test_aggregation_integration.py

**Lines:** 3228
**Test count:** 24 test functions
**Audit status:** ISSUES_FOUND

## Summary

This is a comprehensive integration test suite for aggregation timeout behavior, END_OF_SOURCE flushing, error handling, and expected output count enforcement. The tests are well-documented with explicit bug references (P1-2026-01-22, P2-2026-01-28, etc.) and exercise complex DAG execution scenarios. However, the file suffers from significant code duplication, with nearly identical boilerplate classes defined inline in each test method.

## Test Inventory

### TestAggregationTimeoutIntegration (3 tests)
1. `test_aggregation_timeout_flushes_during_processing` - Verifies timeout fires during active processing using MockClock
2. `test_aggregation_timeout_loop_checks_all_nodes` - Verifies timeout check iterates over all aggregation nodes
3. `test_timeout_fires_before_row_processing` - Verifies timeout is checked BEFORE each row is processed

### TestEndOfSourceFlush (5 tests)
1. `test_end_of_source_single_mode` - END_OF_SOURCE flush with single output_mode
2. `test_end_of_source_passthrough_mode` - END_OF_SOURCE flush with passthrough output_mode
3. `test_end_of_source_transform_mode` - END_OF_SOURCE flush with transform output_mode
4. `test_end_of_source_passthrough_with_downstream_transform` - Passthrough routes through downstream transforms
5. `test_end_of_source_single_with_downstream_transform` - Single mode routes through downstream transforms

### TestTimeoutFlushErrorHandling (7 tests)
1. `test_timeout_flush_error_single_mode_no_duplicate_outcomes` - Verifies no duplicate terminal outcomes on flush failure
2. `test_timeout_flush_downstream_routed_counts_tracked` - Verifies routed counts tracked for timeout flushes
3. `test_passthrough_flush_failure_marks_all_buffered_tokens_failed` - All buffered tokens marked FAILED on passthrough flush failure
4. `test_passthrough_end_of_source_flush_failure_marks_all_failed` - END_OF_SOURCE passthrough flush failure marks all FAILED
5. `test_single_mode_count_flush_failure_triggering_token_has_outcome` - Triggering token has outcome on count flush failure
6. `test_transform_mode_count_flush_failure_triggering_token_has_outcome` - Same as above for transform mode

### TestTimeoutFlushStepIndexing (2 tests)
1. `test_timeout_flush_records_1_indexed_step` - Verifies step_index is 1-indexed for timeout flush
2. `test_end_of_source_flush_records_1_indexed_step` - Verifies step_index is 1-indexed for END_OF_SOURCE flush

### TestExpectedOutputCountEnforcement (4 tests)
1. `test_expected_output_count_matches_passes` - Matching count completes successfully
2. `test_expected_output_count_mismatch_raises_runtime_error` - Mismatched count raises RuntimeError
3. `test_expected_output_count_timeout_flush_path` - Count enforcement in timeout flush path
4. `test_expected_output_count_none_skips_validation` - None expected_output_count skips validation

## Findings

### :large_yellow_circle: Warning

**W1: Massive code duplication - inline class definitions (Lines: throughout)**

Nearly every test method defines its own inline Source, Transform, and Sink classes. These are structurally identical with only minor variations. For example:
- `CollectorSink` is defined ~15 times with identical structure
- `FastSource` variants are defined ~10 times
- `BaseTransform` subclasses with nearly identical `process()` methods appear repeatedly

This creates:
- ~2000+ lines of boilerplate (roughly 62% of the file)
- Maintenance burden if base patterns change
- Harder to identify what makes each test unique

**W2: Module-scoped fixture for LandscapeDB may cause test pollution (Line 53-56)**

```python
@pytest.fixture(scope="module")
def landscape_db() -> LandscapeDB:
    """Module-scoped in-memory database for aggregation integration tests."""
    return LandscapeDB.in_memory()
```

All 24 tests share the same database. While tests query by `run_id`, accumulated data could cause unexpected performance degradation or subtle interactions. The DB records from all 24 tests accumulate in the same in-memory database.

**W3: Tests contain assertions that explicitly document known bugs (Multiple tests)**

Several tests have assertions with comments like:
- "BUG: rows_routed should be > 0" (line 2680)
- "Bug: _check_aggregation_timeouts counts ROUTED as succeeded" (line 2683)
- "Bug: Tokens stuck in BUFFERED state forever" (line 2015)

These assertions appear to test for bug fixes. If the bugs exist, tests should be failing. If bugs are fixed, the comments are misleading. Status of these bugs is unclear from the test file alone.

**W4: Unused imports (Line 25)**

`SourceRow` is imported but the only direct use is as a return type annotation in the inline source classes' `load()` methods. This is not incorrect but suggests the inline pattern could be refactored.

### :large_blue_circle: Info

**I1: Good use of MockClock for deterministic timeout testing**

Tests use `MockClock` with `CallbackSource.after_yield_callback` to deterministically advance time. This is a sound pattern for testing timeout behavior without flaky time-based tests.

**I2: Comprehensive bug reference documentation**

Each test class and many individual tests include explicit bug ticket references (P1-2026-01-22, P2-2026-01-28, etc.) with detailed explanations of the bug mechanics. This is excellent for traceability.

**I3: Tests verify audit trail integrity at database level**

Several tests (e.g., lines 1854-1871, 2021-2034, 2197-2215) directly query the `token_outcomes_table` to verify terminal outcomes are properly recorded. This is appropriate for an audit-focused system.

**I4: Tests cover both happy path and error paths**

The suite covers success cases, flush failures, duplicate outcome prevention, and various output modes (single, passthrough, transform).

## Verdict

**SPLIT** - The test coverage is valuable and thorough, but the file should be refactored:

1. Extract common test helpers (reusable Source, Sink, Transform base implementations) into a shared module or conftest fixtures
2. Consider splitting into multiple files by test class (e.g., `test_aggregation_timeout.py`, `test_aggregation_end_of_source.py`, `test_aggregation_error_handling.py`)
3. Change the module-scoped `landscape_db` fixture to function-scoped, or ensure proper cleanup
4. Clarify the status of the documented bugs - if fixed, update comments; if not fixed, tests should be marked `xfail`

The underlying test logic is sound and provides valuable coverage for a complex subsystem. The issue is maintainability due to the extreme code duplication.
