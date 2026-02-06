# Test Audit: tests/integration/test_chaosllm_server.py

**Auditor:** Claude
**Date:** 2026-02-05
**Lines:** 641
**Batch:** 96

## Summary

This file contains integration tests for the ChaosLLM server, a fake LLM server used for testing. The tests exercise error injection, response modes, admin endpoints, metrics recording, and burst patterns through a pytest fixture.

## Findings

### 1. STRENGTH: Well-Structured and Comprehensive Test Suite

The test file is well-organized into logical test classes covering:
- Basic functionality (health check, response formats)
- Error injection (429, 503, 502, 504, 500 errors)
- Malformed responses (invalid JSON, truncated, empty body)
- Response modes (random, template, echo)
- Admin endpoints (stats, config, export, reset)
- Metrics recording
- Burst patterns
- Runtime configuration updates
- Fixture isolation verification

**Verdict:** No action needed - good organization.

### 2. STRENGTH: Proper Fixture Isolation Testing

Lines 568-592 explicitly test that the fixture provides clean state between tests:
- `test_isolation_part_1_make_requests` - creates state
- `test_isolation_part_2_verify_clean_state` - verifies clean
- `test_isolation_part_3_with_marker` - tests with marker config
- `test_isolation_part_4_marker_not_inherited` - verifies marker isolation

**Verdict:** Excellent practice for integration test fixtures.

### 3. POTENTIAL ISSUE: Database Connection Not Closed (Minor)

Lines 426-438 and 465-471 open SQLite connections directly with `sqlite3.connect()` and use context manager, but they don't explicitly verify the database path exists before querying:

```python
db_path = chaosllm_server.metrics_db
with sqlite3.connect(str(db_path)) as conn:
    # ...
```

If `metrics_db` property returns `None` or invalid path, this could cause confusing errors.

**Severity:** Low
**Recommendation:** Add assertion that `db_path` exists before querying, or trust the fixture setup.

### 4. STRENGTH: Marker-Based Configuration

The tests use `@pytest.mark.chaosllm(...)` decorators to configure the server per-test (lines 93, 111, 126, etc.), which is a clean pattern for varying test conditions without boilerplate.

### 5. MINOR: Assertion Order in Malformed Response Tests

Lines 163-175 test invalid JSON response:
```python
with pytest.raises(json.JSONDecodeError):
    response.json()

# Verify content is malformed
assert b"malformed" in response.content or b"unclosed" in response.content
```

The assertion after the `pytest.raises` block only runs if the exception was raised. If `response.json()` unexpectedly succeeds, the test fails but the malformed content assertion never runs. This is acceptable behavior for testing.

**Verdict:** No action needed.

### 6. MISSING COVERAGE: No Test for Concurrent Requests

The tests are all synchronous and single-threaded. There's no test verifying that the ChaosLLM server handles concurrent requests correctly. For a fake server used in integration tests, this might matter if tests use threading/async.

**Severity:** Low
**Recommendation:** Consider adding a test that makes multiple concurrent requests.

### 7. NO TEST PATH INTEGRITY VIOLATIONS

This test file tests the ChaosLLM server, not the ELSPETH pipeline engine. There's no graph construction or `ExecutionGraph` usage, so test path integrity concerns don't apply here.

## Test Class Discovery

All test classes have the `Test` prefix:
- `TestBasicFunctionality`
- `TestErrorInjection`
- `TestMalformedResponses`
- `TestResponseModes`
- `TestAdminEndpoints`
- `TestMetricsRecording`
- `TestBurstPatterns`
- `TestRuntimeConfigurationUpdates`
- `TestFixtureIsolation`
- `TestWaitForRequests`
- `TestMultipleErrorTypes`

**Verdict:** All classes will be discovered by pytest.

## Overall Assessment

**Quality:** HIGH

This is a well-written integration test suite. The tests:
- Cover comprehensive functionality
- Use proper assertions
- Test both happy and error paths
- Verify fixture isolation
- Use clean marker-based configuration

No critical issues found. Minor recommendations for database path validation and concurrent testing are optional enhancements.

## Recommendations

1. **Optional:** Add assertion that `metrics_db` path exists before direct SQL queries
2. **Optional:** Add concurrent request test if threading support is needed
3. No refactoring required
