# Test Audit: tests/engine/test_orchestrator_cleanup.py

## Metadata
- **Lines:** 276
- **Tests:** 4 (in 1 test class)
- **Audit:** PASS

## Summary

Tests for transform/gate cleanup in orchestrator - verifying that `close()` is called on all plugins on success and failure, handles default implementations, and continues cleanup even when one plugin's close() fails. All tests properly use `ExecutionGraph.from_plugin_instances()` for production code path coverage.

## Findings

### Production Code Path (PASS)

All tests correctly use the production graph construction method:

```python
graph = ExecutionGraph.from_plugin_instances(
    source=as_source(source),
    transforms=[as_transform(transform_1), as_transform(transform_2)],
    sinks={"default": as_sink(sink)},
    aggregations={},
    gates=[],
    default_sink="default",
)
```

This follows the test path integrity principle documented in CLAUDE.md.

### Well-Structured Test Classes

Module-level test helpers are defined once and reused:
- `ValueSchema` (line 19)
- `ListSource` (line 25)
- `FailingSource` (line 48)
- `CollectSink` (line 57)
- `TrackingTransform` (line 84)
- `FailingCloseTransform` (line 110)

### Comprehensive Coverage

1. **test_transforms_closed_on_success**: Verifies close() called on all transforms after successful run
2. **test_transforms_closed_on_failure**: Verifies close() called even when source fails
3. **test_cleanup_handles_missing_close_method**: Verifies default no-op close() works
4. **test_cleanup_continues_if_one_close_fails**: Verifies best-effort cleanup - all plugins attempted before error raised

### Clear Error Expectation

The cleanup failure test correctly expects the error to be raised (not swallowed):

```python
with pytest.raises(RuntimeError, match="Plugin cleanup failed"):
    orchestrator.run(config, graph=graph, payload_store=payload_store)

# Both close() methods should have been called
assert transform_1.close_called, "failing transform's close() was not called"
assert transform_2.close_called, "second transform's close() was not called despite first failing"
```

This aligns with CLAUDE.md's principle that plugins are system code and bugs should crash.

### Helpful Comments

Test includes P2 Fix comments explaining the rationale:
```python
# P2 Fix: Use from_plugin_instances instead of private field mutation
```

## Verdict

**PASS** - Well-structured test file with proper production code path usage, good test coverage, and clear organization. No issues found.
