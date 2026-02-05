# Test Audit: test_processor_retry.py

**File:** `/home/john/elspeth-rapid/tests/engine/test_processor_retry.py`
**Lines:** 740
**Batch:** 89

## Summary

Tests for RowProcessor work queue iteration guards, retry integration with RetryManager, and recovery support with restored aggregation state. This is a comprehensive test file covering critical failure/retry paths.

## Test Classes

### TestRowProcessorWorkQueue

Tests for fork child execution and work queue iteration guards.

### TestRowProcessorRetry

Tests for retry integration in RowProcessor.

### TestRowProcessorRecovery

Tests for recovery support with restored aggregation state.

### TestNoRetryAuditCompleteness

Tests for audit trail completeness when `retry_manager` is None (P2 bug verification tests).

## Issues Found

### 1. DEFECT: Overmocked Retry Test Bypasses Production Path (High)

**Location:** `test_retries_transient_transform_exception` (lines 253-321)

**Problem:** Test mocks `processor._transform_executor` directly:

```python
processor._transform_executor = Mock()
processor._transform_executor.execute_transform.side_effect = flaky_execute
```

This bypasses the production `TransformExecutor` entirely. The test verifies retry count but doesn't verify:
- Audit trail recording for each attempt
- Backoff timing
- Correct token state updates

**Impact:** Test verifies retry manager integration with processor but not actual transform execution with retry.

**Recommendation:** Either:
1. Keep this as a unit test for retry manager integration, but add integration test with real executor
2. Create a real failing transform and verify full audit trail

### 2. DEFECT: Test Uses Private Attribute Access for Verification (Medium)

**Location:** `test_processor_accepts_retry_manager` (lines 232-251)

**Problem:** Test asserts on private attribute:

```python
assert processor._retry_manager is retry_manager
```

**Impact:** Test couples to internal implementation. If `_retry_manager` is renamed or stored differently, test breaks unnecessarily.

**Recommendation:** Verify behavior instead of internal state (e.g., verify retry behavior occurs).

### 3. DEFECT: Mock Transform Missing Required Attributes (Medium)

**Location:** Multiple tests (lines 298-307, 344-347, 393-395, 434-436)

**Problem:** Tests create `Mock()` transforms with only partial attributes:

```python
transform = Mock()
transform.node_id = "transform-1"
# Missing: name, input_schema, output_schema, _on_error (sometimes)
```

**Impact:** Tests may pass even if production code accesses other attributes. The production `_execute_transform_with_retry` accesses `transform._on_error` and `transform.name`.

**Recommendation:** Use `Mock(spec=TransformProtocol)` or create proper test transforms.

### 4. DEFECT: test_llm_non_retryable_error_propagates Uses Wrong Pattern (Medium)

**Location:** Lines 412-443

**Problem:** Test expects non-retryable `LLMClientError` to propagate:

```python
with pytest.raises(LLMClientError) as exc_info:
    processor._execute_transform_with_retry(transform, token, ctx, step=0)
```

However, the production code at line 1249 only re-raises if `not e.retryable`, which is correct. But the test doesn't verify that the error was NOT recorded to audit trail (since it propagated).

**Impact:** If audit recording happens before the re-raise, the test wouldn't catch it.

**Recommendation:** Verify no audit trail was written for the propagated error.

### 5. GOOD: P2 Bug Verification Tests (Positive)

**Location:** `TestNoRetryAuditCompleteness` (lines 557-740)

**Observation:** These tests verify critical P2 bug fixes:
- `test_no_retry_retryable_exception_records_transform_error`: Verifies audit completeness
- `test_no_retry_with_on_error_none_raises_instead_of_invalid_routed`: Verifies proper error handling

These tests use real components (`LandscapeDB.in_memory()`, real `LandscapeRecorder`) and query the database to verify audit trail. This is the correct pattern.

### 6. Missing Coverage: Retry Exhaustion with Non-LLM Errors (Medium)

**Problem:** `test_max_retries_exceeded_returns_failed_outcome` only tests `ConnectionError`. No test for retry exhaustion with `TimeoutError` or `OSError`.

**Impact:** Different error types may have different handling.

### 7. Missing Coverage: Retry with Backoff Timing (Low)

**Problem:** No test verifies that exponential backoff is actually applied between retries. Tests use `base_delay=0.01` to speed up but don't verify timing behavior.

**Impact:** Backoff logic bugs would not be caught.

### 8. DEFECT: Fork Test May Have Race Condition with Edge Registration (Low)

**Location:** `test_fork_children_are_executed_through_work_queue` (lines 114-226)

**Problem:** Test registers edges but the edge routing logic is complex:

```python
edge_a = recorder.register_edge(
    run_id=run.run_id,
    from_node_id=gate_node.node_id,
    to_node_id=transform_node.node_id,
    label="path_a",
    mode=RoutingMode.COPY,
)
```

Both edges point to the same `transform_node.node_id`, which is unusual. In production, fork paths typically go to different transforms.

**Impact:** Test may not accurately reflect production fork behavior where paths diverge.

**Recommendation:** Use distinct target nodes for each fork path.

### 9. Missing Coverage: Work Queue with Nested Forks (Medium)

**Problem:** `test_fork_children_are_executed_through_work_queue` tests single-level fork. No test for nested forks (fork within fork) which would stress the iteration guard more.

**Impact:** Complex DAG scenarios untested.

### 10. DEFECT: Restored Aggregation State Test Incomplete (Medium)

**Location:** `test_processor_accepts_restored_aggregation_state` (lines 527-554)

**Problem:** Test verifies state is passed to executor but doesn't verify the state is actually USED during processing:

```python
assert processor._aggregation_executor.get_restored_state(NodeID("agg_node")) == {
    "buffer": [1, 2],
    "count": 2,
}
```

**Impact:** State restoration might work but subsequent row processing might not use the restored state correctly.

**Recommendation:** Add test that processes rows after restoration and verifies they're added to the restored buffer.

## Structural Issues

### 11. Mixed Mocking Patterns (Medium)

**Problem:** Some tests use heavy mocking (lines 253-321), others use real components (lines 445-521). This inconsistency makes coverage analysis difficult.

**Recommendation:** Clearly separate unit tests (mocked) from integration tests (real components), perhaps in different files or test classes.

### 12. Duplicate Contract Factory Function (Low)

**Problem:** `_make_observed_contract()` is duplicated in this file and `test_processor_quarantine.py`. Should be in `conftest.py`.

## Test Path Integrity

- Tests do NOT use `ExecutionGraph.from_plugin_instances()` but don't need to
- Fork test manually constructs edge maps but this is appropriate for testing processor-level routing
- Test classes properly named with "Test" prefix
- No DAG construction violations

## Verdict

**NEEDS IMPROVEMENT** - Critical retry paths have overmocking issues. The P2 bug verification tests are good but earlier tests need real component integration.

## Fixes Required

1. **High:** Add integration test for retry with real `TransformExecutor` verifying audit trail per attempt
2. **Medium:** Replace `Mock()` transforms with proper test transforms having required attributes
3. **Medium:** Add test for restored aggregation state being used in subsequent processing
4. **Medium:** Fix fork test to use distinct target nodes for fork paths
5. **Low:** Move `_make_observed_contract()` to `conftest.py`
6. **Low:** Add test for retry exhaustion with different error types
