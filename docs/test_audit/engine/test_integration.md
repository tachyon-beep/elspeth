# Test Audit: tests/engine/test_integration.py

**Lines:** 3696
**Tests:** 25
**Test Classes:** 10
**Audit:** WARN

## Summary

This is a large integration test file that covers critical engine functionality including full pipeline execution, audit trail verification, fork/coalesce operations, retry behavior, and error recovery. The tests are comprehensive and valuable, but the file suffers from significant code duplication and test path integrity issues that should be addressed.

## Findings

### Critical

- **Test Path Integrity Violation (Lines 166-261)**: The `_build_production_graph()` helper function manually constructs execution graphs using `graph.add_node()` and direct attribute assignment (`graph._sink_id_map`, `graph._transform_id_map`, etc.) instead of using `ExecutionGraph.from_plugin_instances()`. Per CLAUDE.md, this violates the Test Path Integrity principle. The docstring even acknowledges this: "Build a simple graph for testing (temporary until from_config is wired)." This means if the production `from_plugin_instances()` or `from_config()` has bugs, these tests will pass while production fails.

### Warning

- **Massive Inline Class Duplication**: The file contains 14 inline `ListSource` definitions and 15 inline `CollectSink` definitions. While `_ListSource` and `_CollectSink` module-level helpers exist (lines 95-163), most tests still define their own. These duplicates are nearly identical, wasting ~2000+ lines. Tests should reuse the module-level `_ListSource` and `_CollectSink` classes.

- **hasattr() Usage (Lines 433, 1352, 1358, 2373)**: Four uses of `hasattr()` found:
  - Line 433: `if hasattr(state, "error_json")` - This may be legitimate for polymorphic NodeState types
  - Lines 1352, 1358, 2373: Used to verify classes are deleted - legitimate test assertions

- **File Size (3696 lines)**: The file is oversized and could be split into logical groups:
  - `test_integration_audit.py` - Audit spine and completeness tests (TestEngineIntegration, TestAuditTrailCompleteness)
  - `test_integration_fork_coalesce.py` - Fork/coalesce integration (TestForkIntegration, TestForkCoalescePipelineIntegration)
  - `test_integration_complex_dag.py` - Complex DAG patterns (TestComplexDAGIntegration)
  - `test_integration_retry.py` - Retry behavior (TestRetryIntegration)
  - `test_integration_errors.py` - Error handling (TestNoSilentAuditLoss, TestErrorRecovery)
  - `test_integration_explain.py` - Explain/lineage queries (TestExplainQuery)

- **Module-Scoped Database Fixture (Line 84-92)**: Using `scope="module"` for the database fixture is efficient but requires unique run_ids per test. The comment acknowledges this constraint. Tests appear to handle this correctly, but any failure could cause cascading test pollution.

### Info

- **All Test Classes Named Correctly**: All 10 test classes are prefixed with `Test` - pytest will discover them correctly.

- **TestAggregationIntegrationDeleted Class (Lines 1336-1358)**: This class exists solely to verify old code was deleted. While this is a valid audit check, it could be simplified to a single test in a different location or removed after the deletion is confirmed stable.

- **test_full_feature_pipeline_deleted (Line 2363-2373)**: Similar deletion verification test. Consider consolidating with TestAggregationIntegrationDeleted.

- **Good Use of Helper Functions**: The `_make_source_row()` helper (lines 64-81) properly creates SourceRow with OBSERVED schema, avoiding code duplication.

- **Comprehensive Assertions**: Tests include thorough assertions for audit trail completeness, checking node_states, tokens, routing events, and artifacts.

## Test Path Integrity Analysis

The `_build_production_graph()` function is the core issue. It manually:
1. Creates an `ExecutionGraph()` directly
2. Calls `graph.add_node()` repeatedly
3. Calls `graph.add_edge()` repeatedly
4. Directly assigns internal maps: `graph._sink_id_map`, `graph._transform_id_map`, `graph._config_gate_id_map`, `graph._route_resolution_map`, `graph._default_sink`

This bypasses all validation and transformation logic in the production `from_plugin_instances()` method. If that method has a bug (like BUG-LINEAGE-01 mentioned in CLAUDE.md), these tests would pass but production would fail.

**Impact**: 15 of 25 tests (60%) use `_build_production_graph()` via `orchestrator.run()`.

## Duplication Metrics

| Inline Class | Count | Should Use |
|--------------|-------|------------|
| `ListSource` | 14 | `_ListSource` (module-level) |
| `CollectSink` | 15 | `_CollectSink` (module-level) |
| `EmptySource` | 1 | Could be added to module helpers |
| Transform classes | ~15 | These are test-specific, duplication acceptable |
| Sink subclasses | ~5 | `RoutedSink`, `ExplodingSink` etc. - test-specific |

## Recommendations

1. **HIGH PRIORITY**: Fix Test Path Integrity - Replace `_build_production_graph()` with production code paths. Either:
   - Wire up `ExecutionGraph.from_plugin_instances()`
   - Wire up `ExecutionGraph.from_config()` when available
   - The docstring acknowledges this is a known issue

2. **MEDIUM PRIORITY**: Deduplicate inline classes - Update all tests to use `_ListSource` and `_CollectSink` module-level helpers. This would remove ~1500+ lines.

3. **MEDIUM PRIORITY**: Split the file - 3696 lines is difficult to maintain. The logical groupings identified above would improve navigation and reduce cognitive load.

4. **LOW PRIORITY**: Consolidate deletion verification tests into a single test file (e.g., `test_deleted_interfaces.py`).

## Verdict

**WARN** - Tests are comprehensive and valuable, but the Test Path Integrity violation in `_build_production_graph()` is a significant concern that could hide production bugs. The massive code duplication makes the file harder to maintain than necessary. Recommend addressing the production code path issue and deduplicating before additional integration tests are added.
