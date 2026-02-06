# Test Audit: tests/integration/test_checkpoint_recovery.py

**Auditor:** Claude
**Date:** 2026-02-05
**Lines:** 741
**Batch:** 96

## Summary

This file contains integration tests for checkpoint and recovery functionality. It verifies checkpoint creation, recovery after simulated crashes, aggregation state preservation, and topology hash atomicity. This is critical for ELSPETH's crash recovery guarantees.

## Findings

### 1. TEST PATH INTEGRITY VIOLATION: Manual Graph Construction

Multiple fixtures and tests use `graph.add_node()` directly instead of `ExecutionGraph.from_plugin_instances()`:

**Lines 50-54 (`mock_graph` fixture):**
```python
def mock_graph(self) -> ExecutionGraph:
    """Create a minimal mock graph for checkpoint/recovery tests."""
    graph = ExecutionGraph()
    graph.add_node("node-001", node_type=NodeType.TRANSFORM, plugin_name="test", config={"schema": {"mode": "observed"}})
    return graph
```

**Lines 347-351 and 408-410:**
```python
graph = ExecutionGraph()
graph.add_node("source", node_type=NodeType.SOURCE, plugin_name="test", config={...})
graph.add_node("transform_a", node_type=NodeType.TRANSFORM, plugin_name="test", config={...})
```

**Lines 551-557 (`simple_graph` fixture):**
```python
def simple_graph(self) -> ExecutionGraph:
    graph = ExecutionGraph()
    schema_config = {"schema": {"mode": "observed"}}
    graph.add_node("source", node_type=NodeType.SOURCE, plugin_name="test_source", config=schema_config)
    graph.add_node("sink", node_type=NodeType.SINK, plugin_name="csv", config=schema_config)
    graph.add_edge("source", "sink", label="continue")
    return graph
```

**Lines 682-686:**
```python
graph = ExecutionGraph()
graph.add_node("source", node_type=NodeType.SOURCE, plugin_name="test", config={...})
graph.add_node("transform", node_type=NodeType.TRANSFORM, plugin_name="test", config={...})
graph.add_edge("source", "transform", label="continue")
```

**Severity:** MEDIUM
**Impact:** These tests verify checkpoint/recovery logic, not DAG construction. However, if `from_plugin_instances()` has different behavior than `add_node()` (e.g., validation, edge creation), bugs could hide.

**Recommendation:** For tests that focus on checkpoint state (not DAG structure), manual construction may be acceptable. However, consider adding at least one test that uses production graph construction to verify end-to-end behavior.

### 2. STRENGTH: Tests Bug Fixes Explicitly

The test file explicitly documents and tests bug fixes:
- Bug #1: Topology hash race condition (lines 316-424)
- Bug #8: Resume checkpoint cleanup (lines 528-643)
- Bug #9: Early validation fixes (lines 425-525)
- Bug: incompatible-checkpoint-error-propagates (lines 646-741)

**Verdict:** Excellent practice for regression prevention.

### 3. POTENTIAL ISSUE: Direct Database Manipulation

The `_setup_partial_run()` helper (lines 210-310) uses raw SQL inserts:
```python
conn.execute(
    runs_table.insert().values(
        run_id=run_id,
        started_at=now,
        ...
    )
)
```

This bypasses the `LandscapeRecorder` API, which could:
- Create invalid states if schema changes
- Miss validation that recorder provides
- Create states that couldn't exist in production

**Severity:** MEDIUM
**Recommendation:** Consider using `LandscapeRecorder` methods where possible. The direct inserts are acceptable for setting up specific checkpoint recovery scenarios that can't be created through normal APIs.

### 4. STRENGTH: Comprehensive Recovery Scenarios

The tests cover important recovery scenarios:
- Full checkpoint/recovery cycle (lines 56-81)
- Checkpoint sequence ordering (lines 82-118)
- Aggregation state preservation (lines 120-150)
- Checkpoint cleanup after completion (lines 152-169)
- Recovery respects checkpoint boundary (lines 171-188)
- Multiple runs with independent checkpoints (lines 189-208)

### 5. MINOR: Hardcoded Token/Node IDs

Lines 92-104 use hardcoded token IDs that depend on `_setup_partial_run()`:
```python
checkpoint_mgr.create_checkpoint(
    run_id=run_id,
    token_id="tok-001-003",  # Depends on _setup_partial_run creating this
    node_id="node-001",
    sequence_number=3,
    graph=mock_graph,
)
```

This coupling between tests and helper is fragile.

**Severity:** Low
**Recommendation:** Consider having `_setup_partial_run()` return the created token IDs.

### 6. STRENGTH: Tests Error Handling Contract

`TestCanResumeErrorHandling` (lines 646-741) explicitly tests that `can_resume()` returns a `ResumeCheck` object instead of raising exceptions. This verifies the API contract.

### 7. NO CLASS DISCOVERY ISSUES

All test classes have the `Test` prefix:
- `TestCheckpointRecoveryIntegration`
- `TestCheckpointTopologyHashAtomicity`
- `TestResumeCheckpointCleanup`
- `TestCanResumeErrorHandling`

## Overall Assessment

**Quality:** GOOD with minor concerns

The tests are comprehensive and explicitly verify bug fixes. However:
- Manual graph construction could hide production path bugs
- Direct database manipulation could create unrealistic states

These are acceptable trade-offs for unit-testing checkpoint logic, but the file should include at least one end-to-end test using production APIs.

## Recommendations

1. **HIGH:** Add one integration test that uses `ExecutionGraph.from_plugin_instances()` with real plugin instances to verify full production path
2. **MEDIUM:** Consider refactoring `_setup_partial_run()` to use `LandscapeRecorder` where possible
3. **LOW:** Have `_setup_partial_run()` return created IDs to reduce coupling
4. **LOW:** Add docstring to `_setup_partial_run()` explaining the exact state it creates

## Action Items

- [ ] Consider adding production-path test for checkpoint recovery
- [ ] Review if direct SQL manipulation could create impossible states
- [ ] Document the intentional test path deviation with inline comment
