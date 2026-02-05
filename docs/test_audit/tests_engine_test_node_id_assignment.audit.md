# Test Audit: tests/engine/test_node_id_assignment.py

**Lines:** 220
**Test count:** 8
**Audit status:** ISSUES_FOUND

## Summary

Solid unit test coverage for `Orchestrator._assign_plugin_node_ids()` method. Tests cover happy paths, error paths, and edge cases (pre-assigned aggregation IDs). However, heavy use of MagicMock raises concerns about overmocking - the tests verify the method's behavior with mocks but may miss issues that arise with real plugin instances.

## Findings

### 🟡 Warning

1. **Overmocking concerns (throughout)**: All 8 tests use `MagicMock` for source, transforms, and sinks. While this isolates the `_assign_plugin_node_ids` logic, it means the tests don't validate:
   - That real plugin classes have the `node_id` attribute
   - That setting `node_id` on real plugins works correctly
   - Protocol compliance of actual plugins

2. **Testing private method directly (all tests)**: All tests call `orchestrator._assign_plugin_node_ids()` directly. While this is acceptable for unit testing internal logic, there should also be integration tests that verify this method is called correctly via the public `run()` interface.

3. **Mocking LandscapeDB spec incompletely (lines 19, 37, 56, etc.)**: Using `MagicMock(spec=LandscapeDB)` but then never using the mock. The orchestrator is created but LandscapeDB interactions are not tested. This could hide issues if `_assign_plugin_node_ids` needs DB interaction.

### 🔵 Info

1. **Good error path coverage (lines 104-143)**: Tests for missing transform and missing sink mappings properly verify error messages with `pytest.raises(ValueError, match=...)`.

2. **Edge case for aggregations (lines 180-220)**: Excellent test for preserving pre-assigned node_ids - this documents the aggregation assignment flow where CLI assigns IDs before orchestrator runs.

3. **Clear test naming**: Test names clearly describe what is being tested (e.g., `test_assign_plugin_node_ids_raises_for_missing_transform`).

## Verdict

**KEEP** - Tests are valid and provide good coverage of the `_assign_plugin_node_ids` method. Consider adding one integration test that exercises this method through the production path (`Orchestrator.run()`) to complement these unit tests and catch any mock/real divergence.
