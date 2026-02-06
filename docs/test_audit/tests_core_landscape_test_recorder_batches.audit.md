# Test Audit: tests/core/landscape/test_recorder_batches.py

**Lines:** 449
**Test count:** 12
**Audit status:** PASS

## Summary

This test file provides comprehensive coverage of batch lifecycle management for aggregation operations. Tests are well-organized into three logical classes covering batch creation/management, recovery queries, and retry functionality. The fixture-based approach (`landscape_db`) provides clean, consistent test setup.

## Findings

### 🔵 Info

1. **Lines 115-173: Excellent lifecycle test** - `test_batch_lifecycle` demonstrates best practices by testing the complete state machine (draft -> executing -> completed) in a single coherent test. This verifies the batch status transitions work correctly.

2. **Lines 207-313: Strong recovery query coverage** - `TestBatchRecoveryQueries` class tests critical crash recovery scenarios: finding incomplete batches, including failed batches for retry, and maintaining creation order for deterministic recovery. These tests directly support audit integrity.

3. **Lines 316-449: Thorough retry testing** - `TestBatchRetry` covers all aspects of retry behavior: attempt increment, member preservation, rejecting retries of non-failed batches, and handling nonexistent batches. The error case tests (lines 411-449) properly use `pytest.raises` with match patterns.

4. **Lines 371-379: Source node registration in retry test** - `test_retry_batch_preserves_members` registers both an aggregation node and a separate source node. This is necessary because rows need a valid source_node_id, showing attention to foreign key constraints.

5. **Lines 218-227, 263-272, 293-302: Explicit node_id assignment** - Several tests use explicit `node_id="agg_node"` rather than letting the system generate one. This is intentional for test clarity but worth noting as it differs from production usage where node_ids are typically generated.

## Verdict

**KEEP** - Tests are well-structured, test real database operations without mocking, and cover critical crash recovery and retry scenarios. The separation into three focused test classes improves readability. All tests verify actual database state changes, not just return values.
