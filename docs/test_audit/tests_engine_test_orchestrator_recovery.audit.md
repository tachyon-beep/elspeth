# Test Audit: tests/engine/test_orchestrator_recovery.py

**Lines:** 324
**Test count:** 1
**Audit status:** ISSUES_FOUND

## Summary

This file contains tests for orchestrator crash recovery via the resume() method. The file has extensive fixture setup (200+ lines) for a single test. The test itself verifies batch retry behavior after simulated crash, but the fixture-heavy approach and manual graph construction patterns raise concerns.

## Findings

### 🔴 Critical

1. **Lines 289-317: Manual graph construction bypasses production path**
   - `_create_minimal_graph()` manually calls `graph.add_node()`, `graph.add_edge()`.
   - Directly sets internal state: `graph._sink_id_map`, `graph._default_sink`.
   - Per CLAUDE.md "Test Path Integrity": "Manual graph.add_node() / graph._field = value bypasses validation".
   - This test could pass while production graph construction is broken.

### 🟡 Warning

1. **Lines 73-203: Extremely large fixture (130+ lines)**
   - `failed_run_with_batch` fixture performs extensive database setup.
   - Creates run, registers 3 nodes, registers 2 edges, creates 3 rows, 3 tokens, 1 batch, 3 batch members, 1 checkpoint.
   - This is essentially a mini integration test within a fixture.
   - Makes it hard to understand what specific state the test is actually verifying.

2. **Lines 54-70: Duplicate graph construction**
   - `mock_graph` fixture manually constructs a graph.
   - Same graph structure is then created again in `_create_minimal_graph()`.
   - Both use manual construction instead of `from_plugin_instances()`.

3. **Lines 205-270: Single test for complex feature**
   - Only one test (`test_resume_retries_failed_batches`) for the entire recovery feature.
   - Missing coverage for:
     - Resume with no incomplete batches
     - Resume with multiple incomplete batches
     - Resume with checkpoint at different nodes
     - Resume failure handling
     - Resume with missing/corrupted checkpoint

4. **Lines 263-267: Weak final status assertion**
   - Asserts `run.status in (RunStatus.COMPLETED, RunStatus.FAILED)`.
   - This accepts both success and failure - doesn't verify recovery actually worked.
   - Should assert `RunStatus.COMPLETED` if testing successful recovery.

5. **Lines 272-287: Config creation doesn't match fixture graph**
   - `_create_minimal_config()` creates real NullSource and JSONSink plugins.
   - But graph has node IDs "source", "agg_node", "sink" from fixture.
   - Potential mismatch between config plugins and graph nodes.

### 🔵 Info

1. **Lines 27-70: Good fixture organization**
   - Fixtures properly separated for db, checkpoint_manager, recovery_manager, orchestrator, payload_store.
   - Uses `tmp_path` for filesystem isolation.

2. **Lines 245-260: Good batch retry verification**
   - Test verifies attempt number incremented.
   - Test verifies batch members preserved in retry.
   - These are important invariants for recovery.

## Verdict

**REWRITE** - The critical issue is manual graph construction bypassing production paths. The single test provides inadequate coverage for crash recovery, which is a critical feature. The 130-line fixture makes the test hard to understand and maintain. Recommended:
1. Use `ExecutionGraph.from_plugin_instances()` or proper test helpers
2. Split the fixture into smaller, focused fixtures
3. Add tests for recovery edge cases
4. Strengthen the final status assertion to verify recovery success
