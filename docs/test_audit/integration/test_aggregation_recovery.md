# Test Audit: test_aggregation_recovery.py

**File:** `tests/integration/test_aggregation_recovery.py`
**Lines:** 577
**Batch:** 95

## Summary

This test file contains end-to-end integration tests for aggregation crash recovery. It simulates crash scenarios, checkpoint creation, and recovery processes.

## Findings

### 1. TEST PATH INTEGRITY VIOLATION - MANUAL GRAPH CONSTRUCTION

**Severity:** Medium - Acceptable with Caveats

**Location:** `mock_graph` fixture (lines 58-72)

```python
@pytest.fixture
def mock_graph(self) -> ExecutionGraph:
    """Create a minimal mock graph for aggregation recovery tests."""
    graph = ExecutionGraph()
    schema_config = {"schema": {"mode": "observed"}}
    agg_config = {
        "trigger": {"count": 1},
        "output_mode": "transform",
        "options": {"schema": {"mode": "observed"}},
        "schema": {"mode": "observed"},
    }
    graph.add_node("source", node_type=NodeType.SOURCE, plugin_name="test", config=schema_config)
    graph.add_node("sum_aggregator", node_type=NodeType.AGGREGATION, plugin_name="test", config=agg_config)
    graph.add_node("count_aggregator", node_type=NodeType.AGGREGATION, plugin_name="count_agg", config=agg_config)
    return graph
```

**Assessment:**

This is a borderline case. The tests are:
1. Testing checkpoint/recovery infrastructure (acceptable for manual construction)
2. Using the graph only for `can_resume()` and `get_resume_point()` validation
3. Not testing actual pipeline execution

However, unlike the contract tests, these tests interact with the full recovery system which may have different behavior depending on how the graph was constructed.

**Verdict:** Acceptable, but would be stronger with production path.

### 2. RAW SQL FOR NODE REGISTRATION

**Severity:** Low - Technical Debt

**Location:** `_register_nodes_raw` method (lines 342-408)

```python
def _register_nodes_raw(
    self,
    db: LandscapeDB,
    run_id: str,
    *,
    extra_nodes: list[tuple[str, str, NodeType]] | None = None,
) -> None:
    """Register nodes using raw SQL to avoid schema_config requirement."""
```

This helper bypasses the production node registration path (`recorder.register_node()`) to avoid schema_config requirements. While this simplifies tests, it creates a maintenance burden:

1. If the schema changes, this method must be manually updated
2. The test path diverges from production

**Recommendation:** If `recorder.register_node()` has been updated to handle schema_config differently, this raw SQL approach should be revisited.

### 3. GOOD: Comprehensive Recovery Scenarios

**Status:** Excellent

The tests cover multiple recovery scenarios:
- Full recovery cycle (crash during flush)
- Multiple aggregation nodes (independent recovery)
- Batch member order preservation
- Cannot retry non-failed batches
- Timeout preservation on resume (Bug #6)

### 4. GOOD: Bug #6 Fix Verification

**Location:** `test_timeout_preservation_on_resume` (lines 410-577)

This test verifies that aggregation timeout windows don't reset on resume - a critical SLA preservation requirement. The test:
1. Simulates 30s elapsed time
2. Creates checkpoint with elapsed time
3. Restores state
4. Verifies timeout triggers at 60s total, not 90s

### 5. MINOR: Time Mocking Approach

**Severity:** Low

**Location:** Lines 464-466, 568

```python
original_monotonic = time.monotonic()
elapsed_seconds = 30.0
evaluator._first_accept_time = original_monotonic - elapsed_seconds
```

The test manipulates internal state (`_first_accept_time`) to simulate time passage. While functional, this could break if the implementation changes. Consider using a time-mocking library like `freezegun` for more robust testing.

### 6. MISSING: Sink Node in Graph

**Severity:** Low - May Not Be Required

The `mock_graph` fixture creates source and aggregation nodes but no sink node. This may be fine for recovery testing, but could mask issues if the recovery system expects a complete graph.

## Test Path Integrity

| Test | Uses Production Path | Notes |
|------|---------------------|-------|
| All tests | NO (graph) | Uses manual `mock_graph` fixture |
| All tests | NO (nodes) | Uses raw SQL via `_register_nodes_raw` |

## Defects

None identified - tests appear functionally correct.

## Missing Coverage

1. **Medium:** No test for recovery when checkpoint is corrupted
2. **Low:** No test for recovery with pending batches (not just EXECUTING)
3. **Low:** No sink node in mock graph

## Recommendations

1. **Consider production path for one test** - Add at least one test that uses `ExecutionGraph.from_plugin_instances()` to verify recovery works with production graphs

2. **Add corrupted checkpoint test** - Per the Three-Tier Trust Model, our data (audit trail) should crash on corruption. Test that recovery handles this correctly.

3. **Refactor time mocking** - Use a proper time-mocking approach instead of manipulating internal state

4. **Add sink to mock graph** - Even if not strictly required, having a complete graph structure prevents future issues

## Overall Assessment

**Quality: Good**

The tests thoroughly cover aggregation recovery scenarios with good attention to edge cases (Bug #6). The manual graph construction is acceptable for infrastructure testing, though one production-path test would strengthen coverage.
