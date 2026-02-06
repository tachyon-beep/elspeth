# Analysis: src/elspeth/plugins/pooling/errors.py

**Lines:** 57
**Role:** Defines capacity error classification for the pooling subsystem. Contains `CAPACITY_ERROR_CODES` (frozenset of HTTP status codes 429, 503, 529), the `is_capacity_error()` predicate function, and the `CapacityError` exception class. These are used by transform plugins to signal rate-limiting/overload conditions that should trigger AIMD throttle backoff and retry in the `PooledExecutor`.
**Key dependencies:** No imports beyond `__future__`. Imported by `executor.py` (catches `CapacityError`), `prompt_shield.py`, `content_safety.py`, `openrouter_multi_query.py`, `azure_multi_query.py`, and multiple test files. The `is_capacity_error()` function is used by `prompt_shield.py` and `content_safety.py` to convert HTTP status codes into `CapacityError` exceptions.
**Analysis depth:** FULL

## Summary

This is a minimal, well-defined module with clear semantics. The capacity error codes are correct for the target APIs (Azure OpenAI, OpenRouter). The `CapacityError` exception carries the HTTP status code for audit trail inclusion. I found one concern: there's a dual mechanism for signaling capacity errors (`CapacityError` and `LLMClientError` with `retryable=True`), which creates ambiguity about which exception type to use. This is already handled correctly in the executor but could confuse future plugin authors.

## Warnings

### [36-57] `CapacityError` and `LLMClientError` serve overlapping roles for retry signaling

**What:** The executor's retry loop at `executor.py:410` catches both `CapacityError` and `LLMClientError`:
```python
except (CapacityError, LLMClientError) as e:
```

`CapacityError` is raised by non-LLM transforms (e.g., `prompt_shield.py`, `content_safety.py`) that make direct HTTP calls and detect capacity codes. `LLMClientError` (and its subclasses `RateLimitError`, `ServerError`, `NetworkError`) is raised by the `AuditedLLMClient` for LLM-specific errors.

Both exception types signal "retryable" conditions but via different mechanisms:
- `CapacityError`: Always retryable (line 57: `self.retryable = True`), carries `status_code`
- `LLMClientError`: `retryable` is a constructor parameter, subclasses set it explicitly

The executor checks `isinstance(e, LLMClientError) and not e.retryable` at line 418 to short-circuit non-retryable LLM errors. But `CapacityError` is always retried (it doesn't check `retryable`).

**Why it matters:** If a future plugin author raises `CapacityError` for a non-retryable condition (which would be a misuse, but the API doesn't prevent it), it would be retried regardless. The `retryable = True` attribute on `CapacityError` is never checked -- it exists for API consistency but is dead code in the current executor. This creates a subtle contract inconsistency: `CapacityError.retryable` is always `True` and always ignored, while `LLMClientError.retryable` is checked and meaningful.

### [18] `CAPACITY_ERROR_CODES` may need expansion for other providers

**What:** The frozenset contains `{429, 503, 529}`. Code 529 is Azure/Anthropic-specific ("Overloaded"). Other providers may use different codes:
- Google Cloud: 429, 503, and sometimes 500 for transient failures
- AWS Bedrock: Uses throttling exceptions, not always HTTP status codes
- OpenRouter: Already handled via `LLMClientError` path, not this code path

**Why it matters:** If new non-LLM transforms are added for other cloud providers, they might encounter provider-specific status codes that should trigger capacity retries but aren't in the frozenset. The current code is correct for the existing Azure-focused transforms, but the frozenset should be reviewed when adding new provider integrations. The `is_capacity_error()` function is the single point of truth, so expanding the set is straightforward.

## Observations

### [21-33] `is_capacity_error()` is a clean predicate with frozenset lookup

**What:** The function performs an O(1) set membership check. The frozenset is immutable (correct for a constant). The function is used by `prompt_shield.py` and `content_safety.py` at the HTTP response handling layer to decide whether to raise `CapacityError`.

### [48-49] Constructor takes `status_code` and `message` as positional parameters

**What:** Both parameters are positional:
```python
def __init__(self, status_code: int, message: str) -> None:
```
This means callers must pass them in order. Looking at usage in tests and plugins:
```python
raise CapacityError(429, "Rate limited")       # correct
raise CapacityError(status_code=429, message="Rate limited")  # also used
```
Both forms are used consistently across the codebase.

### [55-57] `super().__init__(message)` correctly sets the exception message

**What:** The base `Exception` class receives only the `message`, not the `status_code`. This means `str(e)` returns the message, and `e.status_code` is accessed as an attribute. The executor uses both: `str(e)` for the error description and `e.status_code` for the audit trail at line 444.

### Module has no logging

**What:** Unlike many other modules in the codebase, this module has no `structlog` import or logger. This is appropriate -- it's a pure data/exception definition module with no runtime behavior that would benefit from logging.

## Verdict

**Status:** SOUND
**Recommended action:** No immediate changes needed. When adding new cloud provider integrations, review `CAPACITY_ERROR_CODES` for completeness. Consider documenting the relationship between `CapacityError` and `LLMClientError` more explicitly, perhaps in the module docstring, to guide future plugin authors on which to use when.
**Confidence:** HIGH -- The module is 57 lines of straightforward exception and constant definitions. Test coverage is thorough (dedicated test file `test_capacity_errors.py` plus integration coverage in executor tests).
