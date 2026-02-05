# Test Audit: tests/engine/test_orchestrator_telemetry.py

**Lines:** 729
**Test count:** 16
**Audit status:** ISSUES_FOUND

## Summary

This test file provides comprehensive coverage of telemetry event emission in the Orchestrator across seven test classes. Tests verify event ordering, content, emission conditions, and integration with the Landscape audit trail. The tests use a clean `RecordingExporter` pattern to capture events for verification. However, some tests make claims about code structure in comments rather than verifying behavior, and there is manual graph construction that bypasses production paths.

## Findings

### 🟡 Warning

1. **Manual Graph Construction (Lines 99-111)**: The `create_minimal_graph()` helper manually constructs `ExecutionGraph` with direct internal attribute assignment (`_transform_id_map`, `_sink_id_map`, `_default_sink`). This bypasses `ExecutionGraph.from_plugin_instances()` and could hide graph construction bugs. For telemetry tests, the graph structure matters less, but this pattern should be noted.

2. **Comment-Based Code Structure Claims (Lines 314-349, 351-379)**: Tests `test_no_run_started_if_begin_run_fails` and `test_no_run_completed_if_finalize_fails` make claims in comments about code line numbers and structure (e.g., "line ~549-553", "line ~557-566") rather than actually testing the failure scenarios. These tests run the happy path and assert that telemetry was emitted, then rely on comments to explain why failures would prevent emission. This is fragile because:
   - Code line numbers change during refactoring
   - The actual failure scenarios are not tested
   - The tests don't verify the failure behavior they claim to document

3. **Mock Source Creation Pattern (Lines 114-149)**: The `create_mock_source()` helper uses `MagicMock` extensively rather than real source plugins. While appropriate for some telemetry tests, this reduces confidence that telemetry works with actual plugins.

4. **Duplicate Contract Creation Code (Lines 128-143, 409-422)**: Schema contract creation is duplicated in `create_mock_source()` and in `test_run_completed_emitted_with_failed_status`. This could be extracted to a helper.

### 🔵 Info

1. **Good Recording Exporter Pattern (Lines 75-96)**: The `RecordingExporter` class provides a clean way to capture telemetry events for test verification without mocking.

2. **Comprehensive Event Type Coverage**: Tests verify `RunStarted`, `RunFinished`, `PhaseChanged`, and `RowCreated` events across various scenarios.

3. **Correct Phase Verification (Lines 223-247)**: The test `test_phase_changed_events_emitted_for_all_phases` verifies that GRAPH, SOURCE, and PROCESS phases are all emitted.

4. **Event Order Verification (Lines 249-267)**: The test `test_events_emitted_in_correct_order` verifies that `RunStarted` is first and `RunFinished` is last.

5. **Consistent run_id Verification (Lines 492-510)**: The test `test_all_events_share_same_run_id` verifies that all events from a single run share the same `run_id`.

6. **RowCreated for Quarantined Rows (Lines 528-601)**: The test `test_row_created_emitted_for_quarantined_row` uses real source plugins (`QuarantiningSource`) and `build_production_graph()`, following good practices.

7. **Export Failure Handling (Lines 670-728)**: The test `test_run_finished_emitted_when_export_fails` verifies that telemetry emission happens before export, so export failures don't prevent telemetry.

8. **Granularity and Config Coverage (Lines 58-73)**: The `MockTelemetryConfig` properly implements `RuntimeTelemetryProtocol` for testing.

### 🔴 Critical

1. **Tests Don't Actually Test Failure Scenarios (Lines 314-379)**: The `TestNoTelemetryOnLandscapeFailure` class name suggests it tests that no telemetry is emitted when Landscape fails, but the tests only verify the happy path. The actual failure scenario (e.g., `begin_run` raising an exception) is not tested - the tests just run successfully and make claims in comments. To properly test this, the tests would need to mock `recorder.begin_run()` to raise an exception and verify no telemetry was emitted. This is a gap in test coverage.

## Verdict

**KEEP** - The tests provide valuable coverage of telemetry emission, but the `TestNoTelemetryOnLandscapeFailure` tests should be strengthened to actually test the failure scenarios rather than relying on code structure claims in comments. The manual graph construction is acceptable for unit-style telemetry tests. Consider adding tests that mock Landscape failures to verify telemetry is not emitted.
