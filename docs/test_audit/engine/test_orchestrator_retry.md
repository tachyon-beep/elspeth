# Test Audit: tests/engine/test_orchestrator_retry.py

**Lines:** 250
**Tests:** 2
**Audit:** PASS

## Summary

This file tests the Orchestrator retry functionality, verifying that transient failures are retried and that exhausted retries mark rows as failed. The tests use the production code path via `build_production_graph()` helper and make meaningful assertions about retry behavior.

## Findings

### PASS: Production Code Path Used

**Location:** Lines 132, 240

The tests correctly use `build_production_graph(config)` from the helper module to construct execution graphs:

```python
# Use production graph path for test reliability
graph = build_production_graph(config)
```

This follows the Test Path Integrity principle from CLAUDE.md and ensures tests exercise the same code path as production.

### PASS: Meaningful Retry Behavior Verification

**Location:** Lines 137-143

The first test verifies the retry mechanism works correctly:

```python
# Row should succeed after retry
assert result.status == "completed"
assert result.rows_processed == 1
assert result.rows_succeeded == 1
# Transform was called twice (first attempt failed, second succeeded)
assert attempt_count["count"] == 2, f"Expected 2 attempts (1 failure + 1 success), got {attempt_count['count']}"
assert len(sink.results) == 1
```

The assertion on `attempt_count["count"] == 2` directly verifies retry behavior occurred.

### PASS: Retry Exhaustion Coverage

**Location:** Lines 245-250

The second test verifies rows are marked failed when retries are exhausted:

```python
# Row should be marked failed after exhausting retries
assert result.status == "completed"
assert result.rows_processed == 1
assert result.rows_failed == 1
assert result.rows_succeeded == 0
assert len(sink.results) == 0
```

This is important edge case coverage.

### PASS: Proper Test Plugin Implementation

**Location:** Lines 67-80, 180-189

The test transforms properly inherit from `BaseTransform` and implement the required protocol:

```python
class RetryableTransform(BaseTransform):
    name = "retryable"
    input_schema = ValueSchema
    output_schema = ValueSchema

    def __init__(self) -> None:
        super().__init__({"schema": {"mode": "observed"}})

    def process(self, row: PipelineRow, ctx: Any) -> TransformResult:
        attempt_count["count"] += 1
        if attempt_count["count"] == 1:
            raise ConnectionError("Transient failure")
        return TransformResult.success(row.to_dict(), success_reason={"action": "passthrough"})
```

This follows CLAUDE.md guidance that plugins are system-owned code and should be properly implemented.

### INFO: Closure for Attempt Tracking

**Location:** Lines 65-66

```python
# Transform that tracks retry attempts via closure
attempt_count = {"count": 0}
```

Using a dict closure for tracking is a pragmatic approach to maintain state across retry attempts in tests. This is acceptable for test code.

### INFO: Type Annotation for Unused Import

**Location:** Lines 22-24

```python
if TYPE_CHECKING:
    from elspeth.contracts.results import TransformResult
```

The `TransformResult` type annotation import is guarded but not actually used in any type hints in the file. The actual `TransformResult` is imported inside the test methods directly.

### PASS: Configuration Settings Coverage

**Location:** Lines 103-119, 211-227

Tests properly configure `RetrySettings` with realistic values:

```python
retry=RetrySettings(
    max_attempts=3,
    initial_delay_seconds=0.01,  # Fast for testing
    max_delay_seconds=0.1,
),
```

The comment "Fast for testing" shows deliberate consideration of test execution time.

## Verdict

**PASS** - This is a well-structured test file that correctly uses the production code path for graph construction, makes meaningful assertions about retry behavior, and covers both success-after-retry and retry-exhaustion scenarios. The tests are efficient with fast delay settings and properly implement test plugins using the base classes.

**Recommendations:**
1. Remove the unused `TYPE_CHECKING` import for `TransformResult` (minor cleanup)
2. Consider adding a test for non-retryable errors (errors that should not trigger retry)
3. Consider adding a test that verifies retry backoff timing is respected
