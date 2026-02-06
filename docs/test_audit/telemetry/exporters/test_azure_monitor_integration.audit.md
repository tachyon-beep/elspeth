# Audit: tests/telemetry/exporters/test_azure_monitor_integration.py

## Summary
**Lines:** 331
**Test Classes:** 2 (Integration, SpanFormat)
**Quality:** GOOD - Real SDK integration tests with mocked transport

## Findings

### Strengths

1. **Proper Integration Test Design** (Lines 28-66)
   - Uses `pytest.importorskip` to skip if Azure SDK not installed
   - Uses real SDK but mocks HTTP transport to capture spans
   - Tests the actual span conversion path

2. **Trace Context Correlation Testing** (Lines 148-179)
   - Verifies same run_id produces same trace_id
   - Critical for distributed tracing correlation in App Insights

3. **Batching Behavior Tests** (Lines 181-246)
   - Tests batch accumulation and flush
   - Tests partial batch flush
   - Good coverage of buffering semantics

4. **Span Format Verification** (Lines 249-331)
   - Tests span context validity
   - Tests timestamp nanosecond precision
   - Tests None value exclusion

### Minor Issues

1. **Duplicate Type Comments** (Lines 196, 227, 268)
   - `# type: ignore[method-assign,union-attr]  # type: ignore[method-assign,union-attr]`
   - Harmless but indicates copy-paste

2. **Assertion Weakening** (Line 331)
   - `assert "sink_name" not in span.attributes or span.attributes.get("sink_name") is None`
   - Disjunction allows two possible behaviors - should be explicit about expected behavior

### Missing Coverage

1. **Error Response Handling**
   - No tests for what happens when SDK returns SpanExportResult.FAILURE
   - The capture_export always returns SUCCESS

2. **Connection String Validation**
   - Uses dummy connection string format but doesn't test SDK's reaction to malformed strings

## Verdict
**PASS** - Good integration test coverage with real SDK. The duplicate type comments should be cleaned up.
