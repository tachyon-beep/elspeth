# Test Audit: tests/engine/test_orchestrator_phase_events.py

**Lines:** 241
**Test count:** 2
**Audit status:** PASS

## Summary

This file contains focused tests for PhaseError event emission in the Orchestrator. Both tests verify that failures are attributed to the correct pipeline phase (SOURCE vs PROCESS) and that exactly one PhaseError is emitted per failure. The tests use proper production paths via `ExecutionGraph.from_plugin_instances()` and verify both event emission and audit trail recording.

## Findings

### 🔵 Info

1. **Lines 37-152: Comprehensive PROCESS phase failure test**
   - `test_process_failure_emits_single_phase_error` creates a transform that throws RuntimeError.
   - Verifies exactly ONE PhaseError is emitted (not zero, not duplicated).
   - Verifies PhaseError.phase == PipelinePhase.PROCESS (not misattributed to SOURCE).
   - Uses EventBus subscription pattern for event capture - proper testing approach.
   - P1 Fix comment indicates prior issue with missing audit trail verification was addressed.
   - Queries `LandscapeRecorder.list_runs()` to verify audit trail records FAILED status.

2. **Lines 154-240: Comprehensive SOURCE phase failure test**
   - `test_source_failure_emits_source_phase_error` creates a source that throws RuntimeError.
   - Verifies PhaseError.phase == PipelinePhase.SOURCE (critical distinction from PROCESS).
   - Same thorough verification pattern as the PROCESS test.
   - Both tests use `ExecutionGraph.from_plugin_instances()` - production path per CLAUDE.md.

3. **Lines 111-118, 199-206: Good use of production graph construction**
   - Both tests use `ExecutionGraph.from_plugin_instances()` with all required parameters.
   - This follows CLAUDE.md "Test Path Integrity" guidance.

4. **Lines 60-72, 61-72: Inline contract creation in ListSource**
   - Test creates FieldContract/SchemaContract inline for OBSERVED mode.
   - This is appropriate for a test that needs controlled behavior.

### 🟡 Warning

1. **Lines 147-152, 234-240: Module-scoped db workaround noted**
   - Comments indicate tests use `runs[0]` (most recent) due to module-scoped db.
   - This works but could be fragile if test order changes or parallel execution.
   - Consider using function-scoped db for isolation, or capturing run_id before the run.

## Verdict

**KEEP** - These are well-designed tests that verify critical event emission behavior. They use production paths, verify both events and audit trail, and have clear documentation. The module-scoped db workaround is acceptable given the comments explaining the approach.
