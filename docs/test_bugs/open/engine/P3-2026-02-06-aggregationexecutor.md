# Test Bug Report: Fix weak assertions in aggregation_executor

## Summary

- This is a comprehensive test file for the AggregationExecutor with good coverage of buffering, checkpoint/restore functionality, and edge cases. The tests properly use real database fixtures (not mocks) and follow production code paths. However, there are some minor issues with test organization, one potential test that does nothing effective, and some structural concerns around repeated boilerplate setup code.

## Severity

- Severity: trivial
- Priority: P3
- Verdict: **KEEP**

## Reporter

- Name or handle: Test Audit
- Date: 2026-02-06
- Audit file: docs/test_audit/tests_engine_test_aggregation_executor.audit.md

## Test File

- **File:** `tests/engine/test_aggregation_executor`
- **Lines:** 1748
- **Test count:** 31

## Findings

- **Impact:**: Test appears to provide coverage but validates nothing substantial. 2. **W002: Excessive use of `hasattr()` for deletion verification (lines 69, 90-91, 107, 230)** - Multiple tests use `hasattr()` to verify old methods are deleted. While this is semantically valid for verifying interface changes, these tests could be consolidated into a single parameterized test. - **Impact:** Test file inflation, minor maintenance burden. 3. **W003: Mocking `logging.getLogger` may not work as expected (lines 1284-1295, 1475-1482, 1546-1556)** - Tests mock `logging.getLogger` but this may not capture the actual logger used if the module imports it at load time. The mock would need to patch the specific module's logger reference. - **Impact:** Tests may pass without actually verifying the warning is logged in production. 4. **W004: Large test setup boilerplate repeated ~25+ times** - Nearly every test repeats: create recorder, begin_run, register_node, create settings, create executor. This could be extracted to fixtures or a setup method. - **Impact:** Code duplication, harder maintenance, ~500+ lines of boilerplate. 5. **W005: Checkpoint size tests create very large data structures (lines 1267-1277, 1337-1350, 1393-1402, 1456-1468, 1528-1540)** - Tests that verify checkpoint size warnings/errors create arrays of 750-6000 tokens with large string data. While necessary for the functionality being tested, these tests may be slow. - **Impact:** Potential slow test execution.


## Verdict Detail

**KEEP** - The test file provides solid coverage of the AggregationExecutor's buffering and checkpoint functionality. The warnings identified are minor structural issues (boilerplate duplication, potentially ineffective logging mocks, one vestigial test) that do not invalidate the test coverage. Recommend consolidating the "old interface deleted" tests and extracting common setup to fixtures in a future refactoring pass.

## Proposed Fix

- [ ] Weak assertions strengthened
- [ ] Redundant tests consolidated
- [ ] Test intent clearly expressed in assertions

## Tests

- Run after fix: `.venv/bin/python -m pytest tests/engine/test_aggregation_executor -v`

## Notes

- Source audit: `docs/test_audit/tests_engine_test_aggregation_executor.audit.md`
