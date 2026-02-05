# Test Audit: tests/integration/test_resume_comprehensive.py

**Auditor:** Claude Code
**Date:** 2026-02-05
**Batch:** 104
**Lines:** 1422

## Summary

This is a comprehensive integration test file for resume functionality with 8 tests covering various resume scenarios. The tests are well-documented and test important edge cases. However, there are several **critical issues** that need attention.

## Findings

### 1. CRITICAL: Test Path Integrity Violation - Manual Graph Construction

**Severity:** HIGH
**Location:** All tests (lines 123-130, 317-326, 424-433, 507-513, 628-637, 711-717, 832-841, 911-917, 1033-1042, 1111-1117, 1233-1242, 1301-1307, 1404-1413)

All tests manually construct `ExecutionGraph` using `graph.add_node()` and direct attribute assignment instead of using the production factory method `ExecutionGraph.from_plugin_instances()`.

**Example from line 317-326:**
```python
# Build graph manually
resume_graph = ExecutionGraph()
schema_config = {"schema": strict_schema}
resume_graph.add_node("src", node_type=NodeType.SOURCE, plugin_name="null", config=schema_config)
resume_graph.add_node("xform", node_type=NodeType.TRANSFORM, plugin_name="passthrough", config=schema_config)
resume_graph.add_node("sink", node_type=NodeType.SINK, plugin_name="csv", config=schema_config)
resume_graph.add_edge("src", "xform", label="continue")
resume_graph.add_edge("xform", "sink", label="continue")
resume_graph._sink_id_map = {SinkName("default"): NodeID("sink")}  # Direct private attribute!
resume_graph._transform_id_map = {0: NodeID("xform")}  # Direct private attribute!
resume_graph._default_sink = "default"  # Direct private attribute!
```

**CLAUDE.md explicitly forbids this pattern:**
> "Tests must use production code paths like `ExecutionGraph.from_plugin_instances()`"
> "Manual graph construction with `graph.add_node()` or direct attribute assignment violates this"

**Impact:** If production code has bugs in `from_plugin_instances()`, these tests would still pass because they bypass that code path entirely. This is exactly the BUG-LINEAGE-01 pattern referenced in CLAUDE.md.

**Recommendation:** Refactor all tests to use `ExecutionGraph.from_plugin_instances()` with real plugin instances. The tests already create `PipelineConfig` with real plugins, so the graph should be built from those.

---

### 2. MEDIUM: Fixture Shadow/Conflict - `payload_store`

**Severity:** MEDIUM
**Location:** Lines 243-247, 351-355, etc.

The tests have both a `payload_store` parameter AND access `test_env["payload_store"]`:

```python
def test_resume_normal_path_with_remaining_rows(
    self,
    test_env: dict[str, Any],
    payload_store,  # This shadows the conftest.py payload_store fixture
) -> None:
    ...
    payload_store = test_env["payload_store"]  # Immediately reassigned
```

The `payload_store` parameter pulls in the global `MockPayloadStore` from `conftest.py`, but then immediately reassigns it to `test_env["payload_store"]` which is a `FilesystemPayloadStore`.

**Impact:**
- The `conftest.py` fixture is instantiated but never used
- Confusion about which payload store is being used
- Potential for subtle bugs if someone removes the reassignment

**Recommendation:** Remove the `payload_store` fixture parameter from all test methods since they use `test_env["payload_store"]`.

---

### 3. LOW: Duplicate Setup Code

**Severity:** LOW
**Location:** `_setup_failed_run()` (lines 100-241) and inline setup in each test

There's significant code duplication between:
1. `_setup_failed_run()` helper method
2. Manual setup in type-specific tests (datetime, decimal, array, object tests)

Each of the type-specific tests (lines 456-1260) manually reproduces most of the setup logic with minor variations, rather than parameterizing `_setup_failed_run()` or creating a more flexible helper.

**Recommendation:** Extend `_setup_failed_run()` to accept schema and row data as parameters, or use pytest parametrization.

---

### 4. LOW: Hardcoded Edge IDs May Not Match Production

**Severity:** LOW
**Location:** Lines 202-216, 552-566, etc.

Edge IDs are manually created as "e1", "e2" in the database setup:

```python
for edge_id, from_node, to_node in [
    ("e1", "src", "xform"),
    ("e2", "xform", "sink"),
]:
```

Production code likely generates different edge IDs (UUIDs). The test documents this is testing "Bug #3 - Resume with real edge IDs" but the test doesn't actually verify the edge ID format matches production.

**Recommendation:** Verify that the edge ID format used in tests matches what production code would generate.

---

### 5. LOW: Test Documentation References Non-existent Bugs

**Severity:** LOW
**Location:** Lines 3-10

The docstring references "Bug #3", "Bug #4", "Bug #8" without providing links or ticket references:

```python
"""Comprehensive end-to-end integration tests for the resume process.

Tests all critical aspects of resume:
1. Normal resume with remaining rows (Happy path)
2. Early-exit resume with no remaining rows (Bug #8)
3. Resume with schema type restoration (Bug #4)
4. Resume with real edge IDs (Bug #3)
```

These appear to be internal bug references that may not be tracked anywhere findable.

**Recommendation:** Add full bug ticket references (e.g., JIRA IDs, GitHub issue numbers) or remove the references if they're no longer relevant.

---

### 6. GOOD: Correct Schema Contract Usage

The tests properly create `SchemaContract` and `ContractAuditRecord` for the PipelineRow migration (lines 136-163, 498-504, etc.). This is the correct pattern.

---

### 7. GOOD: Meaningful Assertions

The tests have strong assertions that verify actual behavior:
- Row counts processed (lines 336-338)
- Checkpoint cleanup verification (lines 347-349, 447-450)
- Output file content verification (lines 341-344)
- Status verification throughout

---

### 8. GOOD: Test Isolation

Each test uses fresh database instances via `tmp_path` fixture and proper cleanup is verified.

---

## Test Class Discovery

**Status:** PASS

The class is correctly named `TestResumeComprehensive` (starts with "Test") so pytest will discover all methods.

---

## Missing Coverage

### 1. Resume with Multiple Transforms

No test exercises resume with more than one transform in the pipeline. The DAG structure is always: source -> single transform -> sink.

### 2. Resume with Gates/Routing

No tests cover resume when the original run had gate routing decisions.

### 3. Resume with Forks/Coalesce

No tests cover resume of a forked/joined pipeline.

### 4. Resume Failure Scenarios

Only `test_resume_with_unsupported_type_crashes` tests error paths. Missing:
- Resume when checkpoint is corrupted
- Resume when payload data is missing
- Resume when graph structure has changed since original run

---

## Efficiency Issues

### 1. Repeated Database Setup

Each test creates the full database schema. Consider using pytest fixtures with `scope="class"` for the database engine if tests don't need complete isolation.

### 2. Large Test Methods

Several tests are 100-150 lines long. The setup logic could be extracted to reduce duplication.

---

## Recommendations Summary

| Priority | Issue | Action |
|----------|-------|--------|
| **HIGH** | Test Path Integrity Violation | Refactor to use `ExecutionGraph.from_plugin_instances()` |
| **MEDIUM** | Fixture shadow/conflict | Remove unused `payload_store` parameter |
| **LOW** | Code duplication | Extract common setup to parameterized helper |
| **LOW** | Missing coverage | Add tests for multi-transform, gates, forks |

---

## Verdict

**NEEDS WORK** - The tests are well-structured and test important resume scenarios, but the critical Test Path Integrity violation means they bypass production graph construction code, potentially hiding bugs. The fixture conflict is also a code quality issue that should be addressed.
