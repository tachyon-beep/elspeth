## tests/engine/test_node_id_assignment.py
**Lines:** 220
**Tests:** 8
**Audit:** WARN

### Summary
This test file validates the `Orchestrator._assign_plugin_node_ids()` method which assigns node IDs to plugins during pipeline setup. The tests are comprehensive for unit testing the assignment logic, but use `MagicMock` for all plugins which is appropriate for this internal method's unit tests. The tests verify error handling, correct assignment, and preservation of pre-assigned IDs.

### Findings

#### WARN: Heavy Mocking of Plugins
**Severity:** Low
**Location:** All tests use `MagicMock()` for source, transform, and sink plugins

While this is technically "overmocking," it's justified here because:
1. The method being tested (`_assign_plugin_node_ids`) is an internal helper that only sets `node_id` attributes
2. The test is verifying ID assignment logic, not plugin behavior
3. Using real plugins would require unnecessary setup without adding test value

This is acceptable for unit testing an internal method. Integration tests should verify the full flow works with real plugins.

#### GOOD: Error Path Coverage
**Severity:** N/A

The tests properly cover error paths:
- `test_assign_plugin_node_ids_validates_source` - missing node_id attribute raises AttributeError
- `test_assign_plugin_node_ids_raises_for_missing_transform` - missing transform mapping raises ValueError
- `test_assign_plugin_node_ids_raises_for_missing_sink` - missing sink mapping raises ValueError

#### GOOD: Pre-assigned ID Preservation
**Severity:** N/A
**Location:** Line 180-220

`test_assign_plugin_node_ids_preserves_preassigned_transform_ids` validates that aggregation transforms with pre-assigned node_ids are not overwritten. This matches the production code behavior (lines 306-308 in orchestrator/core.py).

#### Note: Test Class Naming
The class `TestNodeIdAssignment` is properly named with "Test" prefix, so pytest will discover all tests.

### Verdict
**WARN** - Tests are well-structured unit tests for the internal `_assign_plugin_node_ids` method. The mocking is justified since we're testing assignment logic, not plugin integration. Consider adding a comment noting that integration tests exist elsewhere to verify the full node ID assignment flow with real plugins. No blocking issues.
