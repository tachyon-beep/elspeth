# Test Audit: test_audited_http_client.py

**File:** `tests/plugins/clients/test_audited_http_client.py`
**Lines:** 1289
**Batch:** 114

## Summary

This test file provides comprehensive coverage of `AuditedHTTPClient`, which wraps `httpx` to record all HTTP calls to the Landscape audit trail. Tests cover POST and GET methods, header fingerprinting, response handling, error recording, and various edge cases.

## Audit Results

### 1. Defects

**PASS** - No defects found. Tests correctly verify:
- Audit trail recording with correct call type, status, request/response data
- Auth header fingerprinting (secrets not stored)
- URL composition with base_url
- Error status codes (4xx, 5xx) recorded as ERROR
- Large response handling

### 2. Overmocking

**ACCEPTABLE** - The mocking pattern is appropriate:
- `httpx.Client` is mocked to avoid real network calls (correct for unit tests)
- Mock responses have all required attributes (`status_code`, `headers`, `content`, `json()`)
- The `LandscapeRecorder` is mocked, but the mock accurately simulates call index allocation

**CONCERN** - Every test patches `httpx.Client` with the same boilerplate:
```python
with patch("httpx.Client") as mock_client_class:
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.post.return_value = mock_response
    mock_client_class.return_value = mock_client
```
This is a lot of repetition but it's the correct pattern for testing code that uses `with httpx.Client() as client:`.

### 3. Missing Coverage

**MEDIUM PRIORITY** - Missing tests:

1. **Rate limiter integration** - No tests verify that `_acquire_rate_limit()` is called before HTTP requests when a limiter is provided.

2. **Telemetry emission** - Tests don't verify `telemetry_emit` callback is called with correct `ExternalCallCompleted` event. They only verify the recorder is called.

3. **`_extract_provider` edge cases** - Production code handles URLs with credentials (`https://user:pass@host/`). No test verifies credentials are not leaked in the provider field.

4. **JSON parse failure handling** - Production code has special handling when JSON parse fails despite `Content-Type: application/json`. This path is untested.

5. **Timeout exceptions** - Tests verify connection errors but not timeout-specific errors (`httpx.TimeoutException`).

6. **XML content type** - Production code treats `xml` in content-type as text. No test for this.

### 4. Tests That Do Nothing

**PASS** - All tests have meaningful assertions on either:
- `recorder.record_call.call_args[1]` (audit record contents)
- `mock_client.post/get.call_args` (httpx call arguments)
- `response.status_code` (return value)

### 5. Inefficiency

**HIGH** - Massive code duplication:
- `TestAuditedHTTPClient` and `TestAuditedHTTPClientGet` duplicate nearly identical tests
- Every test creates a mock recorder with the same pattern
- Every test sets up mock httpx client with identical boilerplate
- POST tests (lines 13-1027) and GET tests (lines 1029-1290) are 90% identical

**Recommendation:** Refactor using:
1. Shared fixtures for mock recorder and httpx client
2. Parametrized tests for POST/GET methods
3. Helper method for mock httpx setup

Example refactor:
```python
@pytest.fixture
def mock_recorder():
    """Create a mock LandscapeRecorder."""
    import itertools
    recorder = MagicMock()
    counter = itertools.count()
    recorder.allocate_call_index.side_effect = lambda _: next(counter)
    return recorder

@pytest.fixture
def httpx_mock():
    """Create a configurable httpx mock."""
    # ... setup code ...

@pytest.mark.parametrize("method", ["get", "post"])
def test_successful_call_records_to_audit_trail(self, method, ...):
    # Single test covering both methods
```

### 6. Structural Issues

**PASS** - Good structure:
- `Test` prefix on all test classes
- Logical separation between POST and GET tests
- Descriptive test names and docstrings

### 7. Test Path Integrity

**PASS** - Tests instantiate real `AuditedHTTPClient` and call real methods. The mocking is at the network boundary (httpx) which is appropriate.

## Notable Strengths

1. **Fingerprint testing** - Excellent coverage of auth header fingerprinting:
   - Verifies fingerprint format (`<fingerprint:64hexchars>`)
   - Verifies different credentials produce different hashes
   - Verifies dev mode behavior (headers removed)

2. **Response body handling** - Good coverage of JSON, text, and binary responses.

3. **Error response recording** - Verifies 4xx/5xx recorded as ERROR with error details.

4. **Large response handling** - Verifies responses over 100KB are not truncated.

## Recommendations

### High Priority

1. **Refactor for DRY** - The duplication between POST and GET tests is significant. A 40-50% reduction in lines is achievable.

### Medium Priority

2. Add test for rate limiter integration:
```python
def test_rate_limiter_acquired_before_request(self):
    """_acquire_rate_limit is called before making HTTP request."""
    mock_limiter = MagicMock()
    client = AuditedHTTPClient(..., limiter=mock_limiter)
    # Make request
    mock_limiter.acquire.assert_called_once()
```

3. Add test for telemetry emission:
```python
def test_telemetry_emitted_after_successful_call(self):
    """ExternalCallCompleted event is emitted after audit recording."""
    telemetry_events = []
    def capture(event): telemetry_events.append(event)

    client = AuditedHTTPClient(..., telemetry_emit=capture)
    # Make request
    assert len(telemetry_events) == 1
    assert telemetry_events[0].call_type == CallType.HTTP
```

4. Add test for URL credential stripping:
```python
def test_extract_provider_strips_credentials(self):
    """Credentials in URL are not exposed in telemetry provider field."""
    # URL with embedded credentials
    # Verify only hostname extracted
```

### Low Priority

5. Add test for JSON parse failure path.
6. Add test for XML content type handling.

## Test Quality Score: 7.5/10

Comprehensive coverage of the main functionality with excellent attention to security (fingerprinting). Significant code duplication reduces maintainability. Missing some edge cases and integration points (rate limiter, telemetry).
