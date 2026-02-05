# Test Audit: tests/core/landscape/test_recorder_artifacts.py

**Lines:** 341
**Test count:** 9
**Audit status:** PASS

## Summary

This test file provides solid coverage of artifact registration and query operations in the LandscapeRecorder. Tests are well-structured with clear setup, action, and assertion phases. The regression tests for idempotency_key handling (P2-2026-01-20) are particularly valuable for audit integrity.

## Findings

### 🔵 Info

1. **Lines 16-59, 60-111, etc.: Repetitive setup code** - Each test method manually imports and sets up LandscapeDB and LandscapeRecorder. Unlike the batch tests file which uses fixtures, this file duplicates setup code across all tests. Consider using a shared fixture for consistency with other test files in this module.

2. **Lines 227-254, 256-289, 291-341: Mixed concerns in single test class** - The `TestLandscapeRecorderArtifacts` class contains tests for artifacts, rows, tokens, and node states. The class name suggests artifact focus but includes unrelated query tests (`test_get_rows_for_run`, `test_get_tokens_for_row`, `test_get_node_states_for_token`). These would be better organized in separate test classes.

3. **Lines 112-176: Excellent regression test coverage** - The idempotency_key tests (`test_register_artifact_with_idempotency_key`, `test_register_artifact_without_idempotency_key_returns_none`) reference the specific bug ticket (P2-2026-01-20) and test both the presence and absence cases. This is high-quality regression testing.

4. **Lines 280-285: Unused variables** - In `test_get_tokens_for_row`, the `_children` and `_fork_group_id` variables are returned from `fork_token()` but explicitly marked as unused. This is appropriate - the test cares about the database state (token count), not the return values.

## Verdict

**KEEP** - Tests are meaningful, provide good coverage of artifact operations, and include valuable regression tests. The minor structural issues (repetitive setup, mixed concerns) do not affect test quality or correctness. The tests verify actual database persistence and query behavior rather than just return values.
