# Test Audit: tests/core/test_dag.py

**Lines:** 3508
**Test count:** 84 test functions (across 18 test classes + 4 standalone functions)
**Audit status:** PASS

## Summary

This is an exceptionally well-structured and comprehensive test file for DAG validation and operations. The tests follow a clear organizational pattern by feature area, exercise both positive and negative cases, and use production code paths (`from_plugin_instances`) for integration tests rather than manual graph construction. The test coverage is thorough, including edge cases like schema validation, coalesce branch compatibility, mixed dynamic/explicit schemas, and deterministic node IDs.

## Findings

### 🔵 Info

1. **Large but well-organized file (lines 1-3508)**: The file is large (3508 lines), but this is justified by comprehensive feature coverage. The test classes are logically grouped by functionality (DAGBuilder, DAGValidation, SchemaContractValidation, SourceSinkValidation, ExecutionGraphAccessors, etc.). Consider whether the file could be split by major feature area (e.g., `test_dag_builder.py`, `test_dag_schema_validation.py`, `test_dag_coalesce.py`) to improve maintainability, but this is not a critical issue.

2. **Repeated config boilerplate (multiple tests)**: Many tests repeat similar `ElspethSettings` construction with nearly identical source/sink configurations. This is acceptable given that tests should be explicit, but a fixture or builder could reduce repetition.

3. **Internal API access in tests (lines 3076, 3351, 3415-3416)**: Some tests access `graph._graph` directly to inspect internal state. This is acceptable for integration tests verifying implementation details but creates coupling to internal representation.

4. **Test `test_duplicate_fork_branches_rejected_in_plugin_gate` uses inline dummy classes (lines 1503-1598)**: This test defines `DummySource`, `DummySink`, and `DummyGate` inline. While this keeps the test self-contained, these could potentially be extracted to a shared fixture if similar patterns appear elsewhere.

5. **Bug regression tests well-documented (multiple tests)**: Tests include explicit bug ticket references and explanations (e.g., BUG-LINEAGE-01, P2-2026-01-30-coalesce-schema-identity-check, P2-2026-02-01-dynamic-branch-schema-mismatch-not-detected). This is excellent practice for maintaining test intent.

### Positive Observations (Not Findings)

- **Production code paths used consistently**: Tests use `ExecutionGraph.from_plugin_instances()` and `instantiate_plugins_from_config()` rather than manual graph construction, adhering to the CLAUDE.md guidance about test path integrity.

- **Schema validation tests are comprehensive**: Covers edge cases like gate routing to incompatible sinks, coalesce with incompatible branches, mixed observed/explicit schemas, and aggregation dual-schema transitions.

- **Contract tests verify interface compliance**: `test_fork_coalesce_contract_branch_map_compatible_with_step_map` explicitly tests the contract between DAG builder and Processor.

- **Deterministic node ID tests**: `TestDeterministicNodeIDs` class verifies checkpoint/resume compatibility.

- **MultiDiGraph edge handling**: `TestMultiEdgeSupport` and `TestMultiEdgeScenarios` correctly test multi-edge scenarios that caused previous bugs with DiGraph.

- **Good use of pytest fixtures**: The `plugin_manager` fixture is used appropriately for tests requiring the plugin system.

## Verdict

**KEEP** - This is a high-quality test file that provides comprehensive coverage of DAG validation and operations. The tests are well-documented, use production code paths, and cover important edge cases including historical bug regressions. The file size is large but justified by feature coverage. No critical issues found.

Optional improvement: Consider splitting into 3-4 smaller files organized by feature area for improved maintainability (e.g., schema validation, coalesce operations, graph building/accessors).
