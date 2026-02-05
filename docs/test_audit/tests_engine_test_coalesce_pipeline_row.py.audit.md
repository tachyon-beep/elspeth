# Test Audit: tests/engine/test_coalesce_pipeline_row.py

**Lines:** 396
**Test count:** 6
**Audit status:** ISSUES_FOUND

## Summary

This test file verifies CoalesceExecutor's handling of PipelineRow objects and contract merging. The tests cover important scenarios including contract merging across branches, crash behavior for missing contracts, and merge policy variations. However, the tests rely heavily on mocks which reduces confidence in integration with real components.

## Findings

### 🟡 Warning

1. **Heavy mocking reduces integration confidence (lines 32-64):**
   All tests use mock `LandscapeRecorder`, `SpanFactory`, and `TokenManager`:
   ```python
   def _make_mock_recorder() -> MagicMock:
       recorder = MagicMock()
       recorder.create_row.return_value = Mock(row_id="row_001")
       ...
   ```
   This means the tests don't verify actual database writes or token management behavior. Given that `test_coalesce_executor_audit_gaps.py` uses real components for similar scenarios, these tests provide lower assurance.

2. **Mock return values may not match real behavior (lines 37-42):**
   ```python
   recorder.coalesce_tokens.return_value = Mock(
       token_id="merged_001",
       join_group_id="join_001",
   )
   ```
   If the real `coalesce_tokens` return type changes (e.g., adds required fields), these tests will continue to pass while production breaks. This is the "mock-drift" problem.

3. **Tests verify mock calls rather than outcomes (lines 156-157, 389):**
   ```python
   token_manager.coalesce_tokens.assert_called_once()
   call_kwargs = token_manager.coalesce_tokens.call_args.kwargs
   ```
   Verifying that a mock was called with certain arguments doesn't prove the system works correctly - it proves the code under test calls its dependencies in a specific way. If the dependency's contract changes, the test won't catch it.

4. **Incomplete coverage of merge strategies:**
   The tests cover `"union"` merge strategy (lines 127, 274, 324, 366) and `"first"` policy (lines 298-344), but don't test:
   - `"nested"` merge strategy
   - `"quorum"` policy
   - `"best_effort"` policy
   These are covered in `test_coalesce_integration.py` but through integration tests, not unit tests of the executor.

### 🔵 Info

1. **Good contract merge verification (lines 70-167):**
   The `test_coalesce_merges_contracts` test properly verifies that fields from both branches appear in the merged contract. This is valuable unit test coverage.

2. **Proper crash behavior test (lines 169-225):**
   `test_coalesce_crashes_if_contract_none` verifies the system crashes (raises `ValueError`) when a token has no contract, which aligns with CLAUDE.md's Tier 1 trust model.

3. **OrchestrationInvariantError test (lines 227-296):**
   `test_coalesce_merge_failure_raises_orchestration_error` correctly verifies that conflicting type contracts (int vs str for same field) raise the appropriate error.

4. **First policy behavior (lines 298-344):**
   The `test_first_policy_merges_immediately` test documents that "first" policy triggers merge on first arrival without waiting for other branches.

5. **Union merge semantics documented (lines 346-396):**
   `test_coalesce_preserves_row_data_correctly` documents that union merge uses "later branches override" semantics for conflicting keys.

## Verdict

**KEEP** - The tests provide useful unit-level coverage of CoalesceExecutor's contract merging logic and error handling. However, consider:
1. Adding integration tests with real components for the specific scenarios tested here (some already exist in `test_coalesce_executor_audit_gaps.py`)
2. The heavy mocking means these tests verify implementation details rather than behavior - they should be considered documentation of expected call patterns rather than strong correctness assurance
3. The overlap with `test_coalesce_executor_audit_gaps.py` (which uses real components) suggests these mock-based tests may be candidates for consolidation
