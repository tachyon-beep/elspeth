# Test Audit: tests/engine/test_orchestrator_resume.py

**Lines:** 1017
**Test count:** 7
**Audit status:** ISSUES_FOUND

## Summary

This test file covers the orchestrator resume workflow comprehensively with two test classes: `TestOrchestratorResumeRowProcessing` (5 tests) and `TestOrchestratorResumeCleanup` (2 tests). The tests use real database operations and proper fixtures with meaningful assertions. However, there is significant code duplication between fixtures that could be consolidated, and the manual graph construction pattern is used extensively which deviates from the production code path.

## Findings

### 🟡 Warning

1. **Manual Graph Construction (Lines 254-268, 739-750, 965-976)**: The tests manually construct `ExecutionGraph` with direct assignment to internal attributes (`_sink_id_map`, `_transform_id_map`, `_config_gate_id_map`, `_route_resolution_map`, `_default_sink`). Per CLAUDE.md "Test Path Integrity" section, this bypasses the production `ExecutionGraph.from_plugin_instances()` path and could hide bugs in the production graph construction logic. However, for resume tests this may be intentional since the graph must match existing database entries.

2. **Heavy Fixture Duplication (Lines 536-563 vs 42-68)**: The `TestOrchestratorResumeCleanup` class duplicates all fixtures from `TestOrchestratorResumeRowProcessing` (`landscape_db`, `payload_store`, `checkpoint_manager`, `recovery_manager`, `orchestrator`). These could be extracted to a common base or module-level fixtures.

3. **Large Fixture Setup (Lines 71-285)**: The `failed_run_with_payloads` fixture is 214 lines long and performs extensive manual database setup. While comprehensive, this complexity makes it harder to understand what the test is actually verifying. Consider breaking into smaller helper functions.

4. **Duplicate Inline Imports (Lines 227-228, 578-579, 719, 766-767, 808-809, 989-990)**: Multiple tests import the same modules inline (e.g., `SchemaContract`, `FieldContract`, `JSONSink`, `NullSource`) within test functions. These should be at module level.

### 🔵 Info

1. **Good P1/P2/P3 Bug Fix Documentation**: Tests include explicit references to bug fixes they verify (P1 audit trail fix at line 477, P2 exact value assertion fix at line 439, P3 cleanup fix at line 575), providing excellent traceability.

2. **Production Plugin Usage**: Tests use real plugins (`NullSource`, `PassThrough`, `JSONSink`) rather than mocks for the actual pipeline execution, which is good practice for integration tests.

3. **Thorough Audit Trail Verification (Lines 503-527)**: The `test_resume_creates_audit_trail_for_resumed_tokens` test properly verifies that both `node_states` and `token_outcomes` are created for resumed rows.

4. **Edge Case Coverage**: The `test_transform_close_called_when_on_complete_fails` test (lines 794-1016) verifies cleanup behavior when `on_complete()` raises an exception, ensuring `close()` is still called.

## Verdict

**KEEP** - The tests provide valuable coverage of the resume workflow with proper integration testing. The manual graph construction is justified for resume tests that must match existing database state. The duplication and large fixtures are maintenance concerns but don't undermine test validity. Consider refactoring fixtures in a future cleanup pass.
