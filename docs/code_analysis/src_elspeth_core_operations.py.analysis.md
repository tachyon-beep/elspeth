# Analysis: src/elspeth/core/operations.py

**Lines:** 181
**Role:** Operation lifecycle management for source/sink I/O. Provides the `track_operation` context manager that handles operation creation, completion, duration tracking, exception capture, context wiring, and audit integrity enforcement. Operations are the source/sink equivalent of node_states in the audit trail.
**Key dependencies:** Imports `BatchPendingError` from `elspeth.contracts`, `Operation` and `LandscapeRecorder` (TYPE_CHECKING), `PluginContext`. Imported by `src/elspeth/engine/orchestrator/core.py` and `src/elspeth/engine/executors.py`.
**Analysis depth:** FULL

## Summary

This is a well-designed context manager that correctly handles a complex matrix of exception and audit-write scenarios. The code demonstrates careful thought about audit integrity -- if the audit write fails after a successful operation, the run must fail (Tier 1 trust rules). The `BaseException` handler for `KeyboardInterrupt`/`SystemExit` is important and correctly ordered. There is one warning about a subtle edge case in the `finally` block's error handling, and one observation about the `BatchPendingError` control flow pattern.

## Warnings

### [151-178] DB error during finally block after BaseException swallows the original BaseException

**What:** When a `BaseException` (e.g., `KeyboardInterrupt`) is raised inside the `with` block, the exception handlers at lines 142-150 set `original_exception` and re-raise. The `finally` block then calls `recorder.complete_operation()`. If that DB call ALSO raises an `Exception`, the code at line 176 checks `if original_exception is None` -- it's not None, so the DB error is logged and the original exception "propagates." However, the actual Python semantics here are subtle: the `raise` at line 150 has already initiated propagation of the `BaseException`. The `finally` block runs during that propagation. If the `except Exception as db_error` block at line 161 catches a DB error, the `raise` at line 177 would replace the original `BaseException` with the DB error. But since `original_exception is not None`, we fall through to the implicit end of the `except` block, and the original exception continues propagating.

This is actually correct behavior, but the interaction between `raise` in the exception handler, `finally` semantics, and `except` within `finally` is subtle enough that it deserves a note: if `complete_operation()` raises a `BaseException` (not just `Exception`) -- for example, another `KeyboardInterrupt` during the DB write -- it would NOT be caught by `except Exception as db_error`, and the original exception would be replaced by the new `BaseException`. This is an extremely unlikely edge case (two `KeyboardInterrupt`s in sequence), but in a system where audit integrity is paramount, it's worth documenting.

**Why it matters:** In the double-interrupt scenario, the operation would be left in "open" status with no audit record of the original error. The original exception information would be lost. For an emergency dispatch system, this could mean an incomplete audit trail for a critical operation.
**Evidence:**
```python
except BaseException as e:
    status = "failed"
    error_msg = str(e)
    original_exception = e
    raise
finally:
    # ...
    try:
        recorder.complete_operation(...)
    except Exception as db_error:  # Only catches Exception, not BaseException
        # ...
        if original_exception is None:
            raise
        # else: falls through, original BaseException propagates
```

### [121] Context operation_id swap is not atomic

**What:** Lines 121-122 save and restore `ctx.operation_id`:
```python
previous_operation_id = ctx.operation_id
ctx.operation_id = operation.operation_id
```
And line 181 restores it in `finally`:
```python
ctx.operation_id = previous_operation_id
```
If `track_operation` is used with concurrent access to `ctx` (e.g., two operations on the same PluginContext from different threads), the save/restore pattern creates a race condition.
**Why it matters:** Current usage appears to be single-threaded per context (one source load, then sequential sink writes). But the pattern is fragile -- if orchestrator concurrency ever allows parallel sink writes with the same context, the operation_id could be corrupted.
**Evidence:** `PluginContext` is a mutable dataclass with no synchronization. The orchestrator creates separate contexts per operation, so this is safe in current usage.
**Mitigating factor:** Each operation gets its own PluginContext in practice. The save/restore is defensive for potential nesting (operation within operation), not for concurrency.

## Observations

### [131-136] BatchPendingError handling is correctly distinguished from failures

**What:** `BatchPendingError` is caught separately and marks the operation as "pending" rather than "failed." This is a control-flow signal for async batch processing (e.g., waiting for LLM batch results).
**Why it matters:** This distinction is critical for the audit trail. A "pending" operation means "still in progress, will complete later" while "failed" means "something went wrong." Conflating these would make the audit trail misleading. The re-raise after setting status ensures the caller can handle the pending state.

### [137-150] Exception ordering is correct (Exception before BaseException)

**What:** `except Exception` appears before `except BaseException`, which is the correct order. Python matches exception handlers top-to-bottom, and `Exception` is a subclass of `BaseException`. Reversing the order would make the `Exception` handler unreachable.
**Why it matters:** The comment on line 146 ("Must come AFTER except Exception") indicates this was a deliberate fix (BUG #10). Good defensive documentation.

### [160-178] Audit integrity enforcement follows Tier 1 rules correctly

**What:** If `complete_operation()` fails (DB error) and the original operation succeeded (`original_exception is None`), the DB error is raised -- forcing the run to fail. If the original operation also failed, the original exception takes priority (DB error is logged).
**Why it matters:** This correctly implements the Data Manifesto principle: "A successful operation with a missing audit record violates Tier-1 trust rules." The run must not continue if audit integrity is compromised.

### [36-51] OperationHandle provides clean output capture pattern

**What:** The `OperationHandle` dataclass with mutable `output_data` allows callers to set output data during the operation without passing it back through the context manager's yield.
**Why it matters:** Clean API design. The caller can set `handle.output_data = {...}` at any point during the operation, and it's captured at completion time.

## Verdict

**Status:** SOUND
**Recommended action:** Document the double-BaseException edge case (line 161's `except Exception` not catching `BaseException`). This is extremely unlikely but worth a comment for future maintainers given the audit integrity requirements. No code change needed -- the behavior is acceptable.
**Confidence:** HIGH -- The context manager covers all exception paths correctly. The audit integrity enforcement logic is well-reasoned. The subtle edge case with double BaseException is theoretical and acceptable for the risk profile.
