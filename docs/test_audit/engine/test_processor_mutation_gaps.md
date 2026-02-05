# Test Audit: tests/engine/test_processor_mutation_gaps.py

**Lines:** 1153
**Test count:** 21 test functions across 10 test classes
**Audit date:** 2026-02-05
**Batch:** 86

## Summary

Targeted tests designed to kill specific mutants identified during mutation testing. Tests target trigger_type fallback, step boundary conditions, fork routing paths, branch-to-coalesce mappings, iteration guards, coalesce step calculations, group ID generation, and error handling paths.

## Test Inventory

| Class | Test | Lines | Purpose |
|-------|------|-------|---------|
| TestTriggerTypeFallback | test_flush_uses_count_when_trigger_type_is_none | 139-222 | Trigger type None fallback |
| TestStepBoundaryConditions | test_last_transform_produces_completed_result | 235-284 | Last step completion |
| TestStepBoundaryConditions | test_multiple_transforms_chains_correctly | 286-344 | Multi-transform chain |
| TestStepBoundaryConditions | test_step_equals_total_steps_minus_one_completes | 346-397 | 3-transform boundary |
| TestForkRoutingPaths | test_fork_gate_creates_child_tokens | 407-511 | Fork routing with config gate |
| TestForkRoutingPaths | test_gate_destinations_for_route_to_sink | 513-570 | Gate destination for sink routing |
| TestForkRoutingPaths | test_gate_destinations_for_continue | 572-628 | Gate destination for continue |
| TestForkRoutingPaths | test_gate_destinations_for_fork_to_paths | 630-702 | Gate destination for fork paths |
| TestBranchToCoalesceMapping | test_branch_to_coalesce_lookup_returns_coalesce_info | 715-758 | Branch mapping retrieval |
| TestBranchToCoalesceMapping | test_branch_not_in_mapping_skips_coalesce_lookup | 760-807 | Unknown branch handling |
| TestIterationGuards | test_single_row_completes_with_minimal_iterations | 821-869 | Single row iteration count |
| TestIterationGuards | test_multiple_transforms_increases_iterations | 871-924 | Multi-transform iteration count |
| TestCoalesceStepCalculations | test_step_offset_calculation_in_work_item | 935-958 | WorkItem step tracking |
| TestCoalesceStepCalculations | test_work_item_with_coalesce_step | 960-986 | WorkItem coalesce metadata |
| TestGroupIdGeneration | test_uuid_hex_slice_produces_16_chars | 1002-1018 | UUID format verification |
| TestGroupIdGeneration | test_error_hash_format_for_failed_operations | 1020-1035 | Error hash format |
| TestGroupIdGeneration | test_join_group_id_format_includes_coalesce_name | 1037-1056 | Join group ID format |
| TestErrorHandlingPaths | test_transform_failure_generates_error_hash | 1067-1088 | Error hash generation |
| TestErrorHandlingPaths | test_error_hash_deterministic_for_same_error | 1090-1101 | Hash determinism |
| TestErrorHandlingPaths | test_different_errors_produce_different_hashes | 1103-1112 | Hash uniqueness |
| TestExpandGroupIdTracking | test_expand_group_id_format | 1122-1133 | Expand group ID format |
| TestExpandGroupIdTracking | test_multiple_expansions_have_different_group_ids | 1135-1153 | Multiple expansion IDs unique |

## Findings

### Defects

1. **Line 191: Direct method assignment bypasses production code**
   ```python
   processor._aggregation_executor.get_trigger_type = mock_get_trigger_type
   ```
   - This replaces the method entirely, not testing the actual fallback logic
   - When `get_trigger_type()` returns None, the processor should handle it
   - But here the test injects a mock that always returns None, then asserts "no exception" - this doesn't verify the fallback VALUE is correct
   - **Impact:** Test may pass even if the fallback logic is broken

### Overmocking

1. **Lines 187-209: Heavy mocking defeats mutation testing purpose**
   - `test_flush_uses_count_when_trigger_type_is_none` mocks both `get_trigger_type` and `should_flush`
   - The test is supposed to kill mutation `if trigger_type is None` -> `if trigger_type is not None`
   - But with both methods mocked, the test doesn't exercise the code path where the mutation would matter
   - **Should:** Create an actual trigger configuration that results in None trigger_type

2. **Lines 562-570, 605-628, 684-702: Tests _get_gate_destinations directly**
   - These tests create `GateOutcome` objects manually and call `processor._get_gate_destinations()`
   - Bypasses the actual gate execution path
   - Better: exercise via full `process_row()` with appropriate gate configuration

### Missing Coverage

1. **No test for actual TriggerType.TIMEOUT behavior**
   - Tests only mention COUNT trigger type in fallback
   - Should have test proving TIMEOUT trigger type is handled differently

2. **No test verifying iteration limit is actually enforced**
   - `TestIterationGuards` tests that small pipelines complete
   - Should have test that artificially creates infinite loop and verifies MAX_WORK_QUEUE_ITERATIONS triggers

### Tests That Do Nothing (Standard Library Tests)

1. **Lines 1002-1018: test_uuid_hex_slice_produces_16_chars**
   - Tests `uuid.uuid4().hex[:16]` produces 16 hex chars
   - This tests Python stdlib, not processor code
   - **Does not kill any mutation** - the mutation is on how processor USES UUID, not how UUID works

2. **Lines 1020-1035: test_error_hash_format_for_failed_operations**
   - Tests `hashlib.sha256(error_msg.encode()).hexdigest()[:16]`
   - Tests stdlib behavior, not processor behavior

3. **Lines 1090-1112: test_error_hash_deterministic_for_same_error, test_different_errors_produce_different_hashes**
   - Tests `hashlib.sha256()` determinism and uniqueness
   - Pure stdlib tests, no production code involved

4. **Lines 1122-1153: TestExpandGroupIdTracking**
   - Both tests verify UUID behavior directly
   - Zero production code exercised

### Inefficiency

1. **Lines 24-69: Duplicate helpers**
   - `make_source_row()` and `_make_pipeline_row()` duplicated from other test files
   - Should be in conftest.py

2. **Lines 72-127: Test transforms defined at module level**
   - `PassthroughTransform` and `BatchTransform` are reusable, good
   - But then tests also define inline transforms (lines 444-496)

### Structural Issues

1. **Lines 935-986: TestCoalesceStepCalculations tests internal _WorkItem**
   - Tests construct `_WorkItem` dataclass directly
   - This is testing internal data structure, not behavior
   - Should verify coalesce behavior through `process_row()` with branch configuration

2. **Lines 715-807: TestBranchToCoalesceMapping tests private attributes**
   - Tests access `processor._branch_to_coalesce` and `processor._coalesce_step_map`
   - Should verify behavior: fork to branches, verify tokens coalesce at correct step

### Test Path Integrity

**MIXED** - Some tests use real components, but several bypass production paths:
- **Good:** TestStepBoundaryConditions (lines 225-397) uses real process_row()
- **Good:** TestForkRoutingPaths.test_fork_gate_creates_child_tokens uses real gate settings
- **Bad:** TestForkRoutingPaths destination tests bypass execution path
- **Bad:** TestCoalesceStepCalculations tests internal _WorkItem directly
- **Bad:** TestGroupIdGeneration, TestErrorHandlingPaths, TestExpandGroupIdTracking test stdlib only

### Info

1. **Lines 7-12: Good documentation of mutation targets**
   - Docstring lists specific line numbers and mutation patterns
   - Helpful for understanding test purpose

2. **Lines 407-511: test_fork_gate_creates_child_tokens is well-designed**
   - Uses real GateSettings, edge registration, and process_row()
   - Verifies actual fork behavior with config-driven gate

## Verdict

**ISSUES_FOUND** - 6 of 21 tests (29%) test Python stdlib rather than production code. These tests cannot kill the mutations they claim to target because they don't exercise processor methods. Additionally, several tests access private attributes directly rather than testing observable behavior. The remaining tests provide genuine mutation coverage.

## Recommendations

1. **Delete or rewrite stdlib tests** (TestGroupIdGeneration, TestErrorHandlingPaths.test_error_hash_*, TestExpandGroupIdTracking)
   - Replace with tests that exercise processor methods that GENERATE these IDs

2. **Fix test_flush_uses_count_when_trigger_type_is_none**
   - Create actual trigger configuration that produces None
   - Or create integration test that verifies fallback behavior observably

3. **Rewrite TestCoalesceStepCalculations**
   - Test through process_row() with fork+coalesce configuration
   - Verify tokens arrive at coalesce step at correct position

4. **Rewrite TestBranchToCoalesceMapping**
   - Test branch-to-coalesce through observable fork/coalesce behavior
   - Remove private attribute access

5. **Add MAX_WORK_QUEUE_ITERATIONS enforcement test**
   - Create pathological case that would infinite loop
   - Verify RuntimeError or appropriate handling
