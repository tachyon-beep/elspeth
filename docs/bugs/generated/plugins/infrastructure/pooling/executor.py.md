## Summary

`PooledExecutor.execute_batch()` converts unexpected worker exceptions into `TransformResult.error("unexpected_pool_error")`, so bugs in `process_fn` are misclassified as row-level transform failures instead of crashing the run.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `src/elspeth/plugins/infrastructure/pooling/executor.py`
- Line(s): 320-337
- Function/Method: `_execute_batch_locked`

## Evidence

`_execute_batch_locked()` catches every non-`FrameworkBugError` / non-`AuditIntegrityError` from worker futures and fabricates a row-level error result:

```python
try:
    _returned_idx, result = future.result()
except (FrameworkBugError, AuditIntegrityError):
    raise
except Exception as exc:
    result = TransformResult.error(
        {
            "reason": "unexpected_pool_error",
            "error": f"{type(exc).__name__}: {exc}",
        },
        retryable=False,
    )
self._buffer.complete(buffer_idx, result)
```

Source: [executor.py](/home/john/elspeth/src/elspeth/plugins/infrastructure/pooling/executor.py#L320)

That conflicts with the engine’s contract for plugin failures. `TransformExecutor` explicitly documents that `TransformResult.error()` is for legitimate processing failures, while exceptions are bugs and must propagate:

- [transform.py](/home/john/elspeth/src/elspeth/engine/executors/transform.py#L139)
- [transform.py](/home/john/elspeth/src/elspeth/engine/executors/transform.py#L305)

Once the executor fabricates `TransformResult.error`, the processor treats it as a normal routed/quarantined transform failure instead of a system crash:

- [processor.py](/home/john/elspeth/src/elspeth/engine/processor.py#L1591)
- [processor.py](/home/john/elspeth/src/elspeth/engine/processor.py#L1662)

The current tests even codify this masking behavior by asserting that a `RuntimeError("Unexpected kaboom")` from `process_fn` becomes an `"unexpected_pool_error"` result rather than propagating:

- [test_pooled_executor.py](/home/john/elspeth/tests/unit/plugins/llm/test_pooled_executor.py#L1080)

What the code does:
- Hides arbitrary worker exceptions behind a synthetic transform error.

What it should do:
- Only convert explicitly modeled row-level failures into `TransformResult.error`.
- Re-raise unexpected exceptions from `process_fn` so plugin bugs crash immediately, per CLAUDE.md’s “plugin method throws exception -> CRASH” rule.

## Root Cause Hypothesis

The executor is trying to preserve reorder-buffer integrity by always completing every reserved slot, but it conflates “keep buffer consistent” with “downgrade arbitrary exceptions into data errors.” The buffer-recovery concern is real, but the chosen mechanism violates the project’s plugin-ownership/error-contract rules.

## Suggested Fix

Do not synthesize `TransformResult.error` for unexpected worker exceptions.

A safe pattern is:
- Re-raise unexpected exceptions from `future.result()`.
- If buffer consistency still needs protection, add a dedicated fatal-path mechanism that marks the batch unusable without converting the exception into a normal transform failure.

For example, the broad `except Exception` branch should be removed or narrowed to only executor-owned shutdown/cancellation cases, not plugin/runtime bugs.

## Impact

Plugin bugs inside pooled execution can be recorded as ordinary transform failures and routed to `on_error` sinks or quarantine paths. That breaks the “exceptions are bugs and propagate” contract, hides defects in system-owned plugins, and pollutes the audit trail with misleading row-level failure records instead of an honest run crash.
---
## Summary

`shutdown(wait=False)` does not reliably stop queued workers before they make their first external call; `_execute_single()` checks shutdown only in the retry path, so pending work can still dispatch after shutdown was requested.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `src/elspeth/plugins/infrastructure/pooling/executor.py`
- Line(s): 175-182, 376-378, 404-406, 455-467, 515-523
- Function/Method: `shutdown`, `_wait_for_dispatch_gate`, `_execute_single`

## Evidence

`shutdown()` sets `_shutdown_event`:

- [executor.py](/home/john/elspeth/src/elspeth/plugins/infrastructure/pooling/executor.py#L175)

But `_execute_single()` does not check that event before the normal dispatch call:

```python
while True:
    self._wait_for_dispatch_gate()
    try:
        result = process_fn(row, state_id)
        self._throttle.on_success()
        return (buffer_idx, result)
```

Source: [executor.py](/home/john/elspeth/src/elspeth/plugins/infrastructure/pooling/executor.py#L455)

The gate itself notices shutdown only while sleeping for pacing:

```python
if self._shutdown_event.is_set():
    break
```

Source: [executor.py](/home/john/elspeth/src/elspeth/plugins/infrastructure/pooling/executor.py#L404)

But after that `break`, `_execute_single()` still calls `process_fn` unconditionally. And if `min_dispatch_delay_ms <= 0`, `_wait_for_dispatch_gate()` returns immediately without consulting `_shutdown_event` at all:

- [executor.py](/home/john/elspeth/src/elspeth/plugins/infrastructure/pooling/executor.py#L376)

There is a shutdown check later, but only after a retryable exception has already happened:

- [executor.py](/home/john/elspeth/src/elspeth/plugins/infrastructure/pooling/executor.py#L515)

So shutdown preempts retries, but not first dispatches from already-submitted work.

What the code does:
- Lets queued/pending workers reach `process_fn` after shutdown unless they happen to be on a retry path.

What it should do:
- Bail out with `shutdown_requested` before invoking `process_fn` whenever `_shutdown_event` is set.

## Root Cause Hypothesis

Shutdown handling was added to the retry loop and submission path, but not to the main “about to call `process_fn`” path. The executor assumes the gate is enough, but the gate only short-circuits sleep; it does not prevent the subsequent dispatch.

## Suggested Fix

Add an explicit shutdown check immediately before `process_fn(row, state_id)` and after `_wait_for_dispatch_gate()` returns. That check should return a deterministic `TransformResult.error({"reason": "shutdown_requested", ...})` without making the external call.

It would also be safer for `_wait_for_dispatch_gate()` to return a boolean such as “dispatch allowed” vs “shutdown interrupted,” so `_execute_single()` cannot accidentally proceed after a shutdown break.

## Impact

During graceful shutdown, queued pool work can still hit external services after the system has requested stop. That can produce extra billable API calls, side effects after teardown began, and misleading operational behavior where shutdown appears acknowledged but new work is still dispatched.
