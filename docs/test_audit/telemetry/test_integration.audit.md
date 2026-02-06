# Audit: tests/telemetry/test_integration.py

## Summary
**Lines:** 886
**Test Classes:** 7 (LandscapeAlignment, TelemetryOrdering, Granularity, FailureIsolation, TotalFailure, HighVolume, ManagerLifecycle)
**Quality:** EXCELLENT - Comprehensive end-to-end integration tests

## Findings

### Strengths

1. **Telemetry-Landscape Ordering** (Lines 294-408)
   - **CRITICAL REGRESSION TEST** (Lines 297-329): No RunStarted if begin_run fails
   - Verifies telemetry only emitted AFTER Landscape success
   - Tests failed run still emits RunFinished with FAILED status
   - Documents audit integrity requirement

2. **Granularity Filtering** (Lines 415-494)
   - Tests LIFECYCLE only emits lifecycle events
   - Tests ROWS includes row events
   - Tests FULL includes all events
   - Uses real pipeline execution

3. **Exporter Failure Isolation** (Lines 502-588)
   - Tests one failing exporter doesn't block others
   - Tests all exporters receive same events
   - Tests partial success counts as emitted

4. **Total Failure Handling** (Lines 606-714)
   - Tests fail_on_total_exporter_failure=True raises after threshold
   - Tests fail_on_total_exporter_failure=False disables telemetry
   - Documents 10-consecutive-failure threshold
   - Verifies disabled state is sticky

5. **High-Volume Stress Testing** (Lines 722-829)
   - Tests 10,000 events without memory issues
   - Tests granularity filter reduces memory for high-throughput
   - Tests metrics accuracy after high-volume

6. **Test Infrastructure** (Lines 54-213)
   - `MockTelemetryConfig` - minimal config for testing
   - `RecordingExporter` - captures events for verification
   - `FailingExporter` - simulates failures with configurable count
   - `ListSource`, `CollectingSink` - minimal pipeline components

### Minor Issues

1. **Module-Scoped Database** (Lines 216-219)
   - `@pytest.fixture(scope="module")` for landscape_db
   - Could cause test pollution if tests don't clean up
   - Works because each run gets unique run_id

2. **Patch Logger** (Lines 524, 582, 628, etc.)
   - `patch("elspeth.telemetry.manager.logger")` to suppress warnings
   - Could mask unexpected log messages during failures
   - Acceptable for expected failure scenarios

### Potential Improvement

1. **Test Class Naming** (Lines 227, 294, 415, 502, 606, 722, 837)
   - Very descriptive names but inconsistent with other test files
   - e.g., `TestTelemetryEmittedAlongsideLandscape` vs typical `TestTelemetryIntegration`
   - Not a bug, just style note

### Excellent Documentation

Every test class has a docstring explaining:
- What is being tested
- Why it matters
- Expected behavior

## Verdict
**PASS** - Outstanding integration test suite. The telemetry ordering tests are particularly critical for audit integrity.
