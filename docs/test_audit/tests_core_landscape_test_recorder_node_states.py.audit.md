# Test Audit: tests/core/landscape/test_recorder_node_states.py

**Lines:** 621
**Test count:** 14
**Audit status:** PASS

## Summary

This test file provides excellent coverage of node state operations in LandscapeRecorder, including hash correctness verification, empty payload handling, retry tracking, audit integrity validation (Tier 1 rules), and deterministic ordering. The tests are well-documented with bug references and explicitly validate the Data Manifesto requirements for audit trail integrity.

## Findings

### Info

1. **Excellent hash correctness testing (line 51-108):** The `test_node_state_hash_correctness` test verifies that `input_hash` and `output_hash` match expected values from `stable_hash()`, not just checking for non-NULL. This is critical for audit integrity.

2. **Bug regression tests with references:** Tests like `test_complete_node_state_with_empty_output` (line 195) and `test_begin_node_state_with_empty_context` (line 287) include bug IDs (P1-2026-01-19) in their docstrings, providing traceability.

3. **Tier 1 audit integrity testing (lines 376-508):** The `TestNodeStateIntegrityValidation` class deliberately corrupts the database using raw SQL to verify that reading corrupted audit data crashes (per Data Manifesto). This is excellent defensive testing.

4. **Deterministic ordering regression test (lines 511-621):** The `TestNodeStateOrderingWithRetries` class inserts states out of order to verify that `get_node_states_for_token()` returns them in deterministic (step_index, attempt) order. This prevents non-determinism in exports.

5. **Minor redundancy:** The import of `NodeStateStatus` appears both at module level (line 5) and inside test methods. The module-level import is sufficient.

## Verdict

**KEEP** - This is a high-quality test file that demonstrates best practices for testing audit-critical functionality. The deliberate corruption tests for Tier 1 integrity, hash correctness verification, and ordering determinism tests are particularly valuable. These tests would catch serious audit integrity bugs before production. No changes needed.
