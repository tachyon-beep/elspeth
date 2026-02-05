# Test Audit: tests/engine/test_integration.py

**Lines:** 3696
**Test count:** 28 test methods across 12 test classes
**Audit status:** ISSUES_FOUND

## Summary

This is a comprehensive integration test file covering the full engine execution lifecycle including audit trail verification, fork/coalesce operations, routing, retry behavior, and error handling. The tests are valuable and thorough, but the file suffers from significant structural issues: excessive inline class duplication (10+ copies of nearly identical ListSource/CollectSink), very large file size making maintenance difficult, and some tests that manually build graphs rather than using production paths (though many do use production paths correctly). The core test logic is sound and validates critical audit requirements.

## Findings

### 🟡 Warning

1. **Massive inline class duplication (throughout file)**: The file defines nearly identical `ListSource` and `CollectSink` classes inline in almost every test method. Examples:
   - Lines 320-335 (ListSource in test_full_pipeline_with_audit)
   - Lines 354-371 (CollectSink in test_full_pipeline_with_audit)
   - Lines 459-475 (ListSource in test_audit_spine_intact)
   - Lines 498-515 (CollectSink in test_audit_spine_intact)
   - Lines 589-605 (ListSource in test_audit_spine_with_routing)
   - Lines 606-628 (CollectSink in test_audit_spine_with_routing)
   - And 15+ more occurrences

   The file already defines reusable `_ListSource` (line 95) and `_CollectSink` (line 126) at module level, but most tests define their own inline versions instead of using these helpers. This creates ~1500 lines of redundant boilerplate.

2. **`_build_production_graph` helper uses manual graph construction (lines 166-261)**: Despite the name suggesting "production" paths, this function manually calls `graph.add_node()` and `graph.add_edge()` rather than using `ExecutionGraph.from_plugin_instances()`. The docstring (line 167) even acknowledges this: "temporary until from_config is wired". This violates CLAUDE.md Test Path Integrity which states "Never bypass production code paths in tests."

3. **File size (3696 lines)**: The file is excessively large for a single test module. This makes it difficult to maintain and understand. Consider splitting into:
   - `test_integration_audit_spine.py` (audit spine tests)
   - `test_integration_fork_coalesce.py` (fork/coalesce/DAG tests)
   - `test_integration_retry.py` (retry behavior tests)
   - `test_integration_error_recovery.py` (error handling tests)

4. **Unused `_recorder` variables in some tests**: Similar to the group_id_consistency file, some tests create `recorder = LandscapeRecorder(db)` early but then use the db directly or let orchestrator create its own. Minor but adds confusion.

5. **Some tests use direct RowProcessor (lines 1162-1331)**: `TestForkIntegration.test_full_pipeline_with_fork_writes_all_children_to_sink` manually constructs a `RowProcessor` and calls `process_row()` directly. While this tests lower-level behavior, it bypasses the orchestrator's full pipeline flow. The test's docstring acknowledges this is a workaround for DiGraph limitations.

### 🔵 Info

1. **Deleted tests pattern (lines 1336-1359, 2363-2374)**: `TestAggregationIntegrationDeleted` and related tests verify that old interfaces are deleted. This is a good pattern for documenting deprecations while ensuring removed features stay removed.

2. **Module-scoped db fixture (lines 84-93)**: Uses `@pytest.fixture(scope="module")` for the database to improve test performance. Good practice.

3. **Comprehensive retry testing (lines 2607-2936)**: `TestRetryIntegration` thoroughly tests both transient failures (succeed after retries) and permanent failures (quarantine after max retries). These are valuable tests.

4. **Explain query tests (lines 2939-3407)**: `TestExplainQuery` verifies the critical audit lineage functionality including tracing through aggregations and coalesced tokens.

5. **Good assertion messages**: Most assertions include descriptive messages that would help diagnose failures.

6. **Schema handling**: Tests properly use `PluginSchema` subclasses or `_make_source_row` helper for schema contracts.

## Test Coverage Analysis

| Class | Tests | Purpose |
|-------|-------|---------|
| TestEngineIntegration | 4 | Import verification, full pipeline, audit spine, routing |
| TestNoSilentAuditLoss | 4 | Verify errors raise rather than skip silently |
| TestAuditTrailCompleteness | 2 | Empty source, multi-sink artifact recording |
| TestForkIntegration | 1 | Fork execution through pipeline |
| TestAggregationIntegrationDeleted | 2 | Verify old aggregation interfaces deleted |
| TestForkCoalescePipelineIntegration | 2 | Full fork-coalesce-sink flow |
| TestComplexDAGIntegration | 3 | Diamond DAG, metrics capture |
| TestRetryIntegration | 2 | Transient/permanent failure retry behavior |
| TestExplainQuery | 3 | Audit lineage tracing |
| TestErrorRecovery | 2 | Partial success, quarantined row audit |

## Structural Issues

1. **Duplication tax**: ~40% of the file is duplicated ListSource/CollectSink/schema definitions. Consolidating these would reduce the file to ~2200 lines.

2. **Mixed abstraction levels**: Some tests use full orchestrator, others use RowProcessor directly, others use individual executors (GateExecutor, TransformExecutor, etc.). While this provides coverage at different levels, it makes the file harder to reason about.

3. **`_build_production_graph` misnamed**: Function uses manual graph construction but has "production" in the name, which is misleading.

## Verdict

**SPLIT** - The test logic is valuable and should be preserved, but the file needs structural improvement:

1. Extract the inline class definitions to use the existing `_ListSource`/`_CollectSink` module-level helpers, or move to conftest
2. Rename or rewrite `_build_production_graph` to either actually use production paths OR rename to `_build_test_graph` to be honest about what it does
3. Split into 4-5 smaller, focused test files by category (audit spine, fork/coalesce, retry, error recovery, explain queries)

The core test assertions and scenarios are well-designed and catch real issues; the structural problems are about maintainability, not correctness.
