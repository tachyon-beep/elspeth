# Test Audit: test_openrouter_multi_query.py

**File:** `tests/plugins/llm/test_openrouter_multi_query.py`
**Lines:** 974
**Batch:** 128

## Summary

Tests for OpenRouter Multi-Query LLM transform that executes multiple queries (case_studies x criteria) per row using row-level pipelining. Covers configuration validation, single query processing, row processing with result merging, and HTTP-specific error handling.

## Audit Findings

### 1. Defects

**LOW CONCERN**:

1. **Lines 55-58**: `make_openrouter_response` is essentially a passthrough function that adds no value:
   ```python
   def make_openrouter_response(content: dict[str, Any] | str) -> dict[str, Any] | str:
       """Create an OpenRouter message content payload."""
       return content
   ```
   This could be removed with all callers just passing content directly.

### 2. Overmocking

**MEDIUM CONCERN**:

1. **Lines 232-264, 266-297**: Tests for CapacityError on 429/503 fully mock httpx.Client including the context manager pattern. While necessary, this creates fragility if the production code changes how it uses httpx.Client.

2. **Lines 503-559**: `test_process_row_fails_if_any_query_fails` uses a complex mocking pattern with call_count tracking. The test is hard to follow and maintains internal state.

### 3. Missing Coverage

**MEDIUM CONCERN**:

1. **No test for partial query success** - Tests verify all-or-nothing behavior (`test_process_row_fails_if_any_query_fails`), but the docstring says "if any query fails, entire row fails." There's no test for what happens with query-level retries.

2. **No test for query order determinism** - With 4 queries (2 case studies x 2 criteria), the order they execute could matter for reproducibility.

3. **No test for large case_studies/criteria combinations** - What about 10x10 = 100 queries per row? This could cause memory or timing issues.

4. **Lines 619-697**: `test_multiple_rows_processed_in_fifo_order` explicitly removes pool_size to avoid mock threading issues. This comment indicates the test is working around a testing limitation rather than properly testing concurrent behavior.

### 4. Tests That Do Nothing

**PASS** - All tests make meaningful assertions.

### 5. Inefficiency

**MEDIUM CONCERN**:

1. **Lines 380-418, 604-617, 728-753, 755-763**: Four different test classes define nearly identical fixtures:
   - `mock_recorder`
   - `collector`
   - `ctx`
   - `transform`

   These should be consolidated at module level or in a base class.

2. **Lines 619-697**: The comment "Uses sequential execution (no pool_size) to avoid mock threading issues" reveals that the mocking infrastructure doesn't properly support concurrent testing. This means pool_size > 1 behavior isn't being tested despite being configured.

### 6. Structural Issues

**LOW CONCERN**:

1. **Good class organization** - Clear separation between single query tests, row processing tests, multi-row pipelining tests, HTTP-specific tests, and resource cleanup tests.

2. **Import of _make_pipeline_row from conftest** - Line 21 imports from conftest, but the same function is also defined locally in test_openrouter.py. Should use conftest consistently.

## Specific Test Analysis

### TestSingleQueryProcessing (Lines 155-378)

**GOOD**: Comprehensive testing of the `_process_single_query` method including:
- Template rendering verification
- JSON response parsing
- Invalid JSON handling
- Rate limit (429) to CapacityError conversion
- Service unavailable (503) handling
- Template error handling
- Markdown code block stripping
- JSON type validation (must be dict, not array)

### TestRowProcessingWithPipelining (Lines 380-602)

**GOOD**: Tests the full row processing flow including:
- All queries executed per row
- Results merged into single output row
- All-or-nothing failure semantics
- Metadata fields in output

### TestResourceCleanup (Lines 921-974)

**GOOD**: Verifies proper cleanup of:
- Executor shutdown
- HTTP client cache clearing
- Recorder reference clearing
- on_start recorder capture

## Recommendations

1. **HIGH**: Consolidate repeated fixture definitions across test classes.

2. **MEDIUM**: Add proper concurrent testing instead of working around with `del config["pool_size"]`.

3. **MEDIUM**: Remove the no-op `make_openrouter_response` function.

4. **LOW**: Add test for large query matrix (many case_studies x many criteria).

## Quality Score

**7/10** - Good functional coverage but significant code duplication across test classes and acknowledged workaround for concurrent testing limitations.
