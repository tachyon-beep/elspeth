# Audit: tests/engine/test_orchestrator_lifecycle.py

**Lines:** 549
**Tests:** 7
**Audit:** CRITICAL

## Summary

This test file validates that plugin lifecycle hooks (on_start, on_complete, close) are called at the correct times by the Orchestrator. While the tests correctly verify lifecycle ordering, they **violate the Test Path Integrity principle** by manually constructing ExecutionGraph with `graph.add_node()` and direct attribute assignment instead of using `ExecutionGraph.from_plugin_instances()`.

## Findings

### Critical Issues

1. **Manual Graph Construction (CRITICAL - lines 122-131, 207-216, 291-300, 364-371, 441-448, 531-540):** All tests manually construct ExecutionGraph using:
   ```python
   graph = ExecutionGraph()
   graph.add_node("source", node_type=NodeType.SOURCE, ...)
   graph.add_node("transform", node_type=NodeType.TRANSFORM, ...)
   graph.add_node("sink", node_type=NodeType.SINK, ...)
   graph.add_edge("source", "transform", ...)
   graph._transform_id_map = {0: NodeID("transform")}
   graph._sink_id_map = {SinkName("output"): NodeID("sink")}
   graph._default_sink = "output"
   ```

   - **Impact:** High - tests bypass production graph construction logic
   - **Evidence from CLAUDE.md:** "BUG-LINEAGE-01 hid for weeks because tests manually built graphs"
   - **Risk:** Bugs in `ExecutionGraph.from_plugin_instances()` will not be caught
   - **Recommendation:** Refactor to use `build_production_graph()` or `ExecutionGraph.from_plugin_instances()`

2. **Direct Private Attribute Assignment (CRITICAL - lines 129-131, 214-216, etc.):**
   ```python
   graph._transform_id_map = {0: NodeID("transform")}
   graph._sink_id_map = {SinkName("output"): NodeID("sink")}
   graph._default_sink = "output"
   ```

   - **Impact:** High - directly manipulates internal state, bypasses validation
   - **Risk:** If internal representation changes, tests pass but production breaks
   - **Recommendation:** Use public API methods or factory functions

### Additional Issues

3. **Mock Source with Partial Protocol (WARN - lines 89-101, 175-187, 260-272, etc.):** Sources are created as MagicMocks with manual attribute assignment:
   ```python
   mock_source = MagicMock()
   mock_source.name = "csv"
   mock_source._on_validation_failure = "discard"
   mock_source.determinism = Determinism.IO_READ
   mock_source.load.return_value = iter([...])
   ```

   - **Impact:** Medium - mock may not match real source behavior
   - **Note:** Some tests use real source classes (e.g., `TrackedSource`), which is better

4. **Type Ignore Comments (INFO - lines 369, 446):**
   ```python
   graph._transform_id_map = {}  # type: ignore[assignment]
   ```

   - **Impact:** Low - indicates type system disagrees with manual construction

### Positive Aspects

1. **Correct Lifecycle Verification (lines 136-138, 222-225, 304-308, 377-382, 454-458):** Tests correctly verify lifecycle hook ordering:
   - `on_start` called before processing
   - `on_complete` called after all rows
   - `on_complete` called even on error
   - Source/sink lifecycle hooks in correct order

2. **Real Transform Classes (lines 71-85, 154-171, 240-256, 324-342, 398-414, 473-504):** Transform classes inherit from `BaseTransform` and implement real behavior, not just mocks.

3. **Error Path Coverage (lines 227-308, 460-548):** Tests verify `on_complete` is called even when transforms raise exceptions.

## Test Class Discovery

- `TestLifecycleHooks`: Properly named - will be discovered
- `TestSourceLifecycleHooks`: Properly named - will be discovered
- `TestSinkLifecycleHooks`: Properly named - will be discovered

## Required Remediation

All tests in this file need to be refactored to use production graph construction:

```python
# BEFORE (current - violates Test Path Integrity):
graph = ExecutionGraph()
graph.add_node("source", node_type=NodeType.SOURCE, ...)
graph.add_node("transform", node_type=NodeType.TRANSFORM, ...)
graph._transform_id_map = {0: NodeID("transform")}
...

# AFTER (correct - uses production code path):
from tests.engine.orchestrator_test_helpers import build_production_graph

config = PipelineConfig(
    source=as_source(source),
    transforms=[as_transform(transform)],
    sinks={"output": as_sink(sink)},
)
graph = build_production_graph(config)
```

## Verdict

**CRITICAL** - All 7 tests manually construct ExecutionGraph bypassing `from_plugin_instances()`, violating the Test Path Integrity principle documented in CLAUDE.md. This is exactly the pattern that allowed BUG-LINEAGE-01 to hide. While lifecycle hook ordering is correctly verified, the manual graph construction could mask bugs in production graph building. Recommend immediate refactoring to use `build_production_graph()` helper.
