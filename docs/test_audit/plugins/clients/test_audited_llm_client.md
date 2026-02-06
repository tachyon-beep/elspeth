# Test Audit: test_audited_llm_client.py

**File:** `tests/plugins/clients/test_audited_llm_client.py`
**Lines:** 672
**Batch:** 115

## Summary

This test file covers `AuditedLLMClient`, which wraps OpenAI-compatible clients to record all LLM calls to the Landscape audit trail. Tests cover successful calls, error handling, rate limit detection, response formats, and raw response preservation.

## Audit Results

### 1. Defects

**PASS** - No defects found. Tests correctly verify:
- Audit trail recording with correct call type, status, request/response data
- Rate limit error classification
- Token usage handling (including missing usage)
- Raw response preservation for tool calls and multiple choices

### 2. Overmocking

**ACCEPTABLE** - The mocking is appropriate:
- OpenAI client is mocked with realistic response structure
- Mock responses include all required attributes (`choices`, `message`, `content`, `usage`, `model_dump`)
- `LandscapeRecorder` mock accurately simulates call index allocation

The `_create_mock_openai_client` helper creates realistic mock structures, making tests readable and maintainable.

### 3. Missing Coverage

**MEDIUM PRIORITY** - Missing tests:

1. **Rate limiter integration** - No tests verify `_acquire_rate_limit()` is called before LLM requests.

2. **Telemetry emission** - No tests verify `telemetry_emit` callback is called with `ExternalCallCompleted` event.

3. **Error type classification completeness** - Production code has specific error types:
   - `NetworkError` - not tested
   - `ServerError` - not tested
   - `ContentPolicyError` - not tested
   - `ContextLengthError` - not tested

   Only `RateLimitError` and generic `LLMClientError` are tested.

4. **`_is_retryable_error` function** - Production code has complex error classification logic. Only rate limit detection is tested. Missing tests for:
   - Server errors (500, 502, 503, 504, 529)
   - Network errors (timeout, connection refused)
   - Content policy violations
   - Context length exceeded

5. **Streaming responses** - Production code handles `usage=None` (common in streaming). Test exists for this, but no test for streaming-mode responses.

6. **Multiple choices extraction** - Test verifies raw_response preserves choices, but doesn't test that `content` is extracted from first choice when n>1.

### 4. Tests That Do Nothing

**PASS** - All tests have meaningful assertions:
- Verify `recorder.record_call` arguments
- Verify response content, model, usage, latency
- Verify error types and retryable flags

### 5. Inefficiency

**MINOR** - Some duplication:
- Each test creates its own mock recorder with identical pattern
- `_create_mock_openai_client` is duplicated in each test that needs custom response

The duplication is less severe than `test_audited_http_client.py` due to better helper methods.

### 6. Structural Issues

**PASS** - Good structure:
- `Test` prefix on all test classes
- Logical groupings (LLMResponse, LLMClientErrors, AuditedLLMClient)
- Good docstrings explaining test rationale

**NOTE** - Good documentation about removed tests:
```python
# NOTE: test_response_without_model_dump was removed because we require
# openai>=2.15 which guarantees model_dump() exists on all responses.
# Per CLAUDE.md "No Legacy Code Policy" - no backwards compatibility code.
```

### 7. Test Path Integrity

**PASS** - Tests instantiate real `AuditedLLMClient` and call real `chat_completion` method. The mocking is at the external API boundary (OpenAI client) which is appropriate.

## Notable Strengths

1. **Raw response preservation** - Excellent tests for preserving tool calls, multiple choices, and system fingerprints in the audit trail.

2. **Missing usage handling** - Good test for `usage=None` scenario (streaming, certain Azure configs).

3. **Error classification** - Tests verify error types are raised correctly (RateLimitError vs LLMClientError).

4. **LLMResponse dataclass tests** - Thorough coverage of the response object including `total_tokens` property.

## Recommendations

### High Priority

1. Add tests for all error types in production code:
```python
def test_network_error_raised_on_timeout(self):
    """Timeout errors are classified as NetworkError (retryable)."""
    openai_client.chat.completions.create.side_effect = Exception("Connection timed out")
    with pytest.raises(NetworkError) as exc_info:
        client.chat_completion(...)
    assert exc_info.value.retryable is True

def test_server_error_raised_on_500(self):
    """Server 500 errors are classified as ServerError (retryable)."""
    openai_client.chat.completions.create.side_effect = Exception("Internal Server Error (500)")
    with pytest.raises(ServerError) as exc_info:
        client.chat_completion(...)
    assert exc_info.value.retryable is True

def test_content_policy_error_not_retryable(self):
    """Content policy violations are not retryable."""
    openai_client.chat.completions.create.side_effect = Exception("content_policy_violation")
    with pytest.raises(ContentPolicyError) as exc_info:
        client.chat_completion(...)
    assert exc_info.value.retryable is False

def test_context_length_error_not_retryable(self):
    """Context length exceeded is not retryable."""
    openai_client.chat.completions.create.side_effect = Exception("context_length_exceeded")
    with pytest.raises(ContextLengthError) as exc_info:
        client.chat_completion(...)
    assert exc_info.value.retryable is False
```

### Medium Priority

2. Add tests for `_is_retryable_error` function directly:
```python
class TestIsRetryableError:
    """Tests for error classification logic."""

    def test_rate_limit_retryable(self):
        assert _is_retryable_error(Exception("Rate limit exceeded")) is True
        assert _is_retryable_error(Exception("Error 429")) is True

    def test_server_errors_retryable(self):
        for code in ["500", "502", "503", "504", "529"]:
            assert _is_retryable_error(Exception(f"Error {code}")) is True

    def test_network_errors_retryable(self):
        for pattern in ["timeout", "connection refused", "dns"]:
            assert _is_retryable_error(Exception(pattern)) is True

    def test_client_errors_not_retryable(self):
        for code in ["400", "401", "403", "404"]:
            assert _is_retryable_error(Exception(f"Error {code}")) is False

    def test_unknown_errors_not_retryable(self):
        assert _is_retryable_error(Exception("Something unknown")) is False
```

3. Add test for rate limiter integration:
```python
def test_rate_limiter_acquired_before_request(self):
    """_acquire_rate_limit is called before making LLM request."""
    mock_limiter = MagicMock()
    client = AuditedLLMClient(..., limiter=mock_limiter)
    client.chat_completion(...)
    mock_limiter.acquire.assert_called_once()
```

4. Add test for telemetry emission.

### Low Priority

5. Extract mock setup into fixtures to reduce duplication.

## Test Quality Score: 7.5/10

Good coverage of the happy path and some error scenarios. Missing comprehensive error classification testing which is a key feature of the production code. The test for missing usage data is excellent as this is a real-world edge case. Raw response preservation tests are thorough.
