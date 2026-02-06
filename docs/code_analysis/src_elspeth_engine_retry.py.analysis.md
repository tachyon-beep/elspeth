# Analysis: src/elspeth/engine/retry.py

**Lines:** 146
**Role:** Provides configurable retry logic for transform execution using tenacity. Wraps operations with exponential backoff, jitter, and retryable error filtering. Integrates with the audit trail via an `on_retry` callback for recording retry attempts.
**Key dependencies:**
- Imports: `tenacity` (Retrying, RetryError, retry_if_exception, stop_after_attempt, wait_exponential_jitter, RetryCallState), `RuntimeRetryProtocol` (contracts.config)
- Imported by: `engine/processor.py` (RowProcessor._execute_transform_with_retry), `engine/orchestrator/core.py` (creates RetryManager), `engine/__init__.py` (re-exports), `contracts/results.py` (TYPE_CHECKING for MaxRetriesExceeded)
**Analysis depth:** FULL

## Summary

RetryManager is a compact and well-designed wrapper around tenacity. The implementation correctly converts tenacity's 1-based attempt numbering to 0-based for audit convention, uses `before_sleep` hook for retry callbacks (ensuring callbacks fire only on actual retries, not on the final exhausted attempt), and wraps tenacity's `RetryError` into a domain-specific `MaxRetriesExceeded`. The most notable concern is that the `on_retry` callback is never actually used by the primary caller (RowProcessor), meaning retry attempts are not individually audited in the Landscape, despite the module docstring describing this as the integration point. Overall the code is sound and low-risk.

## Warnings

### [78-83, 1304-1307 in processor.py] on_retry callback is documented but never wired in production

**What:** The `execute_with_retry` method accepts an `on_retry` callback (line 83) described as the integration point for `recorder.record_retry_attempt()` (module docstring lines 11-15). However, the only production caller in `RowProcessor._execute_transform_with_retry` (processor.py line 1304) does NOT pass `on_retry`:

```python
# processor.py line 1304-1307
return self._retry_manager.execute_with_retry(
    operation=execute_attempt,
    is_retryable=is_retryable,
    # NO on_retry parameter
)
```

**Why it matters:** This means retry attempts are NOT individually audited in the Landscape audit trail. If a transform succeeds on attempt 3 after failing on attempts 1 and 2, the audit trail only records the final successful attempt's node_state. The failed intermediate attempts are invisible. For an audit system built on "if it's not recorded, it didn't happen," this is a significant gap in traceability. The docstring says "each retry attempt must be auditable" but the integration is not wired.

**Evidence:** The module docstring at lines 10-15 describes `on_retry` as the mechanism for `recorder.record_retry_attempt()`, and the processor at line 1304 invokes `execute_with_retry` without it.

### [130] attempt variable tracks tenacity's 1-based attempt_number

**What:** The `attempt` variable (line 103, initially 0) is updated at line 130 to `attempt_state.retry_state.attempt_number`, which is 1-based in tenacity. This value is then passed to `MaxRetriesExceeded(attempt, final_error)` at line 143.

**Why it matters:** `MaxRetriesExceeded.attempts` is documented as "the number of attempts" but receives tenacity's 1-based `attempt_number`. This is actually correct for the semantic meaning (3 means 3 attempts were made), but the field name `attempts` could be confused with the 0-based convention used for `on_retry` callbacks (line 114: `attempt_number - 1`). The inconsistency between 0-based in callbacks and 1-based in the exception could cause bugs in callers that don't read the docstring carefully.

**Evidence:**
```python
# Line 130 - 1-based from tenacity
attempt = attempt_state.retry_state.attempt_number

# Line 114 - converted to 0-based for callback
on_retry(retry_state.attempt_number - 1, exc)

# Line 143 - 1-based passed to exception
raise MaxRetriesExceeded(attempt, final_error) from e
```

### [125] is_retryable predicate exceptions propagate unhandled

**What:** The `is_retryable` callback is passed to tenacity's `retry_if_exception(is_retryable)`. If `is_retryable` itself raises an exception (e.g., accessing an attribute on a non-standard exception type), tenacity does NOT catch it -- it propagates as an unhandled exception, bypassing the `RetryError` / `MaxRetriesExceeded` path.

**Why it matters:** The caller (RowProcessor) uses `isinstance(e, LLMClientError)` and then accesses `e.retryable`. If `e` is an `LLMClientError` but somehow `retryable` is missing (shouldn't happen for a dataclass/proper class, but worth noting), the `AttributeError` would crash outside the retry loop with no `MaxRetriesExceeded` wrapping.

**Evidence:**
```python
# In processor.py
def is_retryable(e: BaseException) -> bool:
    if isinstance(e, LLMClientError):
        return e.retryable  # Could raise AttributeError if LLMClientError malformed
    return isinstance(e, ConnectionError | TimeoutError | OSError)
```
Per the project's trust model, `LLMClientError` is system code (Tier 1), so bugs should crash. This is therefore correct behavior per CLAUDE.md, but worth documenting.

## Observations

### [126] reraise=False is correct for the wrapper pattern

**What:** `reraise=False` prevents tenacity from re-raising the original exception when retries are exhausted. Instead, it raises `RetryError`, which is caught at line 137 and converted to `MaxRetriesExceeded`.

**Why it matters:** Positive observation -- this ensures all exhausted-retry scenarios go through the `MaxRetriesExceeded` path, giving callers a uniform exception type to handle.

### [109-114] before_sleep_handler correctly guards against None outcome

**What:** The handler checks `retry_state.outcome` is not None before accessing `.exception()`. This guards against edge cases in tenacity where `before_sleep` might be called without an outcome (unlikely in practice but defensive).

**Why it matters:** Minor positive observation.

### [127] Conditional before_sleep is a micro-optimization

**What:** `before_sleep=before_sleep_handler if on_retry else None` avoids registering the hook when no callback is provided. This prevents tenacity from calling an empty function on every retry.

**Why it matters:** Minor positive observation -- clean and intentional.

### [103-104] Local variables for attempt tracking

**What:** `attempt` and `last_error` are tracked as local variables rather than instance state. This means `RetryManager` is stateless and thread-safe (multiple concurrent calls to `execute_with_retry` don't interfere).

**Why it matters:** Positive observation -- the stateless design is correct for a manager that's shared across rows.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** The primary issue is that `on_retry` is never wired in RowProcessor, meaning individual retry attempts are not audited. This should be addressed either by: (1) wiring the `on_retry` callback to `recorder.record_retry_attempt()` in the processor, or (2) updating the docstring to reflect that retry auditing is deferred/unimplemented and noting this as a known gap. The attempt numbering inconsistency (0-based in callbacks, 1-based in `MaxRetriesExceeded`) should be documented explicitly.
**Confidence:** HIGH -- Complete analysis with cross-reference to RowProcessor, tenacity internals, and RuntimeRetryProtocol. The `on_retry` gap was verified by searching all callers of `execute_with_retry`.
