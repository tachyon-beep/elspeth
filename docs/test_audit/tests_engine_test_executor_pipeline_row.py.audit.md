# Test Audit: tests/engine/test_executor_pipeline_row.py

**Lines:** 1424
**Test count:** 25 test methods across 5 test classes
**Audit status:** PASS

## Summary

This is an excellent, comprehensive test file that verifies the executor's handling of PipelineRow objects. The tests systematically verify that: (1) executors pass PipelineRow to plugins, (2) dicts are extracted for Landscape recording, (3) ctx.contract is set from token.row_data.contract, (4) new PipelineRow is created from results with correct contracts, and (5) the system crashes if no contract is available (B6 fix). Test assertions are precise and meaningful.

## Findings

### 🔵 Info

1. **Lines 21-35, 38-59: Helper functions for test contracts** - Clean helper functions `_make_contract()` and `_make_output_contract()` create well-defined test fixtures. Good DRY practice.

2. **Lines 81-82, 136-137, etc.: MagicMock accept attribute deletion** - Pattern `del mock_transform.accept` is used to prevent MagicMock from auto-creating an `accept` attribute, which would trigger batch transform detection. This is documented and intentional.

3. **Lines 188-205: Context capture pattern** - Uses closure (`capture_ctx`) to capture the context passed to transform.process() for verification. This is an effective pattern for verifying arguments passed to mocked methods.

4. **Lines 780-794: PropertyMock for edge case testing** - Uses `patch.object(type(token.row_data), "contract", new_callable=PropertyMock)` to simulate the edge case where input token has no contract. This is appropriate for testing B6 fix behavior.

5. **Lines 922-926, 984-986: Type checking with type() not isinstance()** - Comments explain why `type(row_in_output) is not PipelineRow` is used instead of isinstance() - because PipelineRow subclasses dict. The `# type: ignore` comments are justified.

6. **Lines 1197-1256: Checkpoint serialization tests** - Tests verify checkpoints are JSON-serializable and contain dicts (not PipelineRow). Important for crash recovery.

7. **Lines 1258-1307: Checkpoint contract preservation** - Tests verify contract info is stored in checkpoint for PipelineRow restoration during resume. Critical for recovery functionality.

8. **Lines 1309-1424: Checkpoint roundtrip tests** - Tests verify restore_from_checkpoint reconstructs TokenInfo with PipelineRow. Good coverage of serialization/deserialization symmetry.

### 🟡 Warning

1. **Lines 96-98, 150-152, etc.: MagicMock with nullcontext** - Multiple tests create `mock_span_factory = MagicMock(spec=SpanFactory)` and set `.transform_span.return_value = nullcontext()`. This pattern is repeated ~15 times. Consider extracting to a fixture to reduce boilerplate (minor DRY concern).

## Verdict

**KEEP** - This is a high-quality test file that comprehensively tests the PipelineRow handling contract across all executor types (Transform, Gate, Sink, Aggregation). The tests verify both the happy path and edge cases (missing contracts, checkpointing). The minor code duplication in mock setup is acceptable given the clarity it provides.
