# Test Audit: tests/engine/test_orchestrator_resume.py

**Lines:** 1016
**Tests:** 6
**Audit:** WARN

## Summary

This file tests the Orchestrator resume functionality for recovering failed pipeline runs. The tests are comprehensive and well-structured, covering row processing, sink output, audit trail creation, and resource cleanup. However, there is a notable Test Path Integrity violation: the tests manually construct `ExecutionGraph` objects instead of using the production `from_plugin_instances()` factory method.

## Findings

### WARN: Test Path Integrity Violation - Manual Graph Construction

**Location:** Lines 254-268, 739-750, 965-976 (all fixtures)

The `failed_run_with_payloads` fixture and cleanup tests manually construct `ExecutionGraph` objects using `graph.add_node()` and direct attribute assignment:

```python
graph = ExecutionGraph()
graph.add_node("source-node", node_type=NodeType.SOURCE, plugin_name="null", config=schema_config)
graph.add_node("transform-node", node_type=NodeType.TRANSFORM, plugin_name="passthrough", config=schema_config)
graph.add_node("sink-node", node_type=NodeType.SINK, plugin_name="csv", config=schema_config)
graph.add_edge("source-node", "transform-node", label="continue", mode=RoutingMode.MOVE)
graph.add_edge("transform-node", "sink-node", label="continue", mode=RoutingMode.MOVE)

# Direct attribute assignment bypasses production logic
graph._sink_id_map = {SinkName("default"): NodeID("sink-node")}
graph._transform_id_map = {0: NodeID("transform-node")}
graph._config_gate_id_map = {}
graph._route_resolution_map = {}
graph._default_sink = "default"
```

This violates the Test Path Integrity principle from CLAUDE.md. While there is a justification in the comments ("These are required for the orchestrator to resolve nodes during execution"), the manual construction means bugs in `from_plugin_instances()` won't be caught.

**Mitigation:** The tests are specifically for the resume path, which requires matching node IDs between the database and graph. The fixture pre-populates the database with specific node IDs, which makes using `from_plugin_instances()` impractical. This is a legitimate edge case where manual construction may be necessary.

**Recommendation:** Consider refactoring to use `from_plugin_instances()` first to generate node IDs, then populate the database with those IDs, rather than the current approach.

### PASS: Good Coverage of Cleanup Behavior

**Location:** Lines 530-1016 (`TestOrchestratorResumeCleanup`)

Excellent tests for P3-2026-01-28 bug fix verifying:
- `transform.close()` is called during resume
- `close()` is called even when `on_complete()` raises

These tests use inline transform classes with tracking flags, which is appropriate for verifying callback behavior.

### PASS: Meaningful Assertions

**Location:** Lines 458-466

The tests make specific assertions about expected values:

```python
assert result.rows_processed == 2, f"Expected 2 rows_processed, got {result.rows_processed}"
assert result.rows_succeeded == 2, f"Expected 2 rows_succeeded, got {result.rows_succeeded}"
assert result.rows_failed == 0, f"Expected 0 rows_failed, got {result.rows_failed}"
```

This is explicitly called out as a "P2 Fix" for replacing vacuous `>= 0` assertions.

### PASS: Audit Trail Verification

**Location:** Lines 468-527 (`test_resume_creates_audit_trail_for_resumed_tokens`)

Good test verifying that resumed rows have proper audit trail entries (node_states and token_outcomes). This is a P1 fix ensuring audit integrity.

### INFO: Fixture Duplication

**Location:** Lines 536-562 vs 42-68

The `TestOrchestratorResumeCleanup` class duplicates several fixtures that are identical to `TestOrchestratorResumeRowProcessing`. Consider extracting to a shared fixture module or using fixture parametrization.

### INFO: Import Inside Functions

**Location:** Lines 227-228, 578-580, 719-720, etc.

Multiple inline imports inside fixture bodies:

```python
from elspeth.contracts.schema_contract import FieldContract, SchemaContract
from elspeth.core.landscape.recorder import LandscapeRecorder
```

While not a defect, these could be moved to the module level for clarity.

## Verdict

**WARN** - The tests are comprehensive and well-designed for testing resume functionality, but the manual graph construction is a deviation from the Test Path Integrity principle. However, this appears to be a legitimate edge case since resume tests need to match pre-existing database node IDs. The core behaviors (row processing, cleanup, audit trail) are properly tested with meaningful assertions.

**Recommendations:**
1. Add a comment block explaining why manual graph construction is necessary for resume tests (to match pre-populated database state)
2. Consider extracting shared fixtures to reduce duplication between the two test classes
3. Move inline imports to module level
