# Test Audit: tests/engine/test_orchestrator_retry.py

**Lines:** 251
**Test count:** 2
**Audit status:** PASS

## Summary

This test file covers orchestrator retry functionality with two focused integration tests: one for successful retry after transient failure, and one for exhausted retries marking the row as failed. The tests use real plugins, proper closure-based tracking, and the production graph path via `build_production_graph()`. The tests are well-structured and test meaningful behavior with exact assertions.

## Findings

### 🔵 Info

1. **Good Use of Production Graph Path (Lines 132, 240)**: Both tests use `build_production_graph(config)` from the helper module rather than manual graph construction, following the "Test Path Integrity" principle from CLAUDE.md.

2. **Appropriate Closure-Based Tracking (Line 65-66)**: The `attempt_count` closure pattern (`{"count": 0}`) is used to track retry attempts across the transform, which is a clean approach for verifying retry behavior without mocking.

3. **Exact Value Assertions (Lines 138-143, 246-250)**: Tests use exact value assertions (e.g., `assert attempt_count["count"] == 2`) rather than vacuous `>= 0` checks, properly verifying expected behavior.

4. **Full Plugin Implementations**: Test plugins (`ListSource`, `RetryableTransform`, `AlwaysFailTransform`, `CollectSink`) inherit from proper base classes and implement all required methods, matching production usage patterns.

5. **Realistic Configuration**: Tests use realistic `ElspethSettings` with retry configuration including delays (lines 114-118, 222-226), testing the actual settings-to-runtime path.

6. **Duplicate Inline Test Classes**: Both tests define nearly identical `ListSource` and `CollectSink` classes (lines 47-63 vs 162-178, lines 82-100 vs 191-209). These could be extracted to module level or a shared fixture, but this is a minor concern.

7. **Fast Test Delays (Lines 116-117, 224-225)**: Retry delays are set very low (`0.01` seconds) for fast test execution without compromising test validity.

## Verdict

**KEEP** - Clean, focused tests that follow best practices. The two tests provide good coverage of both the success-after-retry and exhausted-retries scenarios. The duplicate test class definitions are a minor code smell but don't affect test quality.
