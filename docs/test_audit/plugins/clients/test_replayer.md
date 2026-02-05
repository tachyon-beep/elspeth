# Test Audit: test_replayer.py

**File:** `/home/john/elspeth-rapid/tests/plugins/clients/test_replayer.py`
**Lines:** 552
**Batch:** 118

## Summary

Tests for `CallReplayer` which replays recorded external calls during replay mode. Covers basic replay, caching, sequence handling for duplicate requests, and error handling for missing/purged payloads.

## Findings

### 1. GOOD: Comprehensive Replay Functionality Tests

**Location:** Lines 73-158 (`TestCallReplayer`)

Tests cover:
- Basic replay returning recorded response
- Correct lookup parameters (run_id, call_type, request_hash, sequence_index)
- ReplayMissError for missing calls
- Cache behavior

### 2. GOOD: Sequence Index Testing for Duplicate Requests

**Location:** Lines 160-202, 480-552

```python
def test_replay_caches_results_per_sequence_index(self) -> None:
def test_duplicate_requests_return_different_responses_in_order(self) -> None:
```

These tests verify the fix for P1-2026-01-21-replay-request-hash-collisions. Critical for correctness when the same request is made multiple times.

### 3. GOOD: Error Call Handling

**Location:** Lines 204-305

```python
def test_replay_handles_error_calls_without_response(self) -> None:
def test_replay_error_call_with_purged_response_raises(self) -> None:
def test_replay_error_call_with_response_succeeds(self) -> None:
```

Tests distinguish between:
- Error calls that never had a response (response_ref=None) - OK to use empty dict
- Error calls that HAD a response but it was purged - must fail

This is critical for replay correctness.

### 4. GOOD: Clear Bug Reference Comments

**Location:** Lines 236-276

```python
"""Error calls that HAD a response but it was purged must fail.

Bug: P2-2026-01-31-replayer-missing-payload-fallback
"""
```

Good practice to reference the bug that motivated the test.

### 5. GOOD: HTTP Call Type Testing

**Location:** Lines 380-412

Tests verify replay works for HTTP calls, not just LLM calls.

### 6. GOOD: Cache Key Separation Testing

**Location:** Lines 414-478

```python
def test_different_call_types_same_hash_are_cached_separately(self) -> None:
```

Verifies that (call_type, request_hash, sequence_index) forms the complete cache key.

### 7. POTENTIAL ISSUE: Mock Recorder Doesn't Validate Call Signatures

**Severity:** Low
**Location:** Lines 76-81

```python
def _create_mock_recorder(self) -> MagicMock:
    recorder = MagicMock()
    recorder.find_call_by_request_hash = MagicMock(return_value=None)
    recorder.get_call_response_data = MagicMock(return_value=None)
    return recorder
```

The mock doesn't validate that the replayer calls methods with correct argument names (kwargs vs positional). However, production code uses kwargs explicitly so this is low risk.

### 8. GOOD: Cache Clear Test

**Location:** Lines 330-352

```python
def test_clear_cache(self) -> None:
    """clear_cache empties the cache."""
```

Tests that clear_cache actually clears both cache and sequence counters.

### 9. MISSING COVERAGE: Thread Safety

**Severity:** Low
**Location:** N/A

The docstring mentions "If used across threads, external synchronization may be needed for the cache." There are no tests verifying thread safety concerns or concurrent access.

## Test Path Integrity

**Status:** PASS

No graph construction involved. Tests the replayer in isolation with mocked recorder.

## Verdict

**PASS** - Excellent test coverage for the replayer including critical bug fixes for duplicate request handling and payload missing scenarios. The tests are well-documented with bug references.

## Recommendations

1. Consider adding a test for cache hit after the first miss (to verify cache is populated on miss)
2. Consider adding thread safety tests if the replayer will be used in multi-threaded contexts
3. Consider testing edge case where sequence_index exceeds recorded calls (4th call when only 3 recorded)
