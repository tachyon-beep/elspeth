# Test Audit: tests/engine/test_tokens.py

**Lines:** 992
**Test count:** 24
**Audit status:** PASS

## Summary

This is a comprehensive integration test file for `TokenManager` that uses real `LandscapeDB` instances rather than mocks. It thoroughly tests the token lifecycle including creation, forking, coalescing, expansion, and data isolation. The tests are well-organized into logical test classes and include coverage for several bug fixes (P2-2026-01-20, P2-2026-01-21, P2-2026-01-31).

## Findings

### 🔵 Info

1. **Real database usage** (throughout): All tests use `LandscapeDB.in_memory()` and `LandscapeRecorder`, testing the actual database interaction rather than mocking. This provides high confidence in the integration.

2. **Excellent isolation tests** (lines 207-481): Two test classes (`TestTokenManagerForkIsolation` and `TestTokenManagerExpandIsolation`) thoroughly test that forked/expanded tokens have independent copies of nested data. This includes:
   - `test_fork_nested_data_isolation` - Bug P2-2026-01-20 fix
   - `test_expand_nested_data_isolation` - Bug P2-2026-01-21 fix
   - `test_expand_shared_input_isolation` - Tests isolation even when input rows share objects
   - `test_expand_deep_nesting_isolation` - Tests 3+ levels of nesting

3. **Lineage preservation tests** (lines 561-715): Comprehensive tests for `update_row_data` preserving all lineage fields:
   - `test_update_preserves_all_lineage_fields` - Bug P2-2026-01-31 fix
   - `test_update_preserves_expand_group_id`
   - `test_update_preserves_join_group_id`

4. **Step-in-pipeline audit trail tests** (lines 753-839): Tests verify that `step_in_pipeline` is correctly stored in the audit trail for fork, coalesce, and expand operations.

5. **Good helper functions** (lines 14-39): `_make_observed_contract()`, `_make_source_row()`, and `_make_pipeline_row()` reduce boilerplate while maintaining clarity.

6. **Some repetitive setup** (throughout): Each test creates its own `LandscapeDB`, `LandscapeRecorder`, run, and source node. This could potentially use pytest fixtures, but the explicit approach keeps each test self-contained and easy to understand in isolation.

7. **PipelineRow immutability acknowledged** (lines 207-212, 313-320): Test docstrings correctly note that PipelineRow uses MappingProxyType internally, and tests use `to_dict()` to verify isolation behavior.

## Verdict

**KEEP** - This is an excellent integration test file with comprehensive coverage of the TokenManager's token lifecycle operations. The tests properly validate bug fixes and use real database instances for high-confidence testing.
