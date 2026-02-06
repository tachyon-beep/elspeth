# Test Audit: tests/core/checkpoint/test_recovery_type_fidelity.py

**Lines:** 224
**Test count:** 1 test method
**Audit status:** ISSUES_FOUND

## Summary

This test file validates an important bug fix (Bug #4): type fidelity preservation when restoring row data from canonical JSON during resume. The test creates rows with datetime and Decimal fields, stores them via canonical_json(), then verifies that get_unprocessed_row_data() correctly restores the original types using the provided schema. While the test is valuable and comprehensive, there are structural issues to note.

## Findings

### 🔵 Info

1. **Lines 1-9: Clear problem statement** - The docstring explains the bug: canonical JSON normalizes types (datetime to ISO string, Decimal to string) and json.loads() restores them as plain str without schema guidance.

2. **Lines 49-224: Comprehensive single test** - The test validates the complete flow: creating runs with typed data, storing via canonical_json, creating checkpoints, and verifying type restoration with schema.

3. **Lines 185-198: Schema definition** - The test correctly defines a Pydantic schema with datetime and Decimal fields to enable type coercion during recovery.

4. **Lines 212-220: Verification with prints** - The test includes debug prints to show type restoration worked. These could be removed but are harmless.

### 🟡 Warning

1. **Single test for important functionality** - The file contains only one test. Additional tests would strengthen coverage:
   - Test behavior when schema doesn't match data (e.g., missing fields)
   - Test with additional types (e.g., int, float, bool, nested objects)
   - Test that calling without schema raises TypeError (as mentioned in docstring)

2. **Lines 150-166: Direct table insert for checkpoint** - The test inserts directly into `checkpoints_table` rather than using `CheckpointManager.create_checkpoint()`. This bypasses the production code path for checkpoint creation, though the focus here is on recovery, not checkpoint creation.

3. **Lines 161-163: Hardcoded hash values** - The checkpoint uses hardcoded `upstream_topology_hash` and `checkpoint_node_config_hash` values. This is acceptable for a focused type fidelity test but doesn't validate checkpoint compatibility.

4. **Lines 168-180: Token outcome setup** - Correctly sets up token outcomes per P1-2026-01-22 fix.

### 🔴 Critical

None identified. The single test is valuable and the bug it validates is important.

## Verdict

**KEEP** - The test validates an important type fidelity bug fix. However, consider adding additional tests for edge cases (schema mismatch, different types, missing schema parameter enforcement). The single test is comprehensive for the happy path but leaves some scenarios uncovered.
