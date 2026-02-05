# Test Audit: test_processor_guards.py

**File:** `tests/engine/test_processor_guards.py`
**Lines:** 263
**Auditor:** Claude Code
**Date:** 2026-02-05

## Summary

This file tests safety guards in RowProcessor, specifically the `MAX_WORK_QUEUE_ITERATIONS` guard that prevents infinite loops from bugs in pipeline processing. The tests verify the guard constant value and that it fires correctly on runaway loops.

## Test Path Integrity

**MIXED** - Tests have both production paths and mocked paths:
- Uses real `LandscapeDB.in_memory()` and `LandscapeRecorder`
- Uses real `RowProcessor` with proper initialization
- **However:** `test_work_queue_exceeding_limit_raises_runtime_error` uses mocking

## Findings

### 1. ISSUE: Mock-based test doesn't verify production behavior

**Location:** Lines 78-167
**Severity:** Medium

```python
def test_work_queue_exceeding_limit_raises_runtime_error(self) -> None:
    ...
    with (
        patch.object(
            processor,
            "_process_single_token",
            side_effect=lambda **kwargs: (
                mock_result,
                [_WorkItem(token=token_info, start_step=0)],
            ),
        ),
        patch("elspeth.engine.processor.MAX_WORK_QUEUE_ITERATIONS", 5),
    ):
        # Manually reimplements the work queue loop
        while work_queue:
            iterations += 1
            if iterations > limit:
                raise RuntimeError(...)
```

**Problems:**
1. **Overmocking:** Patches `_process_single_token` completely, so test doesn't verify real processing
2. **Manual reimplementation:** The test manually reimplements the work queue loop (lines 156-167) instead of calling `processor.process_row()`
3. **Tests test code, not production code:** The `RuntimeError` is raised by the TEST CODE, not by the production `RowProcessor.process_row()` method

**The test verifies that the test's loop raises an error, not that `RowProcessor.process_row()` does.**

**Recommendation:** The test should:
1. Create a transform that always produces more work (e.g., gate that always forks)
2. Call `processor.process_row()` directly
3. Verify the production code's guard fires

---

### 2. Tests that do nothing meaningful

**Location:** Lines 169-182
**Severity:** Medium

```python
def test_normal_processing_completes_without_hitting_guard(self) -> None:
    """Normal DAG processing should never approach the iteration limit."""
    # A simple linear pipeline with 10 transforms should complete
    # in exactly 10 iterations (one per transform)
    assert MAX_WORK_QUEUE_ITERATIONS > 10

    # The guard is set high enough that even complex DAGs with
    # many forks/joins should complete well under the limit
    assert MAX_WORK_QUEUE_ITERATIONS > 1000
```

**Problem:** This test:
1. Doesn't create a processor
2. Doesn't process any rows
3. Only asserts that 10,000 > 10 and 10,000 > 1000

**This is a non-test - it always passes regardless of whether normal processing works.**

---

### 3. Redundant constant verification

**Location:** Lines 70-76, 250-263
**Severity:** Low

```python
def test_max_work_queue_iterations_constant_value(self) -> None:
    assert MAX_WORK_QUEUE_ITERATIONS == 10_000

def test_guard_constant_is_reasonable(self) -> None:
    assert MAX_WORK_QUEUE_ITERATIONS >= 1000
    assert MAX_WORK_QUEUE_ITERATIONS <= 100_000
    assert MAX_WORK_QUEUE_ITERATIONS == 10_000
```

**Issue:** Both tests verify the constant is 10,000. This is:
1. Redundant
2. Not particularly valuable - if someone changes the constant, they can update the test
3. The "sanity check" framing is misleading - this doesn't catch bugs

**Recommendation:** One constant verification test is sufficient.

---

### 4. Good Pattern: Real processing test

**Location:** Lines 184-248
**Assessment:** GOOD

```python
def test_iteration_guard_exists_in_process_row(self) -> None:
    ...
    results = processor.process_row(
        row_index=0,
        source_row=SourceRow.valid({"value": 42}, contract=...),
        transforms=[transform],
        ctx=ctx,
    )

    # If we get here without RuntimeError, the guard didn't fire
    assert len(results) >= 1
```

This test:
1. Creates real processor
2. Calls real `process_row()`
3. Verifies normal processing completes

However, it only verifies the guard **doesn't** fire, not that it **would** fire on infinite loops.

---

## Missing Coverage

### 1. CRITICAL: No test that production guard fires

**Severity:** High

There's no test that:
1. Creates a processor with production code
2. Causes an infinite loop scenario
3. Verifies `RowProcessor.process_row()` raises `RuntimeError`

The existing test (finding #1) patches the internals and reimplements the loop.

### 2. No test for `process_token_from_step` guard

The `process_token_from_step()` method also has the iteration guard (see processor.py lines 400-437) but no tests verify this code path.

---

## Test Discovery Issues

**PASS** - Test class properly named:
- `TestProcessorGuards`

---

## Verdict

**FAIL - Critical test quality issues**

### Critical Issues:
1. **Mock-based test doesn't test production code:** The main guard test patches internals and manually reimplements the loop, so it doesn't verify the production `RowProcessor` behavior.

2. **Test that does nothing:** `test_normal_processing_completes_without_hitting_guard` makes only trivial assertions about the constant value.

### Recommendations:
1. **Rewrite `test_work_queue_exceeding_limit_raises_runtime_error`** to:
   - Create a gate that always forks to itself (or similar pathological scenario)
   - Patch only `MAX_WORK_QUEUE_ITERATIONS` to a low value (e.g., 5)
   - Call `processor.process_row()` directly
   - Verify `RuntimeError` is raised by production code

2. **Rewrite `test_normal_processing_completes_without_hitting_guard`** to actually process rows through a multi-step pipeline and verify completion without hitting the guard.

3. **Remove redundant constant tests** - one is sufficient.

4. **Add test for `process_token_from_step` guard** if that code path is used in production.
