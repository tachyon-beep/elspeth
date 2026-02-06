# Test Audit: test_llm_telemetry.py

**File:** `/home/john/elspeth-rapid/tests/plugins/clients/test_llm_telemetry.py`
**Lines:** 380
**Batch:** 117

## Summary

Tests for telemetry integration in `AuditedLLMClient`. Covers telemetry event emission, ordering relative to Landscape recording, error handling, and token usage tracking.

## Findings

### 1. GOOD: Well-Structured Mock Helpers

**Location:** Lines 22-64

```python
def _create_mock_recorder(self) -> MagicMock:
def _create_mock_openai_client(...) -> MagicMock:
```

Clean helper methods for creating mock dependencies with sensible defaults. The OpenAI mock correctly mimics the SDK's response structure.

### 2. GOOD: Critical Ordering Test

**Location:** Lines 194-228

```python
def test_telemetry_emitted_after_landscape_recording(self) -> None:
    """Telemetry is emitted AFTER Landscape recording succeeds."""
    ...
    assert call_order == ["landscape", "telemetry"]
```

Verifies the critical ordering invariant.

### 3. GOOD: No-Telemetry-On-Failure Test

**Location:** Lines 345-380

```python
def test_no_telemetry_when_landscape_recording_fails(self) -> None:
    """Telemetry is NOT emitted if Landscape recording fails."""
```

Ensures telemetry is not emitted when audit recording fails.

### 4. GOOD: Telemetry Isolation Test

**Location:** Lines 305-343

```python
def test_telemetry_failure_does_not_corrupt_successful_call(self) -> None:
```

Regression test verifying only one audit record is created even when telemetry fails.

### 5. GOOD: Token Usage Handling

**Location:** Lines 230-270

```python
def test_telemetry_handles_empty_usage(self) -> None:
    """Telemetry emits None token_usage when provider omits usage data."""
```

Tests edge case where LLM provider doesn't return usage data (can happen with streaming).

### 6. GOOD: Multiple Calls Test

**Location:** Lines 272-303

```python
def test_multiple_calls_emit_multiple_events(self) -> None:
    """Each LLM call emits a separate telemetry event."""
```

Verifies that multiple calls emit separate events, not accumulated into one.

### 7. GOOD: Hash Verification

**Location:** Lines 106-109

```python
assert event.request_hash is not None
assert len(event.request_hash) == 64  # SHA-256 hex digest
```

Verifies hash format consistency.

### 8. MISSING COVERAGE: No Test for Streaming Responses

**Severity:** Low
**Location:** N/A

The production code may handle streaming LLM responses differently (indicated by the `usage` handling). There's no test for streaming scenarios.

### 9. EFFICIENCY: Similar Structure to test_http_telemetry.py

**Severity:** Info
**Location:** Throughout

This file mirrors the structure of `test_http_telemetry.py`, which is good for consistency but suggests potential for a shared test base class or fixtures.

## Test Path Integrity

**Status:** PASS

No graph construction involved. Tests LLM client telemetry behavior directly.

## Verdict

**PASS** - Comprehensive telemetry tests with good coverage of ordering, isolation, and edge cases. The test structure is clean and consistent with HTTP client telemetry tests.

## Recommendations

1. Consider adding tests for streaming LLM responses if the client supports them
2. Consider extracting common telemetry test patterns into a shared fixture or base class
3. Consider testing that telemetry event timestamps are reasonable (not in the past, not too far in the future)
