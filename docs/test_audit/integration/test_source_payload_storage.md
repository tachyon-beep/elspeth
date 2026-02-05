# Test Audit: test_source_payload_storage.py

**File:** `/home/john/elspeth-rapid/tests/integration/test_source_payload_storage.py`
**Lines:** 187
**Batch:** 107

## Overview

Integration test for P0 bug: Source row payloads never persisted. Verifies that source row payloads are stored in PayloadStore during pipeline runs per CLAUDE.md's audit requirement.

## Audit Findings

### 1. DEFECT: Test Path Integrity Violation - Manual Graph Construction

**Severity:** High
**Location:** Lines 41-63 (`_build_simple_graph`)

The test manually constructs the execution graph:

```python
def _build_simple_graph(config: PipelineConfig) -> ExecutionGraph:
    """Build minimal graph: source -> sink."""
    graph = ExecutionGraph()
    schema_config = {"schema": {"mode": "observed"}}
    graph.add_node("source", node_type=NodeType.SOURCE, plugin_name=config.source.name, config=schema_config)
    # ...
    graph._sink_id_map = sink_ids
    graph._transform_id_map = {}
    graph._default_sink = next(iter(config.sinks.keys()))
    return graph
```

This directly accesses private attributes (`_sink_id_map`, `_transform_id_map`, `_default_sink`) and bypasses production validation.

**Impact:** Bugs in production graph construction would not be caught by this test.

**Recommendation:** Use `build_production_graph()` from `orchestrator_test_helpers.py`.

---

### 2. DEFECT: Unused Fixture Parameter

**Severity:** Medium
**Location:** Line 66

```python
def test_source_row_payloads_are_stored_during_run(tmp_path: Path, payload_store) -> None:
```

The `payload_store` fixture is passed but immediately overwritten:

```python
payload_path = tmp_path / "payloads"
payload_path.mkdir()
# ...
payload_store = FilesystemPayloadStore(payload_path)  # Shadows the fixture!
```

This is a bug - either the fixture should be used, or the parameter should be removed.

---

### 3. DEFECT: Potential Test Failure Due to API Mismatch

**Severity:** High
**Location:** Lines 142-146

The test passes `payload_store=payload_store` to `orchestrator.run()`:

```python
result = orchestrator.run(
    config,
    graph=graph,
    payload_store=payload_store,  # This parameter doesn't exist yet!
)
```

The comment explicitly says "This parameter doesn't exist yet!" - this suggests the test was written before the implementation and may fail if the API doesn't match.

**Verification needed:** Check if `orchestrator.run()` accepts a `payload_store` parameter.

---

### 4. MISSING COVERAGE: No Test for Payload Retrieval After Purge

**Severity:** Low

The test verifies payloads are stored, but doesn't test the retention/purge cycle. This would be valuable for verifying the retention policy integration.

---

### 5. MISSING COVERAGE: Error Scenarios

**Severity:** Medium

No tests for:
- PayloadStore write failures
- Disk full scenarios during payload storage
- Corrupted payload retrieval

---

### 6. POSITIVE: Good Assertion Messages

The test includes detailed assertion messages:

```python
assert row.source_data_ref is not None, (
    f"Row {row.row_id} source_data_ref should be set, but is NULL. "
    "This violates CLAUDE.md's non-negotiable audit requirement: "
    "'Source entry - Raw data stored before any processing'"
)
```

This provides excellent context for failures.

---

### 7. STRUCTURAL: Database Cleanup

**Severity:** Low
**Location:** Line 187

```python
db.close()
```

Manual database close at end of test. Should use `try/finally` or pytest fixture for cleanup to ensure database is closed even if test fails.

---

## Summary

| Category | Count | Severity |
|----------|-------|----------|
| Defects | 3 | High, High, Medium |
| Missing Coverage | 2 | Low, Medium |
| Structural Issues | 1 | Low |
| Positive Findings | 1 | N/A |
| Test Path Violations | 1 | High |

## Recommendations

1. **CRITICAL:** Replace manual graph construction with `build_production_graph()`
2. **CRITICAL:** Fix the unused/shadowed `payload_store` fixture parameter
3. **CRITICAL:** Verify `orchestrator.run()` API accepts `payload_store` parameter
4. **MEDIUM:** Add error scenario tests for payload storage failures
5. **LOW:** Use fixture or context manager for database cleanup

## Overall Assessment

This test file has significant issues that may cause false positives or failures. The manual graph construction, shadowed fixture, and potentially mismatched API all need attention. The core assertion logic is good, but the test infrastructure is problematic.
