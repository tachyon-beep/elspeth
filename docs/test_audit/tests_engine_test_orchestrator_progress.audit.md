# Test Audit: tests/engine/test_orchestrator_progress.py

**Lines:** 377
**Test count:** 4
**Audit status:** PASS

## Summary

This file contains tests for the Orchestrator's progress callback functionality. Tests verify progress events are emitted at correct intervals (every 100 rows), handle edge cases (quarantined rows, routed rows), and work correctly when no callback is provided. Tests use production paths via `build_production_graph()` helper and properly capture events via EventBus subscription.

## Findings

### 🔵 Info

1. **Lines 44-133: Thorough progress interval test**
   - `test_progress_callback_called_every_100_rows` creates a 250-row source.
   - Verifies checkpoints at rows 1, 100, 200, 250.
   - P1 Fix comment notes relaxed assertions due to time-based events on slow machines.
   - Verifies monotonically increasing rows_processed and elapsed_seconds.
   - Good defensive testing - doesn't assume exact count, just required checkpoints.

2. **Lines 135-178: Proper null safety test**
   - `test_progress_callback_not_called_when_none` verifies no crash without EventBus.
   - Correctly tests that orchestrator handles missing callback gracefully.

3. **Lines 180-272: Important regression test for quarantine boundary**
   - `test_progress_callback_fires_for_quarantined_rows` tests that quarantined rows still trigger progress.
   - Documents specific regression: progress emission was after quarantine continue statement.
   - Verifies quarantine counts in progress events at specific checkpoints.

4. **Lines 274-376: Important regression test for routed rows**
   - `test_progress_callback_includes_routed_rows_in_success` tests routed rows count as succeeded.
   - Documents specific regression: routed rows weren't included in rows_succeeded.
   - Uses config-driven gate (GateSettings) for routing - proper production approach.
   - Verifies routed_sink received rows while default_sink did not.

5. **Lines 26-38: Good helper function**
   - `_make_observed_contract()` reduces boilerplate for creating test contracts.
   - Used consistently across all tests.

### 🟡 Warning

1. **Lines 55-68, 146-153, 196-212, 287-299: Repeated source definitions**
   - Multiple test-local source classes with similar patterns.
   - Could potentially be parameterized or extracted to reduce duplication.
   - Not a defect but adds maintenance burden.

2. **Lines 108-120: Time-based test fragility acknowledged**
   - Test explicitly notes 5-second interval events can cause extra events.
   - Assertions are appropriately relaxed (`>= 4` instead of exact count).
   - Good approach but indicates underlying timing complexity.

## Verdict

**KEEP** - These tests verify important progress reporting functionality with good regression test coverage. The tests properly handle timing variability and verify both expected checkpoints and event ordering. The duplicate source definitions are a minor maintenance concern but don't affect test validity.
