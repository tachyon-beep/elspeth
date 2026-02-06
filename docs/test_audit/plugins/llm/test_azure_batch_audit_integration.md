# Test Audit: test_azure_batch_audit_integration.py

**File:** `tests/plugins/llm/test_azure_batch_audit_integration.py`
**Lines:** 491
**Batch:** 122

## Summary

This test file validates audit trail recording for Azure Batch LLM operations, specifically testing that LLM calls are recorded against batch states and visible via the `explain()` lineage query. The tests are well-structured integration tests that use real database fixtures.

## Findings

### 1. Defects

**NONE FOUND** - The tests appear to be correctly implemented.

### 2. Overmocking

**NONE** - These are integration tests that use `real_landscape_db` fixture, which tests the actual Landscape database operations. The tests appropriately test the recording layer without mocking the database.

### 3. Missing Coverage

| Gap | Severity | Description |
|-----|----------|-------------|
| No test for batch with partial failures | LOW | Tests only cover all-success or all-failure scenarios, not mixed (some rows succeed, some fail) within a batch |
| No test for call pagination in explain() | LOW | With many calls per batch state, pagination might be needed but is not tested |
| No test for concurrent batch recording | LOW | Tests run sequentially; concurrent writes to audit trail not verified |

### 4. Tests That Do Nothing

**ISSUE:** `test_azure_batch_with_pipeline_row_inputs` (lines 458-486)

This test is incomplete and does not assert meaningful behavior:

```python
def test_azure_batch_with_pipeline_row_inputs():
    """Verify AzureBatchLLMTransform accepts PipelineRow inputs from engine."""
    # ...
    # Verify signature accepts list[PipelineRow]
    # We don't need to call process() - just verifying the type annotation
    from inspect import signature

    sig = signature(transform.process)
    assert "row" in sig.parameters
    # The actual runtime test is implicitly covered by other integration tests
```

**Problems:**
1. Only checks that a parameter named "row" exists in the signature
2. Does not verify the type annotation is `list[PipelineRow]`
3. Does not actually call `process()` to validate runtime behavior
4. Comment claims "implicit coverage" by other tests but doesn't point to which tests

**Recommendation:** Either delete this test (if coverage exists elsewhere) or expand it to verify the actual type annotation:
```python
from typing import get_type_hints
hints = get_type_hints(transform.process)
assert hints.get("row") == list[PipelineRow]
```

### 5. Inefficiency

**Minor:** Each test creates its own run with nodes, rows, and tokens. A fixture could be created for the common setup pattern:
- `begin_run()`
- `register_node()` for source
- `register_node()` for batch

However, given these are integration tests and isolation is important, this is acceptable.

### 6. Structural Issues

**GOOD:** All test classes and functions follow pytest naming conventions (Test* prefix for classes, test_* prefix for functions).

**GOOD:** Tests use the `@pytest.mark.integration` marker appropriately.

**ISSUE:** The standalone function `test_azure_batch_with_pipeline_row_inputs` (line 458) is not in a test class, which is fine for pytest but inconsistent with the other tests in this file that are standalone functions marked with `@pytest.mark.integration`.

### 7. Test Path Integrity

**GOOD:** These tests use the real LandscapeRecorder and its methods, not manually constructing database state. They test the actual recording API.

## Risk Assessment

| Risk | Level | Notes |
|------|-------|-------|
| False positives | LOW | Tests verify actual DB state |
| False negatives | LOW | Tests check specific audit trail fields |
| Test maintenance | LOW | Clear, focused tests |
| Bug-hiding | LOW | Uses real fixtures |

## Recommendations

1. **DELETE OR FIX** `test_azure_batch_with_pipeline_row_inputs` - Currently provides almost no value
2. Consider adding a test for mixed batch outcomes (some rows succeed, some fail)
3. Add `@pytest.mark.integration` marker to `test_azure_batch_with_pipeline_row_inputs` for consistency

## Overall Grade: B+

Good integration tests that validate important audit trail behavior. The main issue is one low-value test that should be fixed or removed.
