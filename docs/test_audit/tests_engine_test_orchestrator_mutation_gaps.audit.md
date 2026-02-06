# Test Audit: tests/engine/test_orchestrator_mutation_gaps.py

**Lines:** 565
**Test count:** 17
**Audit status:** ISSUES_FOUND

## Summary

This file contains mutation-testing targeted tests designed to kill surviving mutants in orchestrator.py. The tests are well-structured with clear documentation linking each test to specific line numbers. However, several tests have structural issues including direct access to internal orchestrator state and one test that manually builds execution graphs instead of using production paths.

## Findings

### 🟡 Warning

1. **Lines 483-514: Direct access to internal state `_sequence_number` and `_current_graph`**
   - Test `test_sequence_number_increments_on_checkpoint` directly accesses `orchestrator._sequence_number` and sets `orchestrator._current_graph`.
   - This couples tests to implementation details rather than observable behavior.
   - If the internal state representation changes, these tests break even if behavior is correct.

2. **Lines 484-488: Manual graph construction instead of production path**
   - `TestCheckpointSequencing.test_sequence_number_increments_on_checkpoint` manually calls `graph.add_node()` and `graph.add_edge()`.
   - Per CLAUDE.md "Test Path Integrity" section, integration tests should use `ExecutionGraph.from_plugin_instances()`.
   - This test is borderline acceptable since it tests checkpoint internals, not graph construction, but the pattern is risky.

3. **Lines 385-448: Integration test mixed with unit test concerns**
   - `test_config_gate_recorded_as_deterministic` is a good integration test, but it's in a file labeled for mutation testing gaps.
   - This test should arguably be in a dedicated gate metadata test file for better organization.

4. **Lines 126-140: Redundant test for required field validation**
   - `test_rows_routed_is_required` tests Python's TypeError for missing required dataclass field.
   - This is testing Python/dataclass behavior, not application logic.
   - The mutation being killed here is unlikely to occur in practice.

### 🔵 Info

1. **Lines 50-124: Well-structured dataclass default tests**
   - `TestRunResultDefaults` properly tests that default values are correct.
   - Each test has clear docstrings linking to specific mutation-tested lines.

2. **Lines 216-297: Good validation edge case coverage**
   - `TestRouteValidationEdgeCases` tests special cases for "continue" and "fork" destinations.
   - Properly calls validation functions directly for isolation.

3. **Lines 311-366: Good source quarantine validation coverage**
   - `TestSourceQuarantineValidation` tests quarantine destination validation with clear error message verification.

## Verdict

**KEEP** - The tests serve their documented purpose of killing mutation survivors. The warnings about internal state access are acceptable in context since these are specifically targeting internal implementation details that mutation testing revealed as undertested. The manual graph construction is borderline but acceptable for checkpoint-specific testing that doesn't depend on graph construction logic.
