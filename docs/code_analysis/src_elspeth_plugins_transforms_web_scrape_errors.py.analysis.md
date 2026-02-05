# Analysis: src/elspeth/plugins/transforms/web_scrape_errors.py

**Lines:** 110
**Role:** Error hierarchy for the web scrape transform. Defines retryable and non-retryable error classes that control engine retry behavior.
**Key dependencies:** None (standalone module). Consumed by `web_scrape.py`. Also imported by test files.
**Analysis depth:** FULL

## Summary

This is a clean, well-organized error hierarchy that correctly separates retryable from non-retryable errors. The `retryable` flag on the base class is the mechanism the engine uses to decide retry vs. error-routing. One critical finding: the `TimeoutError` class shadows the Python built-in `TimeoutError`, which could cause confusion in exception handling. One warning about the unused `TimeoutError` and `ConversionTimeoutError` classes.

## Critical Findings

### [40] `TimeoutError` shadows Python built-in `TimeoutError`

**What:** The class `TimeoutError(WebScrapeError)` on line 40 shadows Python's built-in `TimeoutError` (which is a subclass of `OSError`). Any code in a module that imports this class with `from web_scrape_errors import TimeoutError` will lose access to the built-in `TimeoutError` unless it explicitly uses `builtins.TimeoutError`.

**Why it matters:** This creates a real risk of incorrect exception handling. If any code within the web scrape module or its callers writes `except TimeoutError` intending to catch Python's built-in timeout (e.g., from `socket.timeout` which is an alias for built-in `TimeoutError`), it would instead catch only `WebScrapeError` subclasses, letting real system timeouts propagate unhandled. Conversely, code intending to catch web scrape timeouts could accidentally catch system-level timeouts if the import order is wrong. Currently, `web_scrape.py` does not import this class (it handles timeouts via `httpx.TimeoutException` directly), so the bug is latent rather than active.

**Evidence:**
```python
class TimeoutError(WebScrapeError):
    """HTTP 408 Request Timeout."""
```
Python's `builtins.TimeoutError` is available globally. This class name collision is a known antipattern.

## Warnings

### [40-44, 106-110] `TimeoutError` and `ConversionTimeoutError` are defined but never used

**What:** Neither `TimeoutError` (HTTP 408) nor `ConversionTimeoutError` (HTML conversion timeout) is imported or raised anywhere in the production code. The main `web_scrape.py` file does not import them. There is no HTTP 408 handling in `_fetch_url()`.

**Why it matters:** Unused error classes are dead code. Per the project's No Legacy Code policy, unused code should be removed. If HTTP 408 handling is planned for the future, it should be added when implemented, not pre-declared. The presence of these unused exceptions gives a false impression that HTTP 408 and conversion timeout scenarios are handled.

**Evidence:** Searching for imports across the codebase:
- `web_scrape.py` imports: `ForbiddenError`, `NetworkError`, `NotFoundError`, `RateLimitError`, `ServerError`, `UnauthorizedError`, `WebScrapeError` -- but NOT `TimeoutError`, `ConversionTimeoutError`, `SSLError`, `InvalidURLError`, `ParseError`, `SSRFBlockedError`, or `ResponseTooLargeError`.
- Test files import `TimeoutError` and other errors for testing the error hierarchy itself, but no production code raises them.

### [71-82] `SSLError`, `InvalidURLError`, `ParseError`, `SSRFBlockedError`, `ResponseTooLargeError` are also unused in production

**What:** These five error classes are defined but never raised in `web_scrape.py`. URL validation errors are caught as generic `Exception` on line 158 of `web_scrape.py`, not as `InvalidURLError`. SSRF blocking uses `validate_ip`/`validate_url_scheme` which raise their own exceptions, not `SSRFBlockedError`.

**Why it matters:** Same as above -- dead code. The error hierarchy defines a comprehensive set of error types, but the actual `web_scrape.py` only uses a subset. This means the error handling in `web_scrape.py` is less structured than the error hierarchy suggests.

## Observations

### [8-13] Base class `retryable` flag pattern is clean

**What:** `WebScrapeError.__init__` accepts a `retryable` keyword argument, and each subclass hardcodes its retryability. This is a clean pattern that makes retry decisions declarative and centralized.

### [19-44] Retryable error classification is correct

**What:** `RateLimitError` (429), `NetworkError` (DNS/timeout/connection), `ServerError` (5xx), and `TimeoutError` (408) are all correctly marked retryable. These are all transient errors where a retry is likely to succeed.

### [50-110] Non-retryable error classification is correct

**What:** `NotFoundError` (404), `ForbiddenError` (403), `UnauthorizedError` (401), `SSLError`, `InvalidURLError`, `ParseError`, `SSRFBlockedError`, `ResponseTooLargeError`, and `ConversionTimeoutError` are all correctly marked non-retryable. Retrying these would waste resources without changing the outcome.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** (1) Rename `TimeoutError` to `HTTPTimeoutError` or `RequestTimeoutError` to avoid shadowing the Python built-in. (2) Consider removing unused error classes per the No Legacy Code policy, or wire them into `web_scrape.py` to actually use them.
**Confidence:** HIGH -- The file is simple and the issues are clear-cut.
