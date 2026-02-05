# Test Audit: test_azure_multi_query.py

**File:** `tests/plugins/llm/test_azure_multi_query.py`
**Lines:** 901
**Batch:** 122

## Summary

This test file comprehensively tests the AzureMultiQueryLLMTransform, which processes rows through multiple LLM queries (case studies x criteria). Tests cover initialization, single query processing, row-level pipelining via accept() API, FIFO ordering, and pool metadata auditing.

## Findings

### 1. Defects

**NONE FOUND** - Tests appear correctly implemented.

### 2. Overmocking

**MODERATE CONCERN:** The tests mock at the Azure OpenAI client level using the `chaosllm_*` helpers, which is appropriate for unit tests but may hide issues with:
- Actual HTTP client behavior
- Authentication handling
- Response parsing edge cases

However, this is the correct level for these tests - they're testing the transform logic, not the Azure SDK integration.

**NOTE:** The conftest helpers (`chaosllm_azure_openai_responses`, etc.) use `itertools.cycle()` for responses, which means if a test expects N responses but the transform makes N+1 calls, it will silently succeed with recycled responses. This could hide bugs.

### 3. Missing Coverage

| Gap | Severity | Description |
|-----|----------|-------------|
| No test for template with missing variables | MEDIUM | What happens when input row is missing fields referenced in template? |
| No test for very large rows | LOW | Memory behavior with large input data not tested |
| No test for empty case_studies/criteria | LOW | Edge case validation |
| No test for max_pending backpressure | MEDIUM | `connect_output(..., max_pending=10)` is set but backpressure behavior not tested |

### 4. Tests That Do Nothing

**NONE** - All tests have meaningful assertions.

### 5. Inefficiency

**ISSUE: Duplicated helper function** (lines 29-46)

`_make_pipeline_row()` is defined in this file AND in `conftest.py`. The conftest version should be used:

```python
# In conftest.py:
def _make_pipeline_row(data: dict[str, Any]) -> PipelineRow:
    """Create a PipelineRow with OBSERVED contract for testing."""
    ...

# Duplicated in test_azure_multi_query.py (lines 29-46)
def _make_pipeline_row(data: dict[str, Any]) -> PipelineRow:
    """Create a PipelineRow with OBSERVED schema for testing."""
    ...
```

**Recommendation:** Remove the local `_make_pipeline_row` and import from conftest.

**ISSUE: Repeated fixture definitions** (lines 234-256, 427-437, 640-650, 752-762)

The `mock_recorder` and `collector` fixtures are redefined in multiple test classes:

```python
class TestRowProcessingWithPipelining:
    @pytest.fixture
    def mock_recorder(self) -> Mock:
        recorder = Mock()
        recorder.record_call = Mock()
        return recorder

class TestMultiRowPipelining:
    @pytest.fixture
    def mock_recorder(self) -> Mock:
        recorder = Mock()
        recorder.record_call = Mock()
        return recorder
# ... same pattern in TestSequentialMode, TestPoolMetadataAuditIntegration
```

**Recommendation:** Move these to module-level fixtures or conftest.py.

### 6. Structural Issues

**GOOD:** All test classes have `Test` prefix and will be discovered by pytest.

**GOOD:** Tests are well-organized into logical classes:
- `TestAzureMultiQueryLLMTransformInit` - initialization tests
- `TestSingleQueryProcessing` - single query behavior
- `TestRowProcessingWithPipelining` - accept() API tests
- `TestMultiRowPipelining` - FIFO ordering and concurrency
- `TestSequentialMode` - sequential fallback
- `TestPoolMetadataAuditIntegration` - audit trail metadata

**MINOR:** Line 900-901 contains a comment about removed test but leaves an empty line at end of file.

### 7. Test Path Integrity

**GOOD:** Tests use the actual `AzureMultiQueryLLMTransform` class and its `accept()` API, which is the production code path.

**GOOD:** Tests call `transform.on_start()`, `transform.connect_output()`, and `transform.flush_batch_processing()` - the actual lifecycle methods.

**POTENTIAL ISSUE:** Tests access internal state for verification:
- `transform._query_specs` (line 66)
- `transform._executor` (line 669)
- `transform._recorder` (lines 606, 634)
- `transform._llm_clients` (line 597)
- `transform._get_llm_client` (lines 518-524)

While this is sometimes necessary for unit tests, it couples tests to implementation details.

## Risk Assessment

| Risk | Level | Notes |
|------|-------|-------|
| False positives | LOW | ChaosLLM provides realistic responses |
| False negatives | LOW | Comprehensive assertions |
| Test maintenance | MEDIUM | Internal state access creates coupling |
| Bug-hiding | LOW | Appropriate mocking level |

## Recommendations

1. **REFACTOR:** Remove duplicated `_make_pipeline_row()` function, import from conftest
2. **REFACTOR:** Consolidate repeated `mock_recorder` and `collector` fixtures
3. **ADD:** Test for template rendering with missing input fields
4. **ADD:** Test for backpressure when max_pending is reached
5. **CONSIDER:** Adding a comment about why internal state access is necessary in specific tests

## Overall Grade: A-

Well-structured, comprehensive test suite. The main issues are code duplication that should be refactored for maintainability.
