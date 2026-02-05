# Test Audit: tests/engine/test_orchestrator_errors.py

**Lines:** 797
**Tests:** 8
**Audit:** WARN

## Summary

This file tests orchestrator error handling and quarantine functionality, including transform exceptions, invalid quarantine destinations, quarantine metrics, and token outcome recording. Tests use production code paths and test real audit trail behavior. However, some tests are explicitly testing for known bugs and will fail when the bugs are fixed.

## Test Classes

| Class | Tests | Purpose |
|-------|-------|---------|
| `TestOrchestratorErrorHandling` | 1 | Transform exception marks run as FAILED |
| `TestOrchestratorSourceQuarantineValidation` | 1 | Invalid quarantine destination fails at init |
| `TestOrchestratorQuarantineMetrics` | 1 | Quarantined rows counted separately from failed |
| `TestSourceQuarantineTokenOutcome` | 2 | QUARANTINED token_outcome recording and durability |
| `TestQuarantineDestinationRuntimeValidation` | 2 | Invalid destinations at runtime crash |

## Findings

### Strengths

1. **Production Code Path Compliance (Good)**: All tests use `build_production_graph(config)` which calls `ExecutionGraph.from_plugin_instances()` internally.

2. **Real Audit Trail Testing (Good)**: Tests query actual database tables (`token_outcomes_table`) to verify audit integrity, not just mock objects.

3. **Bug Documentation as Tests (Good)**: Tests document known bugs with detailed comments (e.g., `P1-2026-01-31-quarantine-outcome-before-durability`).

4. **Defensive Testing Patterns (Good)**: Tests verify both positive cases (row went to quarantine sink) AND audit trail completeness (QUARANTINED outcome recorded).

### Warnings

1. **Bug-Testing Tests May Fail After Fix (Lines 447-551)**
   - `test_quarantine_outcome_not_recorded_if_sink_fails` explicitly tests for bug `P1-2026-01-31`.
   - Comment on line 545: "BUG: Currently this FAILS because QUARANTINED is recorded BEFORE sink durability"
   - When this bug is fixed, the test will need to be updated.
   - **Recommendation**: Consider adding skip marker or xfail if bug not yet fixed.

2. **Runtime Crash Tests Expect Unspecified Exception (Lines 678, 790)**
   - `test_invalid_quarantine_destination_at_runtime_crashes` uses `pytest.raises(Exception)` - very broad.
   - Tests document this as known bugs that currently don't crash but should.
   - If the tests run against current code and no crash happens, they may fail unexpectedly.
   - **Severity**: Medium - these are valid tests for expected behavior but may fail intermittently if bugs partially fixed.

3. **Test Uses `row.get()` Pattern (Line 272)**
   ```python
   if row.get("quality") == "bad":
   ```
   - CLAUDE.md prohibits defensive `.get()` patterns in general, but this is testing user data (row values), which is legitimate per the Three-Tier Trust Model.
   - The row value could genuinely be missing, so `.get()` is appropriate here.
   - **Not a violation** - included for completeness.

### Missing Coverage (Minor)

1. **No test for transform retry exhaustion**: Tests check transform exception handling but not the case where retries exhaust and a row becomes FAILED vs QUARANTINED.

2. **No test for multiple quarantined rows**: Tests verify single quarantined row counting but don't test edge case of all rows being quarantined.

### No Issues Found

- All test classes have proper `Test` prefix
- No overmocking
- No empty tests
- Proper inheritance from base classes

## Verdict

**WARN** - Tests are well-structured and use production code paths, but some tests explicitly test known bugs. When those bugs are fixed, test maintenance will be needed. Consider adding `pytest.mark.xfail` decorators to bug-testing tests or splitting into separate "regression" and "expected behavior" test files.

### Recommendations

1. Add `@pytest.mark.xfail(reason="P1-2026-01-31: QUARANTINED recorded before durability")` to `test_quarantine_outcome_not_recorded_if_sink_fails` if bug not yet fixed.

2. Add `@pytest.mark.xfail(reason="P2-2026-01-31: Runtime destination validation not implemented")` to the `TestQuarantineDestinationRuntimeValidation` tests if those bugs are not yet fixed.

3. After bugs are fixed, convert xfail tests to normal tests.
