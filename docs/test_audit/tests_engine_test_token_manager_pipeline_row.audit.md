# Test Audit: tests/engine/test_token_manager_pipeline_row.py

**Lines:** 333
**Test count:** 14
**Audit status:** PASS

## Summary

This test file focuses on the `TokenManager` integration with `PipelineRow` and `SchemaContract`. It validates that contracts are properly propagated through token lifecycle operations (create, fork, expand, coalesce, update). Tests use mock recorders to isolate the TokenManager logic from database operations, which is appropriate for these unit-level tests.

## Findings

### 🔵 Info

1. **Mock-based testing appropriate for unit scope** (throughout): Uses `MagicMock` for `LandscapeRecorder` which is appropriate since this file tests TokenManager's PipelineRow handling, not the full integration path. The companion file `test_tokens.py` uses real databases for integration testing.

2. **Contract propagation tests** (lines 91-176): Tests validate that SchemaContract references are preserved through fork and expand operations. This is critical for maintaining type information through the pipeline.

3. **Deepcopy behavior tested** (lines 219-256): Tests verify that `copy.deepcopy(PipelineRow)` correctly preserves contract references while isolating nested data structures.

4. **Lineage preservation tests** (lines 284-308): `test_update_row_data_preserves_lineage` validates that branch_name, fork_group_id, and expand_group_id are preserved through updates.

5. **Contract requirement validation** (lines 67-88): `test_create_initial_token_requires_contract` validates the guard that crashes when a SourceRow has no contract - important for the trust model.

6. **Good helper functions** (lines 12-34): `_make_contract()` and `_make_mock_recorder()` reduce boilerplate and make tests readable.

7. **Minor: Some tests could be parametrized**: Tests like `test_update_row_data_preserves_lineage` could potentially be combined with parametrization, but the current explicit approach is clear.

## Verdict

**KEEP** - This file provides good unit test coverage for the PipelineRow integration with TokenManager. It complements `test_tokens.py` which provides integration tests with real databases.
