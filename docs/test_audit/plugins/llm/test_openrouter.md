# Test Audit: test_openrouter.py

**File:** `tests/plugins/llm/test_openrouter.py`
**Lines:** 1695
**Batch:** 127

## Summary

Tests for the OpenRouter LLM transform with row-level pipelining via BatchTransformMixin. Covers configuration validation, the accept() API for concurrent processing, template features, and error handling for various HTTP and API failure modes.

## Audit Findings

### 1. Defects

**PASS** - No significant defects found. Tests properly verify behavior and edge cases.

### 2. Overmocking

**LOW CONCERN** - The tests mock HTTP responses via ChaosLLM fixtures which is appropriate for this unit test level. The mocking is well-structured through `mock_httpx_client` context manager.

One minor observation:
- Lines 570-600: `test_missing_state_id_propagates_exception` verifies behavior when state_id is None, but the test acknowledges this creates an ExceptionResult wrapper in tests vs actual production crash behavior. This is acceptable documentation of the difference.

### 3. Missing Coverage

**MEDIUM CONCERN** - Some gaps identified:

1. **No test for concurrent pipelining stress scenarios** - While `test_multiple_rows_processed_in_fifo_order` tests FIFO ordering, there's no test for backpressure behavior when `max_pending` is exceeded.

2. **No test for on_complete lifecycle hook** - Tests cover `on_start`, `connect_output`, and `close`, but don't verify on_complete behavior if it exists.

3. **No test for template_hash determinism** - Tests verify template_hash is present but don't verify the same template produces the same hash consistently.

4. **No test for response_field collision** - What happens if the custom response_field conflicts with an existing row field? This could silently overwrite data.

### 4. Tests That Do Nothing

**PASS** - All tests make meaningful assertions.

### 5. Inefficiency

**MEDIUM CONCERN**:

1. **Repeated fixture patterns across test classes** - Lines 301-343, 815-825, 1216-1225, 1591-1601 all define nearly identical `mock_recorder`, `collector`, and context fixtures. These could be consolidated using module-level fixtures or a base test class.

2. **Transform teardown in every test** - Many tests manually create transforms and call `close()` in try/finally blocks. The `transform` fixture in `TestOpenRouterLLMTransformPipelining` (lines 326-344) handles this correctly; other classes should follow this pattern.

### 6. Structural Issues

**LOW CONCERN**:

1. **Good organization** - Test classes are well-organized by functionality (Config, Init, Pipelining, Integration, TemplateFeatures, Concurrency).

2. **Helper function placement** - `_make_pipeline_row`, `_create_mock_response`, `mock_httpx_client`, and `make_token` are defined at module level (lines 28-113) which is appropriate.

3. **Long file** - At 1695 lines, the file is large but not unreasonably so given the scope of functionality tested.

## Recommendations

1. **HIGH**: Add test for response_field collision with existing row fields to verify expected behavior (overwrite vs error).

2. **MEDIUM**: Consolidate repeated fixture definitions across test classes using pytest class inheritance or module-level fixtures.

3. **LOW**: Add a test verifying template_hash determinism for audit reproducibility.

## Quality Score

**7/10** - Comprehensive tests with good error case coverage. Main concerns are repeated boilerplate and a few missing edge cases.
