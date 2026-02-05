# Audit: tests/engine/test_orchestrator_fork_coalesce.py

**Lines:** 867
**Tests:** 9
**Audit:** WARN

## Summary

This test file validates Orchestrator's handling of fork/coalesce functionality. It includes both production-path tests using `ExecutionGraph.from_plugin_instances()` and unit tests with controlled mocks. The tests are well-documented with clear explanations of mock cascades. However, some tests use extensive mocking that verifies implementation details rather than behavior.

## Findings

### Positive Aspects

1. **Production Graph Construction (lines 165, 236-244, 322-330, 448-456, 524-532, 652-660, 745-753, 833-841):** Most tests correctly use `ExecutionGraph.from_plugin_instances()` directly or via `build_production_graph()`. This satisfies the Test Path Integrity requirement.

2. **Excellent Mock Documentation (lines 334-354, 534-555):** The mock cascade explanations are exemplary - they explain WHY mocking is needed (FK constraints on fake token IDs) and WHERE integration coverage exists (references to specific tests in other files). This is how mock usage should be documented.

3. **Uses Real Plugins (lines 224, 312, 436, etc.):** Tests use `instantiate_plugins_from_config(settings)` to get real plugin instances from configuration, then build graphs with those plugins.

4. **Reusable Test Fixtures (lines 57-73):** `CoalesceTestSource` provides a reusable source for coalesce tests that yields configurable rows.

### Issues

1. **Implementation Detail Testing (WARN - lines 246-262):** Test `test_orchestrator_creates_coalesce_executor_when_config_present` mocks `RowProcessor` and verifies constructor kwargs. The test itself acknowledges this is suspicious with a TODO comment (lines 246-248).

   - **Impact:** Medium - tests implementation rather than behavior, could pass even if coalesce is broken
   - **Evidence:** Lines 249-262 verify `coalesce_executor` kwarg exists but don't verify it works
   - **Recommendation:** The TODO suggests replacing with behavior-based test in "Phase 5"

2. **Heavy Mocking Pattern (WARN - lines 368-396):** Test `test_orchestrator_handles_coalesced_outcome` mocks three components (RowProcessor, SinkExecutor, record_token_outcome). While documented, this creates a fragile test.

   - **Impact:** Medium - changes to orchestrator internals could break test without actual bug
   - **Mitigation:** Documentation explains integration coverage exists elsewhere
   - **Recommendation:** Consider if this unit test adds value beyond integration tests

3. **Potential Step Map Calculation Issue (INFO - lines 851-866):** The step map calculation test expects `expected_step = 0 + 1 = 1`, but the comments mention "gate_idx + 1" semantics. If the implementation changes, this test's assertions may become incorrect.

   - **Impact:** Low - test correctly verifies current behavior
   - **Recommendation:** Add a comment explaining the expected topology

### Missing Coverage

1. **Fork Token Creation (INFO):** The file notes (lines 77-83) that full fork testing at orchestrator level is blocked by DiGraph limitations (can't store multiple edges between same nodes). Fork logic is tested at processor level in `test_processor.py`.

2. **Coalesce with Real Tokens (INFO):** While mock-based tests verify routing, real token flow with FK constraints is deferred to integration tests (properly referenced in comments).

## Test Class Discovery

- `TestOrchestratorForkExecution`: Properly named - will be discovered
- `TestCoalesceWiring`: Properly named - will be discovered
- `TestCoalesceStepMapCalculation`: Properly named - will be discovered
- `CoalesceTestSource`: Not a test class (no "Test" prefix, no test methods) - correctly not discovered

## Verdict

**WARN** - Tests are well-documented and use production code paths for graph construction. However, some tests verify implementation details (mock RowProcessor constructor kwargs) rather than behavior. The extensive mock documentation is excellent and explains that integration coverage exists elsewhere. The warning is due to the acknowledged "suspicious" implementation detail testing that should be refactored per the existing TODO.
