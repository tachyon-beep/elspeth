# Audit: tests/telemetry/exporters/test_datadog_integration.py

## Summary
**Lines:** 433
**Test Classes:** 3 (Integration, SpanFormat, MultipleEvents)
**Quality:** GOOD - Real ddtrace integration with proper span capture

## Findings

### Strengths

1. **Real Library Integration** (Lines 29-63)
   - Uses `pytest.importorskip` for optional dependency
   - Patches `ddtrace.tracer.start_span` to capture real spans
   - Restores original in fixture teardown
   - Tests actual ddtrace behavior, not mocks

2. **Internal Structure Access** (Lines 99, 147-150, 168, 237)
   - Accesses `span._meta` for string tags
   - Accesses `span._metrics` for numeric tags (Lines 314-320)
   - Documents ddtrace's internal storage separation

3. **Timestamp Verification** (Lines 110-130)
   - Verifies `span.start_ns` matches event timestamp exactly
   - Critical for audit trail accuracy

4. **Dict Flattening Verification** (Lines 292-320)
   - Tests that nested dicts become dotted tags
   - Correctly checks `_metrics` for numeric values

5. **Multiple Event Ordering** (Lines 353-433)
   - Tests 5 events create 5 separate spans
   - Tests event type names are preserved

### Minor Issues

1. **Fixture Not Cleaning Up** (Lines 39-49)
   - Uses global tracer modification
   - Could affect other tests if run in same process
   - `captured_spans` fixture doesn't use proper context manager

2. **Zero Duration Assertion** (Line 272)
   - Tests `span.duration_ns == 0` for instant spans
   - This is correct but relies on implementation detail

### Missing Coverage

1. **Agent Connection Failure**
   - No tests for behavior when Datadog agent is unreachable
   - Integration tests note "spans fail to send but that's expected"
   - Could add explicit test for graceful degradation

2. **Numeric Tag Storage** (Line 148)
   - `tags = dict(span._meta)` only gets string tags
   - numeric metrics tested separately but some tests might miss numeric values

## Verdict
**PASS** - Good integration tests that verify real ddtrace behavior. The global tracer modification in fixtures could be improved but works correctly.
