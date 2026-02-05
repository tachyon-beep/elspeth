# Audit: tests/system/recovery/test_crash_recovery.py

## Summary
System tests for crash recovery and resume scenarios. These tests verify that ELSPETH can recover from crashes and resume processing, producing the same results as uninterrupted runs.

**Lines:** 1029
**Test Classes:** 5 (TestResumeIdempotence, TestRetryBehavior, TestCheckpointRecovery, TestAggregationRecovery, _FailOnceTransform)
**Test Methods:** 7
**Fixtures:** test_env, mock_graph

## Verdict: PASS WITH ISSUES

The tests verify critical recovery functionality but have significant complexity and some structural problems.

---

## Detailed Analysis

### 1. Defects
**Issue: _FailOnceTransform has no explicit reset between tests**

Lines 40-79 define `_FailOnceTransform` with class variables:
```python
_attempt_count: ClassVar[dict[str, int]] = {}
_fail_row_ids: ClassVar[set[str]] = set()
```

The `reset()` method exists but isn't called in a fixture. If tests run in parallel or non-deterministic order, state could leak between tests.

**Severity:** Low (tests likely run sequentially), but should be fixed.

**Issue: Manual graph construction**

Same issue as `test_lineage_completeness.py` - Lines 82-112 manually construct graphs with private attribute access:
```python
graph._sink_id_map = sink_ids
graph._transform_id_map = transform_ids
graph._default_sink = SinkName("default")
graph._route_resolution_map = {}
```

### 2. Overmocking
**Partial concern: mock_graph fixture**

Lines 601-607 and 900-912 create minimal mock graphs:
```python
@pytest.fixture
def mock_graph(self) -> ExecutionGraph:
    """Create a minimal mock graph for checkpoint recovery tests."""
    graph = ExecutionGraph()
    graph.add_node("source", ...)
    graph.add_node("transform", ...)
    return graph
```

These graphs lack edges and proper sink nodes, so they don't represent real pipeline structures. For checkpoint/recovery tests, this may be acceptable since the focus is on checkpoint mechanics, not graph traversal.

### 3. Missing Coverage
**Gaps identified:**

1. **No test for resume with changed config** - What happens if config changes between crash and resume?

2. **No test for multiple checkpoint versions** - Only tests latest checkpoint, not checkpoint history.

3. **No test for corrupted checkpoint recovery** - What if checkpoint data is malformed?

4. **No test for partial aggregation flush on resume** - Aggregation recovery test stores state but doesn't test the flush behavior.

5. **No test for concurrent resume attempts** - What if two processes try to resume the same run?

### 4. Tests That Do Nothing
**None - all tests have meaningful assertions.**

`test_resume_produces_same_result` (lines 118-454) has comprehensive assertions:
- Verifies baseline run completes
- Verifies can_resume returns True
- Verifies resumed run produces correct row count
- Verifies combined output matches baseline

### 5. Inefficiency
**Major complexity: test_resume_produces_same_result**

This test is 336 lines long (lines 118-454) and does extensive manual setup:
- Creates databases
- Manually inserts run records
- Manually inserts node records
- Manually inserts row and token records
- Creates checkpoints
- Marks run as failed
- Creates new plugins for resume
- Runs resume

This is almost integration test complexity. Consider breaking into:
1. A fixture that creates a "crashed" run state
2. A simpler test that just calls resume and verifies output

**Duplication: Inner class definitions**

The pattern of defining `ListSource`, `DoublerTransform`, `CollectSink` as inner classes is repeated. These could be module-level or in conftest.py.

### 6. Structural Issues
**Good: Fixture-based test environment**

Lines 583-598 and 879-897 define `test_env` fixtures that provide:
- Database
- CheckpointManager
- RecoveryManager
- LandscapeRecorder

This is good practice for isolating test setup.

**Issue: Direct SQL in tests**

Lines 636-713 and 768-829 use raw SQL to insert test data:
```python
conn.execute(
    runs_table.insert().values(
        run_id=run_id,
        started_at=now,
        config_hash="test",
        ...
    )
)
```

While this gives precise control over test data, it bypasses the `LandscapeRecorder` API. If the schema changes, these tests will break even if the API handles the change correctly.

**Issue: pytest.mark.stress not applied**

The recovery tests would benefit from a `pytest.mark.system` or similar marker to categorize them as slower integration tests.

---

## Notable Patterns (Positive)

### Idempotence Testing
`test_resume_produces_same_result` (lines 118-454) implements a proper idempotence test:
1. Run pipeline completely (baseline)
2. Run pipeline, checkpoint, crash, resume
3. Assert: baseline output == crashed_output + resumed_output

This is exactly the pattern needed to verify recovery correctness.

### Checkpoint Persistence Testing
`test_checkpoint_across_process_restart` (lines 738-873) simulates process restart:
1. Create checkpoint in database
2. Close database connection
3. Reopen database (new connection)
4. Verify checkpoint data is intact

This validates that checkpoints survive process boundaries.

### Aggregation State Recovery
`test_aggregation_state_recovers` (lines 914-1029) verifies that:
- Aggregation buffer contents are preserved
- Aggregation counters (count, sum) are preserved
- Resume point includes full aggregation state

This is critical for aggregations that may hold unbounded state.

---

## Recommendations

### High Priority

1. **Add _FailOnceTransform reset fixture**:
   ```python
   @pytest.fixture(autouse=True)
   def reset_fail_once_transform():
       _FailOnceTransform.reset()
       yield
       _FailOnceTransform.reset()
   ```

2. **Split test_resume_produces_same_result** - Extract the "crashed run setup" into a fixture to make the test more readable.

3. **Use LandscapeRecorder API instead of raw SQL** - Replace direct SQL inserts with recorder methods where possible. This makes tests more resilient to schema changes.

### Medium Priority

4. **Add config change recovery test** - Verify behavior when:
   - Config is identical (should resume)
   - Config is changed (should refuse or warn)
   - Graph topology changed (should refuse)

5. **Add corrupted checkpoint test** - Verify graceful failure when checkpoint data is corrupted.

6. **Use production graph factory** - Replace `_build_linear_graph()` and `mock_graph` fixtures with `ExecutionGraph.from_plugin_instances()` where feasible.

### Low Priority

7. **Add test markers** - Add `@pytest.mark.slow` or `@pytest.mark.integration` to these tests.

8. **Extract common test plugins** - Move `ListSource`, `DoublerTransform`, `CollectSink` to conftest.py.

---

## Test Quality Score: 7/10

Tests verify critical recovery functionality with good patterns (idempotence testing, persistence verification). Significant deductions for:
- Extremely long test methods
- Raw SQL instead of API calls
- Manual graph construction
- Missing edge case coverage (config changes, corruption)
