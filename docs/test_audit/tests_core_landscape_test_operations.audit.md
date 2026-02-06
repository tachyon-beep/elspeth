# Test Audit: tests/core/landscape/test_operations.py

**Lines:** 1401
**Test count:** 37
**Audit status:** ISSUES_FOUND

## Summary

This is a well-structured and comprehensive test file covering the source/sink operations lifecycle, the `track_operation` context manager, and various constraint enforcement mechanisms. The tests verify critical audit trail integrity requirements (XOR constraints, call index uniqueness, thread safety). However, there are two tests with fixture issues that would cause test failures, and a few minor inefficiencies.

## Findings

### 🔴 Critical

**C1: Unused/shadowed `payload_store` fixture parameter (lines 118-119, 597-605)**

Two tests (`test_begin_operation_stores_input_data` and `test_track_operation_records_output_data`) accept a `payload_store` fixture parameter from conftest.py (which returns a `MockPayloadStore`), but then immediately shadow it by creating a new `FilesystemPayloadStore` with the same variable name:

```python
def test_begin_operation_stores_input_data(
    self, recorder: LandscapeRecorder, run_id: str, source_node_id: str, tmp_path: Any, payload_store
) -> None:
    ...
    payload_store = FilesystemPayloadStore(Path(tmp_path) / "payloads")  # Shadows the fixture!
```

This is confusing and indicates either:
1. The fixture parameter should be removed (the tests don't use it)
2. The tests were intended to use the fixture but were changed without updating the signature

While this may not cause test failures (the shadowing happens before use), it indicates potential confusion during development and creates unnecessary fixture setup overhead.

### 🟡 Warning

**W1: Redundant import inside test method (line 121, 607)**

`from pathlib import Path` is imported at module level (line 14) but is also imported inside `test_begin_operation_stores_input_data` and `test_track_operation_records_output_data`. This is unnecessary duplication:

```python
def test_begin_operation_stores_input_data(...) -> None:
    from pathlib import Path  # Redundant - already at module level
```

**W2: Type annotation inconsistency (line 118)**

`tmp_path` parameter is typed as `Any` when it should be typed as `Path`:

```python
def test_begin_operation_stores_input_data(
    self, ..., tmp_path: Any, ...  # Should be tmp_path: Path
) -> None:
```

**W3: Test uses `time.sleep()` for timing verification (lines 590, 781)**

Two tests use `time.sleep()` to verify duration recording:
- `test_track_operation_records_duration` uses `time.sleep(0.01)`
- `test_get_operations_for_run_orders_by_started_at` uses `time.sleep(0.001)`

While acceptable for this purpose, sleep-based tests can be flaky on slow CI systems. The duration test could use a more deterministic approach like mocking `time.perf_counter()`.

### 🔵 Info

**I1: Excellent test documentation**

The tests have thorough docstrings explaining the behavior being verified, including references to specific bug IDs (e.g., "BUG #10", "P1-2026-01-31-context-record-call-bypasses-allocator"). This aids maintainability and traceability.

**I2: Good separation of concerns**

Tests are well-organized into logical test classes:
- `TestOperationLifecycle` - basic CRUD
- `TestOperationDoubleComplete` - state transition validation
- `TestOperationCallRecording` - call attribution
- `TestPluginContextCallRouting` - XOR constraint at API level
- `TestTrackOperationContextManager` - context manager behavior
- `TestTrackOperationExceptionSafety` - exception handling
- `TestGetOperationsForRun` - query methods
- `TestXORConstraintAtDatabaseLevel` - database constraint verification
- `TestCallIndexUniquenessConstraints` - unique index verification
- `TestConcurrentCallIndexAllocation` - thread safety
- `TestTrackOperationContextGuards` - context cleanup

**I3: Thread safety tests are valuable**

The concurrent allocation tests (`TestConcurrentCallIndexAllocation`) verify thread safety with 100 concurrent threads, which is important for the audit trail integrity guarantees. The tests correctly acknowledge SQLite limitations and focus on verifying the allocator logic.

**I4: Comprehensive edge case coverage**

Tests cover:
- Happy path (operation lifecycle)
- Error conditions (double complete, non-existent operation)
- Exception handling (ValueError, KeyboardInterrupt, BatchPendingError)
- Database failure scenarios (DB error during complete)
- Constraint violations (XOR, uniqueness)
- Context restoration (nested operations, exception recovery)

## Verdict

**KEEP** - This is a high-quality test file with comprehensive coverage of critical audit trail functionality. The issues found are minor (shadowed fixture parameter, redundant imports, type annotation inconsistency) and do not affect test correctness. The tests effectively verify the source/sink operation audit requirements including XOR constraints, call index uniqueness, thread safety, and exception handling. The clear documentation and logical organization make this file valuable for ongoing maintenance.
