# Test Audit: tests/integration/test_resume_schema_required.py

**Auditor:** Claude
**Date:** 2026-02-05
**Batch:** 105-106

## Overview

This file contains integration tests for Bug #4 (Type Degradation on Resume - Schema Required). Tests verify that resume requires source schema for type fidelity and fails early with a clear error if schema is not available.

**Lines:** 193
**Test Class:** `TestResumeSchemaRequired`
**Test Count:** 1

---

## Summary

| Category | Issues Found |
|----------|--------------|
| Defects | 1 (MAJOR) |
| Test Path Integrity Violations | 1 (MAJOR) |
| Overmocking | 0 |
| Missing Coverage | 1 |
| Tests That Do Nothing | 1 (MAJOR) |
| Structural Issues | 1 |
| Inefficiency | 0 |

---

## Issues

### 1. [CRITICAL] Test Does Not Test Production Code

**Location:** `test_resume_fails_early_without_source_schema` (lines 81-193)

**Problem:** This test is fundamentally broken. It manually raises an exception and then catches it, rather than testing the actual production code path:

```python
# 4. Verify that validation would catch this
# The validation code from orchestrator (lines 1349-1355)
if source_schema_class is None:
    # This is what the orchestrator does - fail early with clear error
    with pytest.raises(ValueError) as exc_info:
        raise ValueError(  # <-- TEST RAISES ITS OWN EXCEPTION!
            f"Resume failed: Source plugin '{source_without_schema.name}' does not provide schema class. "
            # ...
        )

# 5. Verify error message is clear and helpful
error_msg = str(exc_info.value)
assert "Resume failed" in error_msg  # <-- ASSERTS ON MANUALLY RAISED EXCEPTION
```

**Impact:** This test ALWAYS passes regardless of whether the actual orchestrator validates this condition. It tests nothing about production behavior.

**Why This Is Severe:** The test claims to verify "Bug #4 fix" but provides zero confidence that the fix actually works. If someone removes the validation from the orchestrator, this test would still pass.

**Recommendation:** The test must call the actual orchestrator resume code and verify it raises the expected error. Example:

```python
# Call the actual production code that should fail
with pytest.raises(ValueError, match="does not provide schema class"):
    orchestrator.resume(run_id=run.run_id, source=source_without_schema, ...)
```

---

### 2. [MAJOR] Test Path Integrity Violation - Manual Graph Construction

**Location:** `simple_graph` fixture (lines 72-79)

**Problem:** Manual graph construction using `graph.add_node()` instead of `ExecutionGraph.from_plugin_instances()`.

```python
@pytest.fixture
def simple_graph(self) -> ExecutionGraph:
    """Create a simple source -> sink graph."""
    graph = ExecutionGraph()
    schema_config = {"schema": {"mode": "observed"}}
    graph.add_node("source", node_type=NodeType.SOURCE, ...)
```

---

### 3. [MINOR] Missing Coverage - Successful Schema Scenario

**Problem:** No positive test case verifying that resume succeeds when the source DOES provide a schema. A proper test suite should verify both the error case and the success case.

---

### 4. [MINOR] Raw SQL Node Registration

**Location:** Lines 110-142

**Problem:** Nodes are registered with raw SQL instead of using the recorder API, similar to `test_resume_edge_ids.py`.

---

## What The Test Should Do

A proper implementation would:

1. Create a mock orchestrator or use the real one
2. Create a run that was interrupted (with checkpoint)
3. Attempt to resume using a source that lacks `_schema_class`
4. Verify the orchestrator raises `ValueError` with the expected message

---

## Verdict

**CRITICAL - MUST FIX** - This test is fundamentally broken and provides no confidence in the Bug #4 fix. It manually raises an exception and then asserts on that exception, testing nothing about production behavior. This is one of the most severe test defects: a test that always passes regardless of whether the code under test works correctly.
