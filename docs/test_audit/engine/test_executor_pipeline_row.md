## tests/engine/test_executor_pipeline_row.py
**Lines:** 1424
**Tests:** 24
**Audit:** WARN

### Summary
This test file validates that executor classes correctly handle PipelineRow objects, including proper dict extraction for Landscape recording, contract propagation, and checkpoint serialization. The tests use appropriate mocking and verify correct behaviors. However, there are some concerns about test completeness for certain edge cases and a few instances where assertions could be strengthened.

### Findings

#### Critical
None identified.

#### Warning
- **Line 780-794: Fragile mock pattern for contract testing**: The test `test_execute_gate_crashes_if_no_contract_available` patches `type(token.row_data).contract` using `PropertyMock`, which relies on the internal implementation detail that `contract` is accessed as a property. If the implementation changes to access it differently, this test would silently pass without actually testing the crash behavior. Consider creating a custom test object with `contract=None` instead.

- **Line 1197-1257: Incomplete checkpoint contract verification**: The test `test_checkpoint_contains_dicts_not_pipeline_row` verifies JSON serializability but does not verify that the checkpoint includes all required fields for restoration (like `contract_version`). The production code in `restore_from_checkpoint` requires these fields and will crash if they're missing.

- **Line 1305-1307: Weak assertion for contract presence**: The assertion `assert "contract" in node_checkpoint or any("contract_version" in t for t in node_checkpoint["tokens"])` is overly permissive. Per the production code in `get_checkpoint_state()`, the checkpoint format v2.0 MUST have both `contract` at node level AND `contract_version` per token. The "or" condition masks a potential bug.

- **Lines 922-925, 984-986, 1103-1104, 1422-1424: Unreachable code type ignores**: Multiple tests have `# type: ignore[comparison-overlap, unreachable]` comments after assertions like `type(row_in_output) is not PipelineRow`. These are correct assertions, but the type ignores suggest mypy sees these as unreachable because PipelineRow subclasses dict. This is working as designed but could confuse future maintainers.

#### Info
- **Lines 77-82, 131-136, etc.: Repeated mock setup pattern**: Each test manually configures the same mock transform/gate setup (setting `name`, `node_id`, `_on_error`, deleting `accept`). This pattern is repeated across ~10 tests. Consider extracting to a fixture or helper function for maintainability and reducing test verbosity.

- **Lines 806-866: Good coverage of SinkExecutor dict extraction**: The `TestSinkExecutorPipelineRow` class properly tests that sinks receive dicts and not PipelineRow objects, correctly verifying that contract metadata stays in the audit trail.

- **Lines 1309-1367: Good checkpoint round-trip testing**: The test `test_restore_from_checkpoint_creates_pipeline_row` properly validates the full checkpoint/restore cycle including contract restoration.

- **Test class naming is correct**: All test classes use the `Test*` prefix (e.g., `TestTransformExecutorPipelineRow`, `TestGateExecutorPipelineRow`, `TestSinkExecutorPipelineRow`, `TestAggregationExecutorPipelineRow`), ensuring pytest discovery.

- **No Test Path Integrity violations**: These tests appropriately use unit-test mocking to isolate the executors, which is correct for this level of testing. The executors don't use `ExecutionGraph.from_plugin_instances()` directly - they are called by the orchestrator which does. Unit testing executors with mocks is the appropriate pattern here.

### Missing Coverage
1. **Transform error routing with contract preservation**: Tests verify error handling but don't verify that the token retains its PipelineRow/contract when routed to an error sink.

2. **Multi-row TransformResult with contracts**: The `TransformResult.success_multi(rows)` path creates multiple output rows, but there's no test verifying contract handling for multi-row results.

3. **GateExecutor fork with contract propagation**: The gate fork tests in the production code create child tokens with PipelineRow - this behavior isn't tested here (fork creates child tokens, each should have proper contract).

4. **AggregationExecutor PipelineRow reconstruction in flush**: The production code reconstructs PipelineRow objects from buffered dicts during flush (line 1288-1295 in executors.py), but this isn't directly tested.

5. **Sink with empty contract on token**: Edge case where a token arrives at sink with no contract on row_data.

### Verdict
**WARN** - Tests are fundamentally sound and cover the core PipelineRow handling behaviors. The warnings are primarily about test maintainability (repeated setup code), slightly weak assertions that could mask regressions, and some missing coverage for edge cases. Recommend extracting common mock setup to fixtures and strengthening the checkpoint contract assertions.
