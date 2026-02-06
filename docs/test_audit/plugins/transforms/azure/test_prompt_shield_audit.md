# Test Audit: test_prompt_shield.py

**File:** `/home/john/elspeth-rapid/tests/plugins/transforms/azure/test_prompt_shield.py`
**Lines:** 1108
**Audit Date:** 2026-02-05
**Auditor:** Claude Opus 4.5

## Summary

This test file provides comprehensive coverage for the `AzurePromptShield` transform, which detects jailbreak attempts and prompt injection attacks using Azure's Prompt Shield API. The tests are well-structured and cover configuration, batch processing, attack detection scenarios, and resource cleanup. Quality is on par with the content_safety tests.

## Test Organization

| Class | Test Count | Purpose |
|-------|------------|---------|
| TestAzurePromptShieldConfig | 7 | Configuration validation |
| TestAzurePromptShieldTransform | 2 | Transform attributes and process() |
| TestPromptShieldPoolConfig | 4 | Pool configuration |
| TestPromptShieldBatchProcessing | 14 | Core batch processing behavior |
| TestPromptShieldInternalProcessing | 3 | Internal processing methods |
| TestResourceCleanup | 3 | Resource cleanup |

## Issues Found

### 1. MEDIUM: Overmocking - HTTP Client Patch Location

**Location:** Lines 320-327, 925-933

**Issue:** Same issue as content_safety tests - patching `httpx.Client` directly rather than at a more appropriate level.

```python
@pytest.fixture(autouse=True)
def mock_httpx_client(self):
    """Patch httpx.Client to prevent real HTTP calls."""
    with patch("httpx.Client") as mock_client_class:
```

**Impact:** Fragile coupling to implementation details.

**Recommendation:** Use `respx` or patch at `AuditedHTTPClient` level.

---

### 2. LOW: Missing Coverage - Rate Limiter Integration

**Location:** Implementation lines 186-187, not tested

**Issue:** Rate limiter integration is not tested:
```python
self._limiter = ctx.rate_limit_registry.get_limiter("azure_prompt_shield") if ctx.rate_limit_registry is not None else None
```

**Recommendation:** Add tests for rate limiter capture and usage.

---

### 3. LOW: Duplicate Helper Functions

**Location:** Lines 20-75

**Issue:** The helper functions are nearly identical to those in `test_content_safety.py`, with only minor differences in the `make_token` function:

```python
# test_content_safety.py
row_data=_make_pipeline_row({}),

# test_prompt_shield.py
contract = SchemaContract(mode="FLEXIBLE", fields=(), locked=True)
row_data=PipelineRow({}, contract),
```

This inconsistency is confusing and the duplication is a maintenance burden.

**Recommendation:** Extract to shared conftest.py with consistent implementation.

---

### 4. LOW: TYPE_CHECKING Import Block Unused

**Location:** Lines 16-17

**Issue:**
```python
if TYPE_CHECKING:
    pass
```

Dead code that should be removed.

---

### 5. LOW: Test `test_all_fields_mode_scans_all_string_fields` Has Incorrect Assertion

**Location:** Lines 694-734

**Issue:** The test asserts 2 API calls for a row with 4 fields:
```python
row_data = {"prompt": "safe", "title": "also safe", "count": 42, "id": 1}
# ...
assert mock_httpx_client.post.call_count == 2
```

However, `"id": 1` is an integer, so only `"prompt"` and `"title"` are strings. This is correct but the comment is misleading:
```python
# Should have called API twice (for "prompt" and "title", not "count" or "id")
```

The comment says "not id" but `id` is an integer anyway, not excluded by string filtering.

**Impact:** Minor confusion, test is technically correct.

**Recommendation:** Use clearer test data like `"id": "row-1"` as string and filter by a different mechanism, or fix the comment.

---

### 6. LOW: Missing Test for Empty documentsAnalysis Array

**Location:** Not tested

**Issue:** The implementation handles `documentsAnalysis` as a list:
```python
doc_attack = any(doc["attackDetected"] for doc in documents_analysis)
```

But no test verifies behavior when `documentsAnalysis` is an empty array `[]`. This would cause `any([])` to return `False`, which is correct behavior, but should be explicitly tested.

**Recommendation:** Add test with `"documentsAnalysis": []` response.

---

### 7. MINOR: Missing Test for Recorder Capture in accept()

**Location:** Implementation lines 236-238, not directly tested

**Issue:** The code has a fallback recorder capture in `accept()`:
```python
# Capture recorder on first row (same as on_start)
if self._recorder is None and ctx.landscape is not None:
    self._recorder = ctx.landscape
```

This fallback path is not explicitly tested.

**Recommendation:** Add test that calls `accept()` without calling `on_start()` first.

---

### 8. INFO: Good Pattern - Attack Detection Scenarios

**Location:** Lines 411-535

The tests cover all attack detection combinations:
- User prompt attack only
- Document attack only
- Both attacks detected
- No attacks (clean)

This is excellent security-focused test coverage.

---

### 9. INFO: Good Pattern - Audit Trail Recording Test

**Location:** Lines 884-919

The test `test_audit_trail_records_api_calls` verifies that API calls are recorded to the audit trail, which is critical for ELSPETH's auditability requirements:

```python
# Verify record_call was invoked
assert ctx.landscape.record_call.call_count == 1
```

This is a good pattern that should be in content_safety tests as well.

---

### 10. INFO: Good Pattern - Fail-Closed Security Posture

**Location:** Lines 619-692

Tests verify that malformed API responses result in errors (fail-closed), not silent passes (fail-open):

```python
def test_malformed_api_response_returns_error(self, mock_httpx_client: MagicMock) -> None:
    """Malformed API responses return error (fail-closed security posture)."""
```

This is the correct security posture for a security transform.

---

## Missing Coverage Analysis

| Feature | Covered | Notes |
|---------|---------|-------|
| Config validation | Yes | All required fields tested |
| User prompt attack detection | Yes | |
| Document attack detection | Yes | |
| Both attacks | Yes | |
| Empty documents array | No | Edge case |
| Batch processing flow | Yes | |
| FIFO ordering | Yes | |
| HTTP error handling | Yes | |
| Malformed API response | Yes | Fail-closed verified |
| Partial API response | Yes | |
| Resource cleanup | Yes | |
| Audit trail recording | Yes | Better than content_safety |
| Rate limiter integration | No | |
| Telemetry emission | No | |
| Non-string field filtering | Yes | |
| fields="all" mode | Yes | |

## Recommendations Summary

1. **Add rate limiter integration tests**
2. **Add empty documentsAnalysis array test**
3. **Extract shared helpers to conftest.py** (with consistent implementation)
4. **Remove dead TYPE_CHECKING import**
5. **Add audit trail recording test to content_safety** (prompt_shield has it)
6. **Fix misleading comment in fields="all" test**

## Comparison with test_content_safety.py

| Aspect | content_safety | prompt_shield | Notes |
|--------|----------------|---------------|-------|
| Audit trail test | No | Yes | Add to content_safety |
| fields="all" behavioral | No | Yes | Add to content_safety |
| Empty response array | N/A | No | Add to prompt_shield |
| Helper consistency | Different | Different | Standardize |

## Overall Assessment

**Quality: B+**

The tests are comprehensive with good security-focused coverage (fail-closed, attack combinations). The audit trail verification is a good addition not present in content_safety. Main gaps are rate limiter integration and empty array edge case. Code duplication with content_safety is the biggest structural issue.
