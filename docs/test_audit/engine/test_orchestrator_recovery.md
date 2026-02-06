# Test Audit: test_orchestrator_recovery.py

## File Information
- **Path:** `/home/john/elspeth-rapid/tests/engine/test_orchestrator_recovery.py`
- **Lines:** 324
- **Tests:** 1
- **Audit:** WARN

## Summary

This test file verifies crash recovery via `Orchestrator.resume()`. The test correctly simulates a mid-flush crash with an incomplete batch and verifies retry behavior. However, there is a **Test Path Integrity violation**: the `_create_minimal_graph()` helper uses manual graph construction (`graph.add_node()`, direct attribute assignment) instead of the production factory.

## Test Inventory

| Test | Purpose | Production Path |
|------|---------|-----------------|
| `test_resume_retries_failed_batches` | Verifies resume retries batches that were executing when crash occurred | **NO** - uses manual graph construction |

## Findings

### Critical: Test Path Integrity Violation

**Location:** Lines 289-318 (`_create_minimal_graph`)

The helper creates an `ExecutionGraph` using manual node/edge additions and direct attribute assignment:

```python
graph = ExecutionGraph()
graph.add_node("source", node_type=NodeType.SOURCE, ...)
graph.add_node("agg_node", node_type=NodeType.AGGREGATION, ...)
graph.add_node("sink", node_type=NodeType.SINK, ...)
graph.add_edge("source", "agg_node", label="continue")
graph.add_edge("agg_node", "sink", label="continue")

# Direct attribute assignment bypasses production logic
graph._sink_id_map = {SinkName("default"): NodeID("sink")}
graph._default_sink = "default"
```

Per CLAUDE.md "Test Path Integrity" section, this pattern can hide bugs in `ExecutionGraph.from_plugin_instances()`. The comment at line 313-314 acknowledges this is manual but doesn't justify why the production path cannot be used.

**Mitigating Factor:** This is a recovery test where the graph must match node IDs from the `failed_run_with_batch` fixture (see comment at lines 306). The fixture manually constructs audit trail records with specific node IDs, and the graph must match for resume compatibility.

**Recommendation:** Either:
1. Refactor the fixture to use production graph construction first, then extract node IDs
2. Document this as an acceptable exception for recovery testing
3. Create a dedicated test that verifies `from_plugin_instances()` produces compatible graphs for resume

### Additional Observations

1. **Single Test:** Only one test for a complex feature (crash recovery with batch retry). Consider adding:
   - Recovery with no incomplete batches
   - Recovery with multiple incomplete batches
   - Recovery with aggregation state restoration
   - Recovery failure scenarios

2. **Strong Assertions (Lines 239-270):** The existing test has good assertions:
   - Original batch marked FAILED
   - Retry batch has incremented attempt number
   - Batch members preserved in retry
   - Run completed or failed appropriately

3. **Fixture Complexity (Lines 73-203):** The `failed_run_with_batch` fixture is 130 lines and manually constructs audit state. This is necessary for simulating crashes but makes the test fragile.

4. **Missing `plugin_manager` Fixture Usage:** The test receives `plugin_manager` but doesn't appear to use it (passed to `_create_minimal_graph` which doesn't use it either). This could be a remnant from refactoring.

### `mock_graph` Fixture Also Uses Manual Construction

**Location:** Lines 54-70

The `mock_graph` fixture also uses manual construction:
```python
graph = ExecutionGraph()
graph.add_node("source", ...)
graph.add_node("agg_node", ...)
graph.add_node("sink", ...)
```

This fixture is used in `failed_run_with_batch` and `test_resume_retries_failed_batches`. The same Test Path Integrity concern applies.

## Verdict

**WARN** - The test validates important recovery behavior but violates Test Path Integrity by using manual graph construction. The violation is partially justified by the need to match fixture node IDs, but this coupling suggests the test design could be improved. Additionally, coverage is limited to a single happy-path scenario.

### Recommendations

1. **P2:** Document why manual graph construction is acceptable for recovery tests, or refactor to use production paths
2. **P3:** Add additional recovery scenarios (no batches, multiple batches, failure cases)
3. **P3:** Remove unused `plugin_manager` parameter if not needed
