# Test Audit: tests/engine/test_coalesce_integration.py

**Lines:** 1187
**Test count:** 11
**Audit status:** ISSUES_FOUND

## Summary

This is a comprehensive integration test file that exercises fork/coalesce pipelines through the production code path using `build_production_graph()`. The tests are well-structured and follow the CLAUDE.md requirement to avoid manual graph construction. However, there are some issues with overmocking via `hasattr()` checks, module-scoped fixtures that may cause test pollution, and one potentially brittle timing-based test.

## Findings

### 🟡 Warning

1. **Module-scoped LandscapeDB fixture may cause test pollution (lines 55-58):**
   ```python
   @pytest.fixture(scope="module")
   def landscape_db() -> LandscapeDB:
       """Module-scoped in-memory database for coalesce integration tests."""
       return LandscapeDB.in_memory()
   ```
   All tests in this module share the same database instance. While tests filter by `run_id`, accumulated data could affect performance or cause subtle issues if any test relies on database being empty. Consider using function scope or explicitly clearing between tests.

2. **Defensive hasattr() check violates CLAUDE.md (lines 515-516):**
   ```python
   row_dict = row.to_dict() if hasattr(row, "to_dict") else row
   ```
   Per CLAUDE.md prohibition on defensive programming patterns: if `row` doesn't have `to_dict()`, that's a bug to fix, not a condition to handle silently. The test should call `row.to_dict()` directly.

3. **Timing-dependent test with real sleep (lines 772-967):**
   The `test_best_effort_timeout_merges_during_processing` test uses `time.sleep(0.25)` in the source and asserts on total duration. This is fragile:
   - Can fail on slow CI runners
   - Comments (lines 879-898) indicate confusion about what the test is actually verifying
   - The test essentially verifies that processing completes in <0.5s, but doesn't definitively prove `check_timeouts()` is called during processing vs at end-of-source

4. **Unused variable in source class (line 797):**
   `SlowSource.__init__` calls `super().__init__()` but doesn't set any instance attributes. While harmless, it's inconsistent with other sources that do set `self._data`.

5. **Comment indicates test limitation (lines 879-898):**
   The extensive comments in `test_best_effort_timeout_merges_during_processing` acknowledge the test doesn't actually verify the stated bug (P1-2026-01-22) definitively. The test was simplified from its original intent and now just verifies "processing should complete reasonably fast."

### 🔵 Info

1. **Good use of build_production_graph() throughout:** All tests use `build_production_graph()` helper per CLAUDE.md Test Path Integrity requirements. This ensures production code paths are exercised.

2. **Comprehensive audit trail verification (lines 590-762):** The `TestCoalesceAuditTrail.test_coalesce_records_node_states` test performs thorough verification of:
   - Node states for consumed tokens
   - Token outcomes (COALESCED, FORKED)
   - Parent-child relationships with ordinals
   - Artifact recording

3. **Good test isolation within class:** Each test class focuses on a specific aspect (pipeline flow, metrics, audit trail, timeouts, aggregation).

4. **Fork+aggregation+coalesce test (lines 969-1187):** The `test_aggregation_then_fork_coalesce` test exercises a complex topology that caught a real bug (coalesce metadata dropped on aggregation continuation).

5. **Inline test plugins (lines 61-110):** `ListSource` and `CollectSink` are well-designed reusable test fixtures that implement the actual plugin protocols.

## Verdict

**KEEP** - This is valuable integration test coverage that exercises production code paths. The issues identified are minor:
- The `hasattr()` pattern should be fixed to call `to_dict()` directly
- The timing-based test could be improved with deterministic clock injection
- Module-scoped fixture is a minor concern but acceptable given run_id filtering

The tests provide important coverage for fork/coalesce scenarios and have caught real bugs per the documented regression test purposes.
