# Test Audit: test_azure.py

**File:** `tests/plugins/llm/test_azure.py`
**Lines:** 1002
**Batch:** 120

## Summary

This test file validates the `AzureLLMTransform` plugin, which handles Azure OpenAI API calls with row-level pipelining via `BatchTransformMixin`. The tests cover config validation, initialization, pipelining behavior, concurrency, and integration scenarios.

## Test Classes

| Class | Test Count | Purpose |
|-------|------------|---------|
| `TestAzureOpenAIConfig` | 9 | Config validation |
| `TestAzureLLMTransformInit` | 8 | Transform initialization |
| `TestAzureLLMTransformPipelining` | 14 | Row-level pipelining with accept() API |
| `TestAzureLLMTransformIntegration` | 3 | Integration scenarios |
| `TestAzureLLMTransformConcurrency` | 4 | Concurrent processing |

## Findings

### 1. POSITIVE: Comprehensive Config Validation

Tests thoroughly validate required fields:
- `deployment_name`, `endpoint`, `api_key`, `template`, `schema`
- Default values for `api_version`, `temperature`, `max_tokens`
- Inheritance from `LLMConfig`

### 2. POSITIVE: Well-Designed Test Fixtures

The file uses fixtures effectively:
```python
@pytest.fixture
def transform(self, collector, mock_recorder) -> Generator[AzureLLMTransform, None, None]:
    t = AzureLLMTransform(...)
    t.on_start(init_ctx)
    t.connect_output(collector, max_pending=10)
    yield t
    t.close()  # Proper cleanup
```

The fixture handles setup AND teardown, ensuring resources are cleaned up.

### 3. POSITIVE: ChaosLLM Integration

Tests use `chaosllm_azure_openai_client` context manager which patches `openai.AzureOpenAI` with controlled response generation:
```python
with chaosllm_azure_openai_client(chaosllm_server, mode="template", template_override="Analysis result"):
    transform.accept(row, ctx)
```

This provides realistic LLM response simulation without actual API calls.

### 4. VERIFIED: Fixture Dependency Chain

**Location:** Line 20
```python
from .conftest import chaosllm_azure_openai_client
```

**Finding:** The tests import `chaosllm_azure_openai_client` from local conftest, which requires a `chaosllm_server` fixture.

**Verification:** The `chaosllm_server` fixture is imported and exported in `tests/conftest.py` (line 91):
```python
from tests.fixtures.chaosllm import ChaosLLMFixture, chaosllm_server
```

**Status:** Correctly configured. Pytest's fixture discovery finds `chaosllm_server` from root conftest.

**Severity:** None - working as intended.

### 5. POSITIVE: Error Propagation Testing

Tests verify correct error handling behavior per CLAUDE.md:
```python
def test_rate_limit_error_propagates_for_engine_retry(self, ...):
    """Rate limit errors propagate as exceptions for engine retry."""
    # Returns ExceptionResult wrapper, not TransformResult.error()
    assert isinstance(result, ExceptionResult)
    assert isinstance(result.exception, RateLimitError)
```

This correctly tests that retryable errors bubble up to the engine's RetryManager.

### 6. POSITIVE: State Management Testing

Tests verify lifecycle methods:
- `on_start()` captures recorder reference
- `close()` clears recorder and cached clients
- `connect_output()` cannot be called twice
- `accept()` fails without `connect_output()`

### 7. MINOR GAP: Missing Template Hash Collision Test

**Issue:** Tests verify `llm_response_template_hash` exists but don't verify hash determinism or collision resistance.

**Missing test:**
```python
def test_same_template_same_hash():
    """Same template produces identical hash."""
```

**Severity:** Low - hash implementation is tested elsewhere.

### 8. POTENTIAL ISSUE: Fixture Reuse Pattern

**Location:** Lines 534-578, 580-622, etc.

Multiple tests create their own transform instances inside the test method despite fixtures being available:
```python
def test_system_prompt_included_in_messages(self, mock_recorder, collector, chaosllm_server):
    transform = AzureLLMTransform({...})  # Creates new transform
    init_ctx = PluginContext(...)
    transform.on_start(init_ctx)
    transform.connect_output(collector, max_pending=10)
    try:
        ...
    finally:
        transform.close()
```

**Impact:** Code duplication. These tests need different configs so creating inline is acceptable, but the try/finally pattern could use a context manager.

**Severity:** Low (style)

### 9. POSITIVE: Security Testing

Test verifies API key is not exposed in `azure_config`:
```python
def test_azure_config_property(self):
    config = transform.azure_config
    assert "api_key" not in config  # Security check
```

### 10. POSITIVE: Test Path Integrity

**Status:** Compliant

Tests use production code paths:
- `AzureLLMTransform` constructor with real config
- `on_start()` and `connect_output()` lifecycle methods
- `accept()` and `flush_batch_processing()` for processing

No manual construction bypassing production factories.

## Recommendations

1. **Verify:** Confirm `chaosllm_server` fixture is defined in root conftest.py
2. **Low Priority:** Consider extracting transform setup pattern into a helper for tests needing custom configs
3. **Low Priority:** Add hash determinism test

## Risk Assessment

| Category | Risk Level |
|----------|------------|
| Defects | None identified |
| Overmocking | Low - ChaosLLM provides realistic simulation |
| Missing Coverage | Low - thorough coverage |
| Tests That Do Nothing | None |
| Structural Issues | Minor - some code duplication |

## Verdict

**PASS** - Excellent test coverage with good use of ChaosLLM for simulation. Fixture dependency chain verified. Minor code duplication in tests that need custom configs.
