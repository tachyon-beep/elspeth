# Test Audit: test_sink_durability.py

**File:** `/home/john/elspeth-rapid/tests/integration/test_sink_durability.py`
**Lines:** 424
**Batch:** 107

## Overview

Tests sink durability guarantees and checkpoint ordering, specifically verifying Bug #2 and Bug #10 fixes related to checkpoint creation timing with respect to sink flush() operations.

## Audit Findings

### 1. DEFECT: Test Path Integrity Violation - Manual Graph Construction

**Severity:** Medium
**Location:** Lines 104-110 (mock_graph fixture)

The test uses manual `graph.add_node()` calls instead of the production path:

```python
@pytest.fixture
def mock_graph(self) -> ExecutionGraph:
    """Create a minimal mock graph."""
    graph = ExecutionGraph()
    schema_config = {"schema": {"mode": "observed"}}
    graph.add_node("source", node_type=NodeType.SOURCE, plugin_name="test", config=schema_config)
    graph.add_node("sink", node_type=NodeType.SINK, plugin_name="csv", config=schema_config)
    return graph
```

This violates CLAUDE.md's Test Path Integrity requirement:
> Tests must use production code paths like `ExecutionGraph.from_plugin_instances()`

**Impact:** Graph construction bugs could be missed. Manual construction bypasses validation logic.

**Recommendation:** Use `build_production_graph()` or `ExecutionGraph.from_plugin_instances()`.

---

### 2. DEFECT: Incorrect Exception Type in Test

**Severity:** Low
**Location:** Lines 215-224

```python
with pytest.raises(IOError, match="Disk full"):
    sink_executor.write(...)
```

The mock sets `OSError` but the test expects `IOError`:
```python
mock_sink.flush.side_effect = OSError("Disk full - simulated crash")
```

While `IOError` is an alias for `OSError` in Python 3, this is technically imprecise. The test passes because of this aliasing, but the code is misleading.

**Recommendation:** Use consistent exception type (`OSError`).

---

### 3. MISSING COVERAGE: No Test for Partial Batch Write Failure

**Severity:** Medium

The tests cover:
- flush() failure (checkpoint not created)
- checkpoint failure after flush (logged, not raised)
- Ordering verification (flush before checkpoint)

Missing:
- Partial batch write failure (write() fails partway through multiple tokens)
- Multiple tokens with interleaved failure scenarios
- Checkpoint callback throwing different exception types

---

### 4. OVERMOCKING: Mock Sink Instead of Real CSVSink

**Severity:** Low
**Location:** Lines 113-135

The mock sink simulates behavior but doesn't verify actual sink contract compliance:

```python
@pytest.fixture
def mock_sink(self, tmp_path: Path) -> Mock:
    sink = Mock()
    sink.name = "csv"
    # ... manual mock setup
```

This is acceptable for testing executor logic, but should be complemented by tests using real sinks.

---

### 5. STRUCTURAL: Raw SQL for Node Registration

**Severity:** Low
**Location:** Lines 46-85 (`_register_nodes_raw`)

Uses raw SQL to insert nodes, bypassing the LandscapeRecorder API:

```python
def _register_nodes_raw(self, db: LandscapeDB, run_id: str) -> None:
    conn.execute(nodes_table.insert().values(...))
```

This is intentional (to avoid schema_config requirement) but creates maintenance burden if schema changes.

---

### 6. POSITIVE: Good Test Coverage for Bug Scenarios

The tests clearly document the bug scenarios being tested:
- Bug #2: Checkpoint not created if flush fails
- Bug #10: Checkpoint failure logged but not raised after durable flush

Clear assertions verify the expected behaviors.

---

## Summary

| Category | Count | Severity |
|----------|-------|----------|
| Defects | 2 | Medium, Low |
| Missing Coverage | 1 | Medium |
| Overmocking | 1 | Low |
| Structural Issues | 1 | Low |
| Test Path Violations | 1 | Medium |

## Recommendations

1. **HIGH:** Replace manual graph construction with production path
2. **MEDIUM:** Add tests for partial batch failure scenarios
3. **LOW:** Use consistent exception types
4. **LOW:** Consider adding a test with real CSVSink for end-to-end verification
