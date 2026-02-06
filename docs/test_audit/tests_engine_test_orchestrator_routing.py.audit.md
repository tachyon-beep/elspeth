# Test Audit: tests/engine/test_orchestrator_routing.py

**Lines:** 620
**Test count:** 8
**Audit status:** PASS

## Summary

This test file provides comprehensive coverage of orchestrator routing behavior across four test classes: invalid routing validation, output sink routing, gate routing to named sinks, and route validation at initialization. Tests properly use the production graph path via `build_production_graph()` and verify both happy paths and error conditions. The tests demonstrate good adherence to the project's principle of failing loudly on configuration errors rather than silently dropping rows.

## Findings

### 🔵 Info

1. **Good Production Path Usage (Lines 131, 296, 381, 461, 541, 616)**: All tests consistently use `build_production_graph(config)` rather than manual graph construction, following CLAUDE.md "Test Path Integrity" guidance.

2. **Module-Scoped Database Fixture (Lines 44-50)**: The `routing_db` fixture is module-scoped for efficiency, with a note that tests must use unique run_ids to avoid conflicts. This is appropriate for tests that don't modify shared state in conflicting ways.

3. **Clear Error Validation (Lines 130, 460, 540)**: Tests properly verify that configuration errors (invalid sink names) raise `GraphValidationError` with helpful error messages containing the gate name and invalid destination.

4. **Source Not Loaded on Validation Failure (Line 469)**: The test `test_invalid_route_destination_fails_at_init` verifies that `source.load_called` is False when validation fails, confirming that no rows are processed before configuration is validated.

5. **Good Edge Case: Continue Routes (Lines 549-619)**: The `test_continue_routes_are_not_validated_as_sinks` test verifies that "continue" is a valid routing target and doesn't get incorrectly validated as a missing sink.

6. **Duplicate Test Class Definitions**: Similar to the retry test file, `ListSource` and `CollectSink` classes are redefined in multiple test classes. This could be consolidated but doesn't affect test validity.

7. **MED-003 Reference (Lines 307-310)**: The `TestRouteValidation` class docstring references a specific requirement (MED-003) about validating routes before processing rows, providing good traceability to requirements.

8. **Production Path with instantiate_plugins_from_config (Line 166)**: The `test_completed_rows_go_to_output_sink` test uses `instantiate_plugins_from_config(settings)` to get real plugin instances, then constructs the graph via `ExecutionGraph.from_plugin_instances()`, fully exercising the production code path.

### 🟡 Warning

1. **Mixed Graph Construction Approaches (Lines 168-176 vs elsewhere)**: The `test_completed_rows_go_to_output_sink` test uses `ExecutionGraph.from_plugin_instances()` directly while other tests use `build_production_graph()`. This inconsistency is minor but could be unified. However, this test specifically needs to use mock sinks, so the approach is appropriate for verifying which sink receives rows.

## Verdict

**KEEP** - High-quality routing tests that properly validate both configuration errors and runtime behavior. The tests follow project conventions and provide good coverage of the gate routing system. The fail-loudly principle for invalid configurations is well-tested.
