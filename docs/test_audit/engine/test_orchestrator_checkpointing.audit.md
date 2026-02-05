# Test Audit: tests/engine/test_orchestrator_checkpointing.py

## Metadata
- **Lines:** 718
- **Tests:** 8 (in 1 test class)
- **Audit:** WARN

## Summary

Tests for orchestrator checkpointing functionality - covering checkpoint creation on every row, interval-based checkpointing, checkpoint deletion on success/preservation on failure, and disabled checkpointing scenarios. Most tests properly use the production graph building helper (`build_production_graph`), except one test that manually constructs a graph for routing scenarios.

## Findings

### Test Path Integrity Violation (WARN)

**test_checkpoint_preserved_on_failure (lines 358-540)**

This test manually constructs an ExecutionGraph instead of using `build_production_graph`:

```python
graph = ExecutionGraph()
graph.add_node("source", node_type=NodeType.SOURCE, ...)
graph.add_node("transform_0", node_type=NodeType.TRANSFORM, ...)
# ... more manual construction
graph._sink_id_map = {...}  # Direct private attribute assignment
graph._transform_id_map = {...}
graph._config_gate_id_map = {...}
graph._route_resolution_map = {...}
graph._default_sink = "good"
```

This violates the test path integrity principle documented in CLAUDE.md. While the routing scenario may be complex, manual graph construction risks testing a different code path than production. The `build_production_graph` helper should be extended to support gates/routing if needed.

### Code Duplication (LOW)

Tests contain significant boilerplate with repeated definitions of:
- `ValueSchema` (defined 7 times)
- `ListSource` (defined 6 times)
- `IdentityTransform` (defined 4 times)
- `CollectSink` (defined 6 times)

These could be extracted to module-level or fixture scope to reduce ~300 lines of repetition.

### Positive Patterns

1. **P2 Fix annotations**: Several tests include tracking of checkpoint calls with clear comments explaining the fix (lines 86, 166, 184, etc.)

2. **Production graph helper usage**: 6 of 8 tests properly use `build_production_graph(config)` which exercises the production code path.

3. **Module-scoped DB fixture**: Uses `scope="module"` for the database fixture to improve performance across tests.

4. **Comprehensive coverage**: Tests cover all checkpoint frequencies (every_row, every_n) and edge cases (disabled, no manager, success/failure scenarios).

### Minor Issues

1. **Conditional assertion in test_checkpoint_preserved_on_failure (line 535-540)**: The test has a conditional that accepts either behavior depending on sink ordering:
   ```python
   if len(good_sink.results) > 0:
       assert len(remaining_checkpoints) == len(good_sink.results), ...
   # If good sink didn't write (bad sink failed first), that's also valid behavior
   ```
   This makes the test less deterministic - it accepts multiple outcomes rather than ensuring a specific behavior.

## Verdict

**WARN** - The test file is generally well-structured and uses production code paths for most tests. However, `test_checkpoint_preserved_on_failure` manually constructs the execution graph, violating the test path integrity principle. This should be refactored to use the production graph construction path. The code duplication is a lower priority but would improve maintainability.

**Recommendations:**
1. Extend `build_production_graph` to handle gate routing scenarios
2. Refactor `test_checkpoint_preserved_on_failure` to use production graph construction
3. Extract common test classes (ValueSchema, ListSource, CollectSink, IdentityTransform) to conftest or module level
4. Consider making the sink ordering deterministic in the failure test
