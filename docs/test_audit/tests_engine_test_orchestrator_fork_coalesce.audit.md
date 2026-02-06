# Test Audit: tests/engine/test_orchestrator_fork_coalesce.py

**Lines:** 866
**Test count:** 9
**Audit status:** ISSUES_FOUND

## Summary

This file tests orchestrator fork and coalesce functionality. While it has good coverage of coalesce wiring, several tests rely heavily on mocking internal components (RowProcessor, CoalesceExecutor, SinkExecutor) which tests implementation details rather than behavior. The file contains extensive inline documentation explaining the mock cascades, which is good, but the mocking approach may hide integration bugs.

## Findings

### 🟡 Warning

1. **Lines 246-262: Mock tests implementation details not behavior**
   - `test_orchestrator_creates_coalesce_executor_when_config_present` patches `RowProcessor` and asserts on constructor kwargs (`"coalesce_executor" in call_kwargs`).
   - The test comment (line 246-248) acknowledges this is "SUSPICIOUS" and notes "TODO: Replace with behavior-based test in Phase 5."
   - Impact: Test will pass even if the actual coalesce behavior is broken, as long as the kwarg is passed.

2. **Lines 334-396: Extensive mock cascade for unit test isolation**
   - `test_orchestrator_handles_coalesced_outcome` patches RowProcessor, SinkExecutor, and record_token_outcome.
   - The inline documentation (lines 334-354) explains why, but the test is fragile - any refactoring of internal wiring breaks it.
   - Impact: Maintenance burden; test may not catch real integration issues.

3. **Lines 534-555, 564-599: Similar mock cascade pattern**
   - `test_orchestrator_flush_pending_routes_merged_tokens_to_sink` has similar issues.
   - Documentation is thorough (lines 534-555 explain the mock cascade) but doesn't mitigate the fragility.

4. **Lines 76-83: Test limitation acknowledged but not addressed**
   - Comment notes "Full fork testing at orchestrator level is blocked by ExecutionGraph using DiGraph instead of MultiDiGraph."
   - This architectural limitation means fork behavior is only tested at processor level, leaving an integration gap at orchestrator level.
   - Impact: Orchestrator-level fork handling may have untested edge cases.

5. **Lines 461-469: Legitimate mock usage acknowledged**
   - `test_orchestrator_calls_flush_pending_at_end` correctly uses mock to verify `flush_pending()` is called.
   - This IS appropriate for verifying coordination behavior. Good example of when mocking is justified.

### 🔵 Info

1. **Lines 32-49: Good helper function**
   - `_make_pipeline_row` creates PipelineRow with OBSERVED schema - reduces boilerplate.

2. **Lines 57-73: Reusable test fixture**
   - `CoalesceTestSource` is a configurable source for coalesce tests - good design.

3. **Lines 85-176: Solid behavior test**
   - `test_orchestrator_handles_list_results_from_processor` tests actual behavior (row counting, sink writes) without excessive mocking.

4. **Lines 691-763, 766-866: Good direct testing**
   - `test_orchestrator_computes_coalesce_step_map` and `test_coalesce_step_map_uses_graph_gate_index` call `orchestrator._compute_coalesce_step_map()` directly instead of mocking.
   - These tests verify calculation logic without mock fragility.

5. **Lines 179-469: Good integration coverage references**
   - Multiple comments reference integration tests in `test_coalesce_integration.py`, `test_processor_coalesce.py` that test full behavior.

## Verdict

**KEEP with improvements** - The file provides necessary coverage for coalesce wiring, but several tests are too tightly coupled to implementation details. Recommend:
1. Follow through on the "Phase 5" TODO to replace mock-heavy tests with behavior tests
2. Consider if some tests can use the direct method testing approach (like lines 757, 851)
3. The extensive inline documentation about mock cascades is valuable - keep it
