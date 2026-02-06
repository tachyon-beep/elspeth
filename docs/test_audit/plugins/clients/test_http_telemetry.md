# Test Audit: test_http_telemetry.py

**File:** `/home/john/elspeth-rapid/tests/plugins/clients/test_http_telemetry.py`
**Lines:** 449
**Batch:** 116

## Summary

Tests for telemetry integration in `AuditedHTTPClient`. Focuses on verifying correct telemetry event emission, ordering relative to Landscape recording, and error handling.

## Findings

### 1. OVERMOCKING: Deep Mocking of httpx.Client

**Severity:** Medium
**Location:** Lines 60-65, 115-120, etc.

```python
with patch("httpx.Client") as mock_client_class:
    mock_client_instance = MagicMock()
    mock_client_instance.post.return_value = mock_response
    mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
    mock_client_instance.__exit__ = MagicMock(return_value=False)
    mock_client_class.return_value = mock_client_instance
```

This deep mocking of httpx internals is necessary for testing telemetry emission without making real HTTP calls. However, it's fragile if httpx changes its context manager implementation. Compare this to `test_http.py` which uses `respx` for more realistic HTTP mocking.

**Impact:** Tests may pass even if the actual httpx integration is broken. However, `test_http.py` covers the real httpx integration.

**Recommendation:** This is acceptable given that `test_http.py` provides the realistic HTTP testing and this file focuses specifically on telemetry behavior.

### 2. GOOD: Critical Ordering Test

**Location:** Lines 177-220

```python
def test_telemetry_emitted_after_landscape_recording(self) -> None:
    """Telemetry is emitted AFTER Landscape recording succeeds."""
```

This test verifies a critical invariant: telemetry must come after the audit record is written.

### 3. GOOD: No-Telemetry-On-Failure Test

**Location:** Lines 222-266

```python
def test_no_telemetry_when_landscape_recording_fails(self) -> None:
    """Telemetry is NOT emitted if Landscape recording fails."""
```

Critical test that ensures we don't emit telemetry for events that weren't properly recorded to the audit trail.

### 4. GOOD: Telemetry Isolation Test

**Location:** Lines 268-315

```python
def test_telemetry_failure_does_not_corrupt_successful_call(self) -> None:
```

Regression test for telemetry failure isolation. Verifies only one audit record is created even when telemetry fails.

### 5. GOOD: Security Test for Credential Leakage

**Location:** Lines 359-410

```python
def test_provider_extraction_strips_credentials_from_url(self) -> None:
    """Provider extraction MUST NOT include credentials from URL."""
```

Important security test with explicit assertions for credential non-leakage.

### 6. EFFICIENCY: Repeated Mock Setup

**Severity:** Low
**Location:** Throughout file

Each test method in the class repeats the mock setup for `httpx.Client`. This could be extracted to a class-level fixture or helper method.

### 7. GOOD: Hash Verification

**Location:** Lines 84-87

```python
assert event.request_hash is not None
assert len(event.request_hash) == 64  # SHA-256 hex digest
assert event.response_hash is not None
assert len(event.response_hash) == 64  # SHA-256 hex digest
```

Verifies that hashes are computed with correct format (SHA-256).

### 8. MISSING COVERAGE: No Test for Telemetry Content Accuracy

**Severity:** Low
**Location:** N/A

While the tests verify that telemetry is emitted and has the right structure, they don't verify that the telemetry payload content matches the actual request/response. The mock response is constructed manually, so this can't catch serialization bugs.

## Test Path Integrity

**Status:** PASS

No graph construction involved. Tests client telemetry behavior directly.

## Verdict

**PASS** - Comprehensive telemetry tests covering critical ordering, isolation, and security properties. The deep httpx mocking is acceptable given complementary tests in `test_http.py`.

## Recommendations

1. Consider extracting the httpx mock setup into a reusable fixture to reduce code duplication
2. Consider adding a test that uses respx (like test_http.py does) to verify telemetry with realistic HTTP mocking for at least one happy path
3. The test class structure is good and follows pytest class conventions
