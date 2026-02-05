# Test Audit: tests/engine/test_orchestrator_lifecycle.py

**Lines:** 548
**Test count:** 6
**Audit status:** ISSUES_FOUND

## Summary

This file tests plugin lifecycle hooks (on_start, on_complete, close) in the Orchestrator. The tests verify correct call ordering and error resilience. However, there is significant overmocking - particularly of sources and sinks - which creates test fragility and may hide integration issues. The manual graph construction also bypasses production validation.

## Findings

### 🔴 Critical

1. **Lines 122-131, 207-216, 291-300, 369-371, 441-448, 531-540: Manual graph construction bypasses production code path**
   - Every test manually constructs `ExecutionGraph` with direct `add_node`/`add_edge` calls and sets private attributes (`graph._transform_id_map`, `graph._sink_id_map`, `graph._default_sink`).
   - Per CLAUDE.md "Test Path Integrity": "Never bypass production code paths in tests."
   - Impact: Tests may pass while `ExecutionGraph.from_plugin_instances()` is broken. The BUG-LINEAGE-01 lesson explicitly warns against this pattern.

### 🟡 Warning

1. **Lines 88-101, 175-187, 260-272, 417-429, 508-519: Heavy source mocking**
   - Each test creates a `MagicMock()` source with 10+ manually configured attributes (`name`, `_on_validation_failure`, `determinism`, `plugin_version`, `output_schema`, `load`, `get_field_resolution`, `get_schema_contract`).
   - This creates implicit coupling to source protocol - any new required attribute breaks all tests.
   - Impact: Maintenance burden and potential for tests to pass while real sources fail.

2. **Lines 104-113, 189-199, 275-283, 346-355, 423-428, 508-519: Mixed real/mock plugins**
   - Tests use real `TrackedTransform` but mock source and sink, creating inconsistent coverage.
   - Real plugins test actual behavior; mocks test assumed contracts.

3. **Lines 34-49: Helper creates minimal SourceRow**
   - `_make_test_source_row` creates SourceRow with OBSERVED contract - reasonable for mocking but diverges from real source behavior.

### 🔵 Info

1. **Lines 52-138: Core lifecycle ordering test**
   - `test_on_start_called_before_processing` correctly verifies `call_order[0] == "on_start"` before `"process"`.
   - Logic is sound; implementation has issues noted above.

2. **Lines 227-308: Error resilience test**
   - `test_on_complete_called_on_error` verifies lifecycle hooks run even on exception.
   - Important behavior to test; correctly uses `pytest.raises(RuntimeError)`.

3. **Lines 311-382: Source lifecycle test**
   - `test_source_lifecycle_hooks_called` uses real `TrackedSource` (line 324) instead of mock.
   - Better pattern than other tests in this file - demonstrates the fix.

4. **Lines 385-458: Sink lifecycle test**
   - `test_sink_lifecycle_hooks_called` uses real `TrackedSink` (line 398).
   - Good pattern; verifies order: `on_start` < `write` < `on_complete`.

5. **Lines 460-548: Sink on_complete resilience**
   - `test_sink_on_complete_called_even_on_error` verifies sinks get cleanup call even when transforms fail.
   - Important for resource management.

## Verdict

**REWRITE** - The manual graph construction violates CLAUDE.md's "Test Path Integrity" policy. These tests should:
1. Use `ExecutionGraph.from_plugin_instances()` instead of manual construction
2. Use test fixtures (like `_TestSourceBase`, `_TestSinkBase`) consistently instead of MagicMock
3. Follow the pattern in `test_source_lifecycle_hooks_called` which uses real `TrackedSource`

The lifecycle hook behavior being tested is valuable, but the test implementation creates maintenance burden and may hide production bugs.
