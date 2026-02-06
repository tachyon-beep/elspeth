# Audit: tests/system/audit_verification/test_lineage_completeness.py

## Summary
System tests verifying that every row processed through a pipeline has complete lineage available via explain queries. This directly validates ELSPETH's core principle: "I don't know what happened" is never acceptable.

**Lines:** 495
**Test Classes:** 3 (TestLineageCompleteness, TestLineageAfterRetention, TestExplainQueryFunctionality)
**Test Methods:** 5

## Verdict: PASS WITH MINOR ISSUES

These tests validate critical audit functionality but have some structural issues around manual graph construction.

---

## Detailed Analysis

### 1. Defects
**Potential issue: Manual graph construction bypasses production path**

Lines 84-122 (`_build_linear_graph`) manually constructs an ExecutionGraph:

```python
def _build_linear_graph(config: PipelineConfig) -> ExecutionGraph:
    """Build a simple linear graph for testing."""
    graph = ExecutionGraph()
    # ... manual node/edge additions ...
    graph._sink_id_map = sink_ids
    graph._transform_id_map = transform_ids
    graph._default_sink = SinkName("default")
    graph._route_resolution_map = {}
```

This accesses private attributes (`_sink_id_map`, `_transform_id_map`, etc.) and bypasses `ExecutionGraph.from_plugin_instances()`. Per CLAUDE.md "Test Path Integrity" section, this could hide bugs in the production graph construction path.

**Severity:** Medium. The tests are for lineage verification, not graph construction, but using the production path would be better.

### 2. Overmocking
**None.**

Tests use:
- Real `LandscapeDB` (in-memory or file-based SQLite)
- Real `Orchestrator`
- Real `LandscapeRecorder`
- Real `PurgeManager`
- Custom test plugins that implement actual protocols

The test plugins (`_TestSourceBase`, `_TestSinkBase`) are minimal but functional.

### 3. Missing Coverage
**Gaps identified:**

1. **No test for multi-path DAG lineage** - All tests use linear pipelines. Fork/join lineage is not tested.

2. **No test for lineage after row failure** - Tests verify successful row lineage but not quarantined/failed row lineage.

3. **No test for external call lineage** - LLM transforms record external calls; this isn't tested.

4. **No test for lineage with aggregations** - Aggregation tokens have parent/child relationships that affect lineage.

### 4. Tests That Do Nothing
**None.**

All tests have meaningful assertions that verify:
- Row counts
- Pipeline completion status
- Lineage presence and content
- Hash persistence after purge

### 5. Inefficiency
**Minor duplication:**

The pattern of creating TestSource/TestSink inner classes is repeated in every test method. This could be extracted to fixtures or module-level classes.

```python
class TestSource(_TestSourceBase):
    name = "test_source"
    output_schema = _InputSchema
    def load(self, ctx: Any) -> Any:
        yield from self.wrap_rows([...])
```

This pattern appears 5 times with minor variations.

### 6. Structural Issues
**ClassVar usage in sinks**

Lines 151 and 365:
```python
class TestSink(_TestSinkBase):
    results: ClassVar[list[dict[str, Any]]] = []
```

Using `ClassVar` for test data collection works but is fragile - state persists between tests if not explicitly cleared. The `TestSink.results.clear()` calls (lines 160, 374, 450) are necessary but easy to forget.

**Recommendation:** Use instance variables or a fixture-managed list instead.

**Private attribute access**

Lines 117-121 access private attributes of ExecutionGraph:
```python
graph._sink_id_map = sink_ids
graph._transform_id_map = transform_ids
graph._default_sink = SinkName("default")
graph._route_resolution_map = {}
```

This couples tests to implementation details.

---

## Notable Patterns (Positive)

### Real Purge Testing
`test_lineage_available_after_payload_purge` (lines 244-320) verifies a critical audit property:
- Payloads can be purged for storage reasons
- Hashes (the audit evidence) survive purge
- Lineage queries still work after purge

This is exactly what the CLAUDE.md "Hashes survive payload deletion" principle requires.

### Explain Query Validation
`test_explain_returns_source_data` (lines 326-410) verifies the fundamental audit capability:
- Given a processed row, explain() returns the original source data
- Source data is stored via PayloadStore
- Lineage includes transformation history

### Step Index Ordering
Lines 486-487 verify that node states are ordered by step_index:
```python
step_indices = [state.step_index for state in lineage.node_states]
assert step_indices == sorted(step_indices)
```

This validates that lineage reconstruction shows transforms in execution order.

---

## Recommendations

### High Priority

1. **Use production graph factory** - Replace `_build_linear_graph()` with `ExecutionGraph.from_plugin_instances()` where possible. If manual construction is needed for specific tests, document why.

2. **Add fork/join lineage test** - Create a test with:
   ```
   source -> gate -> [branch_a, branch_b] -> coalesce -> sink
   ```
   Verify lineage shows fork point, both paths, and join.

### Medium Priority

3. **Extract test plugins to conftest** - Move `_TestSourceBase`, `_TestSinkBase`, `_InputSchema`, etc. to conftest.py for reuse.

4. **Add failed row lineage test** - Verify that quarantined rows have lineage showing the failure point and error details.

5. **Replace ClassVar with fixtures** - Use pytest fixtures to provide result collection lists that are automatically cleared.

### Low Priority

6. **Add external call lineage test** - Use a mock LLM transform and verify explain() includes call details.

---

## Test Quality Score: 8/10

Tests verify critical audit functionality with real database and orchestrator. Deductions for manual graph construction (bypasses production path) and missing coverage for complex DAG scenarios.
