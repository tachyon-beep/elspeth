# Analysis: src/elspeth/engine/clock.py

**Lines:** 111
**Role:** Provides a Clock protocol abstraction for testable timeout logic. SystemClock wraps `time.monotonic()` for production use. MockClock provides deterministic time control for tests. A module-level `DEFAULT_CLOCK` singleton is shared across all components that don't inject a specific clock.
**Key dependencies:**
- Imports: `time` (stdlib), `Protocol` (typing)
- Imported by: `engine/triggers.py`, `engine/executors.py`, `engine/processor.py`, `engine/coalesce_executor.py`, `engine/orchestrator/core.py` (all use `DEFAULT_CLOCK` and/or `Clock` type)
**Analysis depth:** FULL

## Summary

The clock module is minimal, clean, and correctly implements the protocol pattern. The `Clock` protocol enables dependency injection for testability, and `MockClock` provides sufficient control for deterministic tests. The only notable concern is the `MockClock.set()` method which can move time backwards, violating the monotonic contract. This is documented with a warning but the method exists and could be misused in tests, potentially creating bugs that only manifest when tests are reordered or extended. The `DEFAULT_CLOCK` singleton pattern is appropriate for this use case.

## Warnings

### [96-107] MockClock.set() can violate monotonic contract

**What:** The `set()` method allows setting time to any value, including values less than the current time. The docstring warns "Unlike advance(), this can set time to any value including earlier times. Use with caution -- monotonic clocks shouldn't go backwards in production." However, the method has no guard to prevent backward time movement.

**Why it matters:** If a test uses `set()` to move time backwards, any component relying on elapsed time calculations (like TriggerEvaluator's `batch_age_seconds`) will compute negative durations. For example, if `first_accept_time` is 10.0 and `set(5.0)` is called, `batch_age_seconds` returns -5.0. This could cause:
- Timeout triggers to never fire (negative age is always less than positive timeout)
- Negative durations recorded in audit trail if used during integration tests
- Checkpoint/restore logic computing negative offsets

The `advance()` method correctly validates non-negative input (line 92-93), but `set()` does not. While `set()` is test-only, tests are the safety net -- if the safety net itself can produce impossible states, test results may not be trustworthy.

**Evidence:**
```python
def set(self, value: float) -> None:
    """Set mock time to an absolute value.
    ...
    Note:
        Unlike advance(), this can set time to any value including
        earlier times. Use with caution - monotonic clocks shouldn't
        go backwards in production.
    """
    self._current = value  # No guard against backwards movement
```

## Observations

### [110-111] DEFAULT_CLOCK is a module-level singleton

**What:** `DEFAULT_CLOCK: Clock = SystemClock()` is a single instance shared by all consumers that don't inject a clock. This means TriggerEvaluator, AggregationExecutor, CoalesceExecutor, RowProcessor, and Orchestrator all share the same SystemClock instance.

**Why it matters:** This is fine for production (SystemClock delegates to `time.monotonic()` which is process-global anyway), but it means that in tests which don't inject MockClock, multiple components share real time. The pattern is correct -- the risk would only be if someone mutated `DEFAULT_CLOCK` at module level during tests, which would affect all subsequent tests. No evidence this is happening.

### [18-37] Clock protocol is well-defined

**What:** The `Clock` protocol requires only `monotonic() -> float`. This is the minimal interface needed by all consumers.

**Why it matters:** Positive observation -- the protocol is appropriately narrow. No unnecessary methods force implementors to provide capabilities they don't need.

### [40-51] SystemClock is stateless

**What:** SystemClock has no instance state and simply delegates to `time.monotonic()`.

**Why it matters:** Positive observation -- the class is trivially safe for concurrent use and imposes no overhead beyond the function call delegation.

### [71-94] MockClock.advance() correctly validates input

**What:** `advance()` raises `ValueError` for negative seconds, maintaining the monotonic invariant.

**Why it matters:** Positive observation -- prevents accidental backward time movement through the `advance()` API.

### [54-68] MockClock docstring shows correct usage pattern

**What:** The docstring demonstrates the TriggerEvaluator integration pattern clearly.

**Why it matters:** Positive observation -- good documentation for test authors.

## Verdict

**Status:** SOUND
**Recommended action:** Consider adding a guard to `MockClock.set()` that warns or raises if the new value is less than the current value, or document more prominently that `set()` should only be used to establish initial state before any clock-dependent operations begin. This is low priority since MockClock is test-only code.
**Confidence:** HIGH -- The module is small, self-contained, and its integration points are well-understood from reading all consumers.
