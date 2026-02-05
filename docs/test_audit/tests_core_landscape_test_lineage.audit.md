# Test Audit: tests/core/landscape/test_lineage.py

**Lines:** 653
**Test count:** 16
**Audit status:** ISSUES_FOUND

## Summary

This test file provides comprehensive coverage of the `explain()` lineage query functionality, including fork disambiguation, sink routing, and critical audit integrity checks. Most tests follow good patterns with real database setup (LandscapeDB.in_memory()) rather than mocking. However, there are two tests at the end that test for expected behavior that may not be implemented yet, and some tests have redundant imports.

## Findings

### 🟡 Warning

1. **Lines 516-599**: `test_explain_crashes_on_missing_parent_token` directly manipulates the database to simulate corruption by disabling FK constraints and deleting a parent token. While this tests an important audit integrity requirement, the test relies on SQLite-specific `PRAGMA foreign_keys = OFF` which may not work on other databases. This creates a portability concern if the codebase ever supports other backends.

2. **Lines 601-653**: `test_explain_crashes_on_token_with_group_id_but_no_parents` manually updates the database to set `fork_group_id` without creating parent relationships. The test expects explain() to raise `ValueError` with a specific message pattern (`fork_group_id.*no parent|missing parent.*fork`). If this validation is not implemented in `explain()`, this test will fail. Need to verify this behavior exists in production code.

3. **Lines 202-214**: `test_explain_requires_token_or_row_id` imports `pytest` inside the test method rather than using the module-level import. This is inconsistent with other tests in the file (lines 271-273 also do this).

### 🔵 Info

1. **Line 9**: `DYNAMIC_SCHEMA = SchemaConfig.from_dict({"mode": "observed"})` is a good pattern - creating a reusable test constant rather than repeating the schema setup in each test.

2. **Lines 62-95**: `test_explain_returns_lineage_result` is a well-structured integration test that sets up a complete minimal run with source, row, and token, then verifies the lineage query returns correct data.

3. **Lines 97-200**: `test_explain_returns_complete_audit_trail` is a thorough P1-priority test that verifies all audit trail fields are populated (node_states, calls, outcome). This is exactly the kind of high-value test that ensures audit integrity.

4. **Lines 271-331**: The fork disambiguation tests (`test_explain_fork_with_sink_disambiguation`) properly test the scenario where a row forks to multiple sinks and explain() must disambiguate or raise an error.

5. **Lines 415-469**: `test_explain_buffered_tokens_returns_none` correctly tests that non-terminal (BUFFERED) tokens return None from explain(), which is the expected behavior per the DAG execution model.

## Verdict

**KEEP** - This is a high-value test file that thoroughly tests the lineage query functionality including critical audit integrity scenarios. The warnings about database manipulation tests are noted but these tests are testing real edge cases that matter for audit integrity. The file would benefit from consolidating imports at module level for consistency, but this does not affect test validity. The tests covering "crashes on missing parent" scenarios are particularly valuable as they enforce the CLAUDE.md Tier 1 trust model.
