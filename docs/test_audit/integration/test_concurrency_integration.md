# Test Audit: test_concurrency_integration.py

**File:** `tests/integration/test_concurrency_integration.py`
**Lines:** 262
**Batch:** 98

## Summary

This file tests concurrency configuration wiring through the CLI -> Orchestrator -> RowProcessor -> TransformExecutor pipeline.

## Audit Results

### 1. Defects

**POTENTIAL ISSUE** in `test_orchestrator_run_passes_max_workers_to_processor`:

| Issue | Severity | Location |
|-------|----------|----------|
| Manual graph construction | High | Lines 188-197 |

The test manually constructs an ExecutionGraph instead of using `ExecutionGraph.from_plugin_instances()`:
```python
graph = ExecutionGraph()
schema_config = {"schema": {"mode": "observed"}}
graph.add_node("source", node_type=NodeType.SOURCE, plugin_name="test_source", config=schema_config)
graph.add_node("sink", node_type=NodeType.SINK, plugin_name="test_sink", config=schema_config)
graph.add_edge("source", "sink", label="continue", mode=RoutingMode.MOVE)
graph._sink_id_map = {SinkName("output"): NodeID("sink")}
graph._default_sink = "output"
graph._transform_id_map = {}
```

This violates Test Path Integrity per CLAUDE.md - manual construction bypasses production logic and can hide bugs.

### 2. Overmocking

| Issue | Severity | Location |
|-------|----------|----------|
| Extensive mocking of source/sink | Medium | Lines 214-244 |

The test creates elaborate MagicMock objects for source and sink. While this allows isolation, it also means the test doesn't verify that real plugins work correctly with concurrency settings.

| Issue | Severity | Location |
|-------|----------|----------|
| Patching RowProcessor.__init__ | Medium | Lines 247-255 |

Patching `__init__` to capture arguments is fragile. If the signature changes, the test might not catch the regression properly.

### 3. Missing Coverage

| Gap | Severity | Description |
|-----|----------|-------------|
| No actual concurrent execution test | High | Tests only verify config wiring, not that concurrent execution actually works |
| No thread pool size verification | Medium | Tests check max_workers is passed but not that ThreadPoolExecutor is sized correctly |
| No resume path test | Medium | Only tests run(), not resume() which also needs max_workers |

### 4. Tests That Do Nothing

**NONE** - All tests have assertions, though some are shallow.

### 5. Inefficiency

| Issue | Severity | Location |
|-------|----------|----------|
| Repeated db creation/cleanup | Low | Each test creates and closes LandscapeDB.in_memory() |

### 6. Structural Issues

| Issue | Severity | Location |
|-------|----------|----------|
| try/finally for db cleanup | Low | Could use pytest fixture with yield |

### 7. Test Path Integrity

**VIOLATION** - `test_orchestrator_run_passes_max_workers_to_processor` uses manual graph construction with `graph.add_node()` and direct attribute assignment (`graph._sink_id_map`, `graph._default_sink`, `graph._transform_id_map`).

## Verdict: NEEDS IMPROVEMENT

The tests verify config wiring but have a significant Test Path Integrity violation. The test should use `ExecutionGraph.from_plugin_instances()` with real (or properly constructed) plugin instances.

## Recommendations

1. **CRITICAL**: Refactor `test_orchestrator_run_passes_max_workers_to_processor` to use production graph construction
2. Add test that verifies actual concurrent transform execution
3. Add test for resume() path
4. Consider using pytest fixtures for db lifecycle
5. Add test that verifies ThreadPoolExecutor is actually created with correct size
