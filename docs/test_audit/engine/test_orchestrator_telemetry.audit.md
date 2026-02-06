# Test Audit: tests/engine/test_orchestrator_telemetry.py

**Lines:** 728
**Tests:** 16
**Audit:** WARN

## Summary

This test file verifies telemetry event emission in the Orchestrator. The tests cover lifecycle events (RunStarted, RunFinished, PhaseChanged), row-level telemetry, and behavior when telemetry is disabled. The file contains one significant test path integrity violation where `create_minimal_graph()` manually constructs graphs instead of using production code paths, but this is partially mitigated by tests that do use production paths.

## Findings

### CRITICAL: Test Path Integrity Violation

**Severity: MEDIUM** (not CRITICAL because some tests do use production paths)

**Location: Lines 99-111**

```python
def create_minimal_graph() -> ExecutionGraph:
    """Create a minimal valid execution graph."""
    graph = ExecutionGraph()
    schema_config = {"schema": {"mode": "observed"}}
    graph.add_node("source", node_type=NodeType.SOURCE, plugin_name="test_source", config=schema_config)
    graph.add_node("transform", node_type=NodeType.TRANSFORM, plugin_name="passthrough", config=schema_config)
    graph.add_node("sink", node_type=NodeType.SINK, plugin_name="test_sink", config=schema_config)
    graph.add_edge("source", "transform", label="continue", mode=RoutingMode.MOVE)
    graph.add_edge("transform", "sink", label="continue", mode=RoutingMode.MOVE)
    graph._transform_id_map = {0: NodeID("transform")}
    graph._sink_id_map = {SinkName("output"): NodeID("sink")}
    graph._default_sink = "output"
    return graph
```

**Problem:** This function bypasses `ExecutionGraph.from_plugin_instances()` and manually constructs the graph, violating the CLAUDE.md "Test Path Integrity" rule. This pattern could hide bugs in the production graph construction code.

**Affected Tests (13 tests):**
- `test_run_started_emitted_after_begin_run` (line 175)
- `test_run_completed_emitted_after_finalize_run` (line 199)
- `test_phase_changed_events_emitted_for_all_phases` (line 223)
- `test_events_emitted_in_correct_order` (line 249)
- `test_no_telemetry_when_manager_not_provided` (line 273)
- `test_no_telemetry_when_manager_is_none` (line 288)
- `test_no_run_started_if_begin_run_fails` (line 314)
- `test_no_run_completed_if_finalize_fails` (line 351)
- `test_run_completed_emitted_with_failed_status` (line 385)
- `test_run_started_contains_config_hash` (line 453)
- `test_run_completed_contains_accurate_metrics` (line 472)
- `test_all_events_share_same_run_id` (line 492)
- `test_run_finished_emitted_when_export_fails` (line 670)

**Mitigating Factor:** The `TestRowCreatedTelemetry` class (lines 518-654) correctly uses `build_production_graph()`, demonstrating awareness of the proper pattern.

### MINOR: Tests Verify Code Structure by Comment, Not Execution

**Severity: LOW**

**Location: Lines 314-349, 351-380**

The tests `test_no_run_started_if_begin_run_fails` and `test_no_run_completed_if_finalize_fails` have extensive docstrings explaining what they test, but they actually just run successful paths and don't inject failures. The docstrings mention "by inspection of the code" which isn't a true test.

From line 315-327:
```python
def test_no_run_started_if_begin_run_fails(self, landscape_db: LandscapeDB, payload_store) -> None:
    """If begin_run fails, NO RunStarted telemetry event should be emitted.

    This test verifies the code structure: RunStarted is emitted AFTER
    begin_run in the Orchestrator code path. If begin_run raises an exception,
    the code path that emits RunStarted is never reached.

    We verify this by checking the code order:
    1. recorder.begin_run() is called first
    2. self._emit_telemetry(RunStarted(...)) is called after begin_run succeeds

    The test confirms that in normal operation, both happen, and by inspection
    of the code, if begin_run raises, RunStarted emission is skipped.
    """
```

These tests should inject failures to actually verify the behavior, or be removed/renamed to reflect what they actually test.

### MINOR: Mock Source Creates Contract Conditionally

**Severity: LOW**

**Location: Lines 114-149**

The `create_mock_source()` function creates contracts from the first row's keys, which works but could be fragile if rows have different keys. This is acceptable for tests where all rows have the same structure.

### Positive Observations

1. **RecordingExporter Pattern (Lines 75-96)**: Clean implementation for capturing telemetry events for verification.

2. **MockTelemetryConfig (Lines 58-72)**: Properly implements RuntimeTelemetryProtocol for testing.

3. **RowCreated Tests Use Production Paths (Lines 528-654)**: The `TestRowCreatedTelemetry` class correctly uses `build_production_graph()` from the orchestrator_test_helpers module.

4. **Comprehensive Event Coverage**: Tests cover all major telemetry events (RunStarted, RunFinished, PhaseChanged, RowCreated).

5. **Proper Granularity Testing**: Tests verify event ordering, content accuracy, and shared run_ids.

## Recommendations

### High Priority

1. **Refactor tests to use production graph construction**: Replace `create_minimal_graph()` with a pattern similar to `TestRowCreatedTelemetry` that uses `build_production_graph()`.

   Example fix for `create_mock_source()` callers:
   ```python
   # Instead of create_minimal_graph(), create a proper config and use:
   from tests.engine.orchestrator_test_helpers import build_production_graph

   config = PipelineConfig(
       source=create_mock_source([{"id": 1}]),
       transforms=[as_transform(PassthroughTransform())],
       sinks={"output": create_mock_sink()},
   )
   graph = build_production_graph(config)
   ```

### Medium Priority

2. **Fix or rename the "by inspection" tests**: Either:
   - Mock `recorder.begin_run()` to raise and verify no telemetry is emitted
   - Rename tests to reflect they only verify successful path behavior

## Verdict

**WARN** - The test file has valuable telemetry coverage but contains a significant test path integrity violation. The `create_minimal_graph()` function manually constructs execution graphs instead of using production code paths, which could allow bugs in `ExecutionGraph.from_plugin_instances()` to go undetected.

The tests that use `build_production_graph()` (in `TestRowCreatedTelemetry`) demonstrate the correct pattern exists in the codebase. Recommend refactoring the remaining tests to follow this pattern.
