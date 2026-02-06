# Test Audit: tests/engine/test_orchestrator_payload_store.py

**Lines:** 388
**Test count:** 5
**Audit status:** PASS

## Summary

This file contains well-designed acceptance tests verifying the mandatory payload_store requirement in orchestrator.run(). Tests properly verify both the requirement enforcement and the audit trail integration. The tests use production paths via `build_production_graph()` helper and verify observable behavior rather than internal state.

## Findings

### 🔵 Info

1. **Lines 39-101: Excellent requirement enforcement test**
   - `test_run_raises_without_payload_store` verifies ValueError is raised before source loading.
   - Properly checks that `source.load_called` is False, confirming fail-fast behavior.
   - Documents audit compliance rationale in comments.

2. **Lines 103-184: Good audit trail integration test**
   - `test_run_with_payload_store_populates_source_data_ref` verifies source_data_ref is populated.
   - Uses `LandscapeRecorder.get_rows()` to query audit trail - tests observable outcome.
   - Includes helpful assertion messages referencing CLAUDE.md requirements.

3. **Lines 186-253: Proper parameter passthrough verification**
   - `test_execute_run_receives_payload_store` uses spy pattern to verify parameter wiring.
   - Catches "orphaned parameter" bugs where parameters are added but not wired through.
   - The spy pattern is appropriate here since testing internal parameter passing.

4. **Lines 255-277: Fixture isolation test is somewhat weak**
   - `test_payload_store_fixture_isolation` only verifies data can be stored and retrieved.
   - Cannot actually verify isolation between tests from within a single test.
   - However, the test documents expected fixture behavior which has value.

5. **Lines 283-387: Good integration test with transforms**
   - `test_run_with_transform_populates_source_data_ref` verifies payload storage happens before transform.
   - Tests the invariant that transforms don't affect source data capture.

### 🟡 Warning

1. **Lines 47-66, 68-81, 113-132, 134-152, 197-225, 292-315, 317-332, 334-351: Repeated boilerplate**
   - Multiple test classes define nearly identical `MinimalSchema`, `MinimalSource`, `MinimalSink`, etc.
   - Could be extracted to shared fixtures or conftest helpers.
   - Not a defect but adds maintenance burden.

## Verdict

**KEEP** - These are well-designed acceptance tests that verify critical audit compliance requirements. The tests use production paths appropriately and verify observable outcomes. The boilerplate repetition is a minor maintenance concern but doesn't affect test validity.
