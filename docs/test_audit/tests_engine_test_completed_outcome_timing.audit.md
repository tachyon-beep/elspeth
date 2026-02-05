# Test Audit: tests/engine/test_completed_outcome_timing.py

**Lines:** 407
**Test count:** 3
**Audit status:** ISSUES_FOUND

## Summary

This is a well-structured regression test file documenting a known bug in COMPLETED outcome timing. The tests are designed to FAIL with current code (proving the bug exists) and PASS when the bug is fixed. The file serves dual purposes: documenting the contract violations and providing regression tests for the fix. However, there are structural issues with code duplication and the tests may give a misleading impression of test suite health.

## Findings

### Warning

1. **Significant code duplication across test classes (lines 133-186, 243-276, 338-377)**: The `ListSource`, `PassthroughTransform`, and `FailingSink` classes are redefined identically in each of the three test methods. This should be extracted to module-level fixtures or helper classes.

2. **Tests designed to fail may confuse CI interpretation**: The docstrings clearly state these tests "currently FAIL because the bug exists" but there is no pytest marker (like `@pytest.mark.xfail`) to indicate expected failure. Running these tests will show failures that may be misinterpreted as regressions rather than documented bugs.

3. **`_build_graph` helper manually constructs graph internals (lines 58-101)**: The helper directly sets internal attributes like `graph._sink_id_map`, `graph._transform_id_map`, etc. Per CLAUDE.md's "Test Path Integrity" section, this risks testing different code paths than production. Should use `ExecutionGraph.from_plugin_instances()` for integration tests.

### Info

1. **Excellent documentation**: Each test has comprehensive docstrings explaining the bug under test, the contract invariants being verified, and the expected behavior difference between buggy and fixed code.

2. **Direct database assertions verify audit trail integrity (lines 206-228, 299-325, 395-407)**: The tests directly query `token_outcomes_table` and `node_states_table` to verify audit trail invariants, which is appropriate for testing Landscape integrity.

3. **Tests reference specific documentation**: Tests cite `docs/audit/tokens/00-token-outcome-contract.md` and specific invariant numbers, making the relationship between tests and specifications clear.

## Verdict

**KEEP** with modifications needed. The tests serve a valuable purpose documenting a known bug and will become proper regression tests once the bug is fixed. However:
- Add `@pytest.mark.xfail(reason="BUG: COMPLETED recorded before sink write")` until the bug is fixed
- Extract duplicated plugin classes to module level
- Consider using production graph construction path for better test fidelity
