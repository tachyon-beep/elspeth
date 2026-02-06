# Test Audit: test_orchestrator_phase_events.py

## File Information
- **Path:** `/home/john/elspeth-rapid/tests/engine/test_orchestrator_phase_events.py`
- **Lines:** 241
- **Tests:** 2
- **Audit:** PASS

## Summary

This test file verifies that `PhaseError` events are emitted correctly during orchestrator failures, distinguishing between SOURCE phase and PROCESS phase failures. Tests use production code paths via `ExecutionGraph.from_plugin_instances()` and properly inherit from base test classes. The assertions are strong and verify both event emission and audit trail recording.

## Test Inventory

| Test | Purpose | Production Path |
|------|---------|-----------------|
| `test_process_failure_emits_single_phase_error` | Verifies PROCESS phase failures emit exactly one PhaseError(PROCESS) | Yes |
| `test_source_failure_emits_source_phase_error` | Verifies SOURCE phase failures emit PhaseError(SOURCE), not PROCESS | Yes |

## Findings

### Strengths

1. **Production Code Path Compliance (Lines 111-118, 199-206):** Both tests use `ExecutionGraph.from_plugin_instances()` correctly, avoiding manual graph construction.

2. **Strong Assertions:** Tests verify:
   - Exactly one PhaseError is emitted (lines 142, 230)
   - The correct phase is attributed (lines 143, 231)
   - Error message content is captured (lines 144, 232)
   - Audit trail records run as FAILED (lines 152-153, 239-240)

3. **Proper Test Plugin Design:** Test plugins inherit from `_TestSourceBase`, `_TestSinkBase`, and `BaseTransform` (line 77), satisfying the isinstance() checks in the processor.

4. **Regression Prevention:** The test specifically guards against the P1 bug where failures could emit duplicate PhaseError events or attribute to wrong phase.

### Minor Observations

1. **Repeated Plugin Boilerplate (Lines 47-103 vs 161-192):** The `CollectSink` class is defined identically in both tests. This could be extracted, but given only 2 tests, the duplication is acceptable.

2. **Comment at Line 147:** The comment about "module-scoped db" references the fixture `landscape_db` from conftest, but the behavior relies on `list_runs()` returning newest first. This assumption is correct per the recorder implementation.

## Verdict

**PASS** - Well-designed tests that use production code paths, have strong assertions, and properly verify both event emission and audit trail integrity. No defects found.
