# Test Audit: tests/core/checkpoint/test_topology_validation.py

**Lines:** 397
**Test count:** 12 test methods across 3 test classes
**Audit status:** PASS

## Summary

This test file validates checkpoint topology validation, which is critical for audit integrity. The tests verify that resuming with a modified pipeline configuration is correctly rejected, preventing "one run, two configs" corruption. The file covers linear pipeline scenarios (complementing more complex DAG tests in test_compatibility_validator.py), topology hash determinism, and audit integrity guarantees. The tests are well-organized and comprehensive.

## Findings

### 🔵 Info

1. **Lines 1-10: Clear purpose statement** - The docstring explains the audit integrity significance and mentions the companion file for complex DAG tests.

2. **Lines 23-60: Reusable graph builder** - `_create_linear_graph` is a well-designed helper that creates parameterized linear pipelines with proper edge labels and routing modes.

3. **Lines 62-82: Checkpoint factory** - `_create_checkpoint_for_graph` creates checkpoints with correct topology and config hashes from the graph, using production functions `compute_full_topology_hash` and `stable_hash`.

4. **Lines 84-192: Core validation tests (TestCheckpointTopologyValidation)** - Six tests covering: identical graph success, added transform failure, removed transform failure, modified sink config failure, missing checkpoint node failure, and checkpoint node config change failure.

5. **Lines 241-310: Hash determinism tests (TestTopologyHashDeterminism)** - Four tests verifying that identical graphs produce identical hashes, and different configs/edges/routing modes produce different hashes. This is foundational for topology validation correctness.

6. **Lines 313-397: Audit integrity tests (TestResumeAuditIntegrity)** - Two tests focusing on the critical guarantee that mismatched topology produces explicit rejection (not silent acceptance) with clear reasons.

### 🟡 Warning

1. **Lines 115, 131, 175: Assertion message flexibility** - Some assertions check for "topology" OR "configuration changed" in the error message. This is reasonable since different validation checks might fail first, but it means the tests don't verify which specific check caught the problem.

2. **Lines 143-175: Manual graph construction** - `test_modified_sink_config_causes_validation_failure` manually constructs the modified graph instead of using `_create_linear_graph`. This is necessary because the helper doesn't support custom configs, but it duplicates graph construction logic.

3. **Lines 203-238: Same manual construction issue** - `test_checkpoint_node_config_changed_causes_validation_failure` also manually constructs the graph for the same reason.

## Verdict

**KEEP** - This is a well-designed test file for critical audit integrity functionality. The tests cover all important validation scenarios, hash determinism, and explicit rejection guarantees. The organization into three focused test classes is good. No significant issues identified.
