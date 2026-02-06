# BUG #10: Operation Status Recorded as Completed on BaseException

**Issue ID:** elspeth-rapid-8rjp
**Priority:** P1
**Status:** CLOSED
**Date Opened:** 2026-02-05
**Date Closed:** 2026-02-05
**Component:** core-landscape (operations.py)

## Summary

The `track_operation` context manager only caught `Exception`, not `BaseException`. System interrupts like KeyboardInterrupt (Ctrl+C) and SystemExit bypassed exception handlers, leaving `status = "completed"` (the initial value). This caused the audit trail to incorrectly record interrupted operations as successful.

## Impact

- **Severity:** High - Tier-1 audit trail integrity
- **Effect:** Operations interrupted by KeyboardInterrupt or SystemExit recorded as "completed"
- **Risk:** Audit trail would show successful operations that were actually interrupted by user or system

## Root Cause

Python's exception hierarchy has `BaseException` as the root, with `Exception` as a subclass:

```
BaseException
├── KeyboardInterrupt  ← Not caught by except Exception
├── SystemExit         ← Not caught by except Exception
├── GeneratorExit      ← Not caught by except Exception
└── Exception          ← Caught at line 137
```

The `track_operation` context manager (lines 129-141) had:
1. `except BatchPendingError:` - control flow signal
2. `except Exception as e:` - normal exceptions
3. **MISSING:** `except BaseException:` - system interrupts

When a user pressed Ctrl+C or the system raised SystemExit:
- Neither except block caught it
- The finally block executed with `status = "completed"` (initial value from line 125)
- The operation was recorded as successful when it was actually interrupted

## Files Affected

- `src/elspeth/core/operations.py` (lines 124-141)

## Fix

Added `except BaseException` handler AFTER the `except Exception` handler:

```python
except Exception as e:
    status = "failed"
    error_msg = str(e)
    original_exception = e
    raise
except BaseException as e:
    # Catch system interrupts (KeyboardInterrupt, SystemExit, etc.)
    # These are NOT Exception subclasses, so they bypass the above handler.
    # Without this, interrupted operations would be recorded as "completed".
    status = "failed"
    error_msg = str(e)
    original_exception = e
    raise
```

**Order matters:** The `except BaseException` block MUST come after `except Exception`. Python evaluates except clauses in order, and since `Exception` is a subclass of `BaseException`, putting the parent first would catch everything (including normal exceptions).

## Test Coverage

Added comprehensive test in `tests/core/landscape/test_operations.py`:

```python
def test_track_operation_on_base_exception_marks_failed(self, ...)
```

**Test strategy:**
1. Create operation using `track_operation` context manager
2. Raise `KeyboardInterrupt()` within the context
3. Verify operation status is "failed" (not "completed")
4. Verify the exception is re-raised (not swallowed)

**Test results:**
- RED: Test failed initially (status was "completed" instead of "failed")
- GREEN: Test passed after fix (status correctly set to "failed")
- All 42 operations tests pass

## Verification

```bash
# Run specific test
.venv/bin/python -m pytest tests/core/landscape/test_operations.py::TestTrackOperationContextManager::test_track_operation_on_base_exception_marks_failed -xvs

# Run all operations tests
.venv/bin/python -m pytest tests/core/landscape/test_operations.py -x
```

**Results:** All 42 tests pass

## Pattern Observed

This is the third instance of exception handling gaps in Tier-1 code:
1. Bug #3 (database_ops) - missing rowcount validation after writes
2. Bug #7 (routing payloads) - missing payload storage
3. **Bug #10 (this bug)** - missing BaseException handling

**Lesson:** Exception handlers that should be exhaustive must explicitly handle BaseException, not just Exception. System interrupts (KeyboardInterrupt, SystemExit) are NOT Exception subclasses and require separate handling.

## Python Exception Hierarchy Reference

```python
BaseException
├── SystemExit         # sys.exit()
├── KeyboardInterrupt  # Ctrl+C
├── GeneratorExit      # generator.close()
└── Exception          # All "normal" exceptions
    ├── StopIteration
    ├── ArithmeticError
    │   └── ZeroDivisionError
    ├── LookupError
    │   └── KeyError
    └── ... (all user-defined exceptions should inherit from Exception)
```

Most code should only catch `Exception`. But context managers that track lifecycle state (like `track_operation`) must also handle `BaseException` to ensure cleanup code runs correctly even on system interrupts.

## TDD Cycle Duration

- RED (write failing test): 5 minutes
- GREEN (implement fix): 3 minutes
- Verification (run all tests): 3 minutes
- **Total:** ~11 minutes

## Related Bugs

- Part of Group 1: Tier-1 Audit Trail Integrity (10 bugs total)
- Follows same pattern as Bugs #1-9 (validation gaps in Tier-1 code)
