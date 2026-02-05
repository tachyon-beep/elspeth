# Test Bug Report: Fix weak assertions in explain_tui

## Summary

- This test file provides comprehensive coverage of the ExplainScreen TUI component, including state machine transitions, database integration, and widget composition. The tests are well-structured with clear test names and proper assertions. However, there are several issues including overmocking of internal methods, some weak assertions, and a few tests that could be more thorough.

## Severity

- Severity: trivial
- Priority: P2
- Verdict: **KEEP**

## Reporter

- Name or handle: Test Audit
- Date: 2026-02-06
- Audit file: docs/test_audit/tests_cli_test_explain_tui.py.audit.md

## Test File

- **File:** `tests/cli/test_explain_tui.py`
- **Lines:** 686
- **Test count:** 28

## Findings

- **Line 22-26:**: `test_can_import_screen` - This test only verifies that a class can be imported and is not None. This is a tautological test - if the import failed, the test file itself would fail to load. Provides no meaningful coverage.
- **Line 154:**: `test_render_without_data` - The assertion `"No node selected" in content or "Select a node" in content` is an OR condition that weakens the test. The test doesn't know what message should actually appear, suggesting incomplete specification or test uncertainty.
- **Line 291-303:**: `test_loading_failed_state_on_db_error` and `test_loading_failed_state_preserves_db_for_retry` (lines 305-324) - These tests mock `LandscapeRecorder.get_nodes` at the class level, which may interfere with the actual initialization logic. The test should ideally trigger a real database error or use a more targeted mock. However, the pattern is acceptable for testing error paths.
- **Line 367-376:**: `test_load_from_uninitialized_fails_gracefully` - The assertion `"Network timeout" in screen.state.error` verifies the mock's error message appears in output. While this confirms error propagation, it's partially testing the mock rather than real database error handling.
- **Lines 56-68:**: `test_screen_initializes_with_db` - The test creates a recorder and run but doesn't use the recorder variable. The recorder is only needed to create the run, which is fine, but naming could be clearer (e.g., a comment explaining the setup).
- **Lines 111-144:**: `test_tree_selection_updates_detail_panel` - Well-structured test with clear setup, action, and verification. Good use of explicit assertions with descriptive messages.
- **Lines 189-276:**: `TestExplainScreenStateModel` - Good use of discriminated union pattern testing with exhaustive matching. The tests properly verify state transitions and error conditions.
- **Lines 327-685:**: `TestExplainScreenStateTransitions` - Excellent coverage of state machine transitions including happy path, error paths, and complex transition sequences. The explicit type annotations to break mypy's type narrowing (lines 352, 458, 549, 574, 678, 684) are a good practice.
- **Line 577-586:**: `test_clear_from_uninitialized_is_idempotent` - Good edge case coverage for idempotent operations.


## Verdict Detail

**KEEP** - This test file provides solid coverage of the ExplainScreen component's state machine and integration with the database. The import test should be removed as it adds no value, and the OR-condition assertion should be tightened. Overall, the tests are well-structured and follow good patterns for testing stateful components.

## Proposed Fix

- [ ] Weak assertions strengthened
- [ ] Redundant tests consolidated
- [ ] Test intent clearly expressed in assertions

## Tests

- Run after fix: `.venv/bin/python -m pytest tests/cli/test_explain_tui.py -v`

## Notes

- Source audit: `docs/test_audit/tests_cli_test_explain_tui.py.audit.md`
