# Test Audit: tests/engine/test_coalesce_executor.py

**Lines:** 1915
**Test count:** 22 test functions across 12 test classes
**Audit status:** PASS

## Summary

This is a comprehensive test suite for the CoalesceExecutor, covering all coalesce policies (require_all, first, quorum, best_effort), merge strategies (union, nested, select), timeout handling, audit trail recording, and edge cases like duplicate branch detection and late arrivals. The tests use proper fixtures, document known bugs with clear assertions, and verify both happy paths and failure modes. The code structure is clean with good use of pytest fixtures and parametrization.

## Findings

### 🟡 Warning

1. **Direct Access to Private `_pending` Field (Lines 1539, 1671)** - Tests verify internal state by accessing `executor._pending` directly:
   ```python
   key = ("quorum_merge", token_a.row_id)
   assert key not in executor._pending
   ```
   While this is testing important cleanup behavior, it couples tests to implementation details. Consider adding a public method like `has_pending_coalesce(name, row_id)` if this needs to be verified.

2. **Direct Access to Private `_recorder` Field (Lines 632, 723, 750)** - Tests access `executor._recorder` to verify audit trail:
   ```python
   node_states = executor._recorder.get_node_states_for_token(token.token_id)
   ```
   The recorder is injected via constructor, so this could be accessed through the test's `recorder` fixture instead.

3. **Large Test Class `TestFlushPending` (Lines 1089-1307)** - The parametrized test `test_flush_pending_policy_behavior` is well-structured but the parameter combinations and assertions are complex enough that individual test cases might be clearer.

### 🔵 Info

1. **Excellent Fixture Design** - The `coalesce_setup` fixture (Lines 82-171) is a well-designed factory fixture that reduces boilerplate while allowing test-specific configuration. Each test can customize policy, branches, timeout, and clock.

2. **Good Bug Documentation Pattern** - Tests for known bugs (x5a, 6tb, 2ho, l4h) include:
   - Clear class-level docstrings explaining current vs expected behavior
   - Detailed test docstrings explaining the scenario and why it matters
   - Assertion messages that explain what's wrong if the test fails

3. **Proper Audit Trail Verification** - Tests thoroughly verify:
   - node_states for consumed tokens (status, input_hash, output_hash)
   - token_outcomes (COALESCED, FAILED)
   - token_parents lineage for merged tokens
   - context_after_json for coalesce metadata

4. **Good Edge Case Coverage** - Tests cover:
   - Late arrivals after merge (Gap #2 fix)
   - Held tokens audit trail (Gap #1 fix)
   - Duplicate branch detection (bug x5a)
   - Timeout failure recording (bug 6tb)
   - Select branch validation (bug 2ho)
   - Metadata persistence (bug l4h)

5. **MockClock Usage** - Tests that involve timeouts properly use `MockClock` for deterministic timing, avoiding flaky tests.

6. **Test Class Organization** - Classes are well-organized by policy/feature:
   - `TestCoalesceExecutorInit`
   - `TestCoalesceExecutorRequireAll`
   - `TestCoalesceExecutorFirst`
   - `TestCoalesceExecutorQuorum`
   - `TestCoalesceExecutorBestEffort`
   - `TestCoalesceAuditMetadata`
   - `TestCoalesceIntegration`
   - `TestFlushPending`
   - `TestDuplicateBranchDetection`
   - `TestTimeoutFailureRecording`
   - `TestSelectBranchValidation`
   - `TestCoalesceMetadataRecording`

7. **Helper Functions** - `_make_pipeline_row` and `_make_source_row` (Lines 21-47) are clean utilities for creating test data with proper contracts.

## Verdict

**KEEP** - This is a high-quality test suite that provides comprehensive coverage of the CoalesceExecutor's complex behavior. The tests are well-documented, properly structured, and verify critical audit trail invariants. The minor issues with private field access are acceptable tradeoffs for verifying important internal state. The bug documentation tests serve as living documentation and regression protection.
