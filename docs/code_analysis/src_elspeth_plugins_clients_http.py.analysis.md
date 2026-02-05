# Analysis: src/elspeth/plugins/clients/http.py

**Lines:** 683 (including blank lines at end)
**Role:** Audited HTTP client wrapping httpx. Records every HTTP request/response to the Landscape audit trail. Handles auth header fingerprinting, JSON validation at Tier 3 boundary, binary content encoding, latency measurement, and telemetry emission.
**Key dependencies:** httpx, structlog, elspeth.contracts (CallStatus, CallType), elspeth.core.canonical (stable_hash), elspeth.core.security (get_fingerprint_key, secret_fingerprint), base.py (AuditedClientBase, TelemetryEmitCallback), telemetry.events (ExternalCallCompleted). Imported by: plugins/transforms/azure/prompt_shield.py, content_safety.py, web_scrape.py, llm/openrouter.py, openrouter_multi_query.py, context.py
**Analysis depth:** FULL

## Summary

The HTTP client is carefully constructed with strong audit trail discipline. Request/response recording, sensitive header handling, and JSON boundary validation are well-implemented. However, there is a significant resource management issue (new httpx.Client per request), massive code duplication between `post()` and `get()`, and the `_raw_text` field in JSON parse failure cases could record unbounded response bodies directly in the audit trail, bypassing payload store size management. The file is functional and secure but has structural issues that increase maintenance burden and a potential memory/storage risk.

## Critical Findings

### [304, 519] New httpx.Client created and destroyed per request
**What:** Both `post()` (line 304) and `get()` (line 519) create a new `httpx.Client` inside a `with` block for each HTTP call. This means every single request goes through full connection setup (TCP handshake, TLS negotiation) and teardown.
**Why it matters:** In production pipelines processing thousands of rows through HTTP-based transforms (web scraping, OpenRouter LLM calls), this creates:
1. **Performance degradation**: No connection reuse, no HTTP keep-alive, no connection pooling. Each request pays full TLS handshake cost (~100-300ms to most cloud APIs).
2. **Resource exhaustion risk**: Rapid request sequences can exhaust ephemeral ports or hit OS file descriptor limits, causing `OSError: [Errno 24] Too many open files` or `ConnectionError`.
3. **Server-side impact**: Many APIs track connections. Rapid connect/disconnect cycles can trigger server-side rate limiting or firewall blocks that are distinct from API-level rate limits.
**Evidence:** `http.py:304`: `with httpx.Client(timeout=effective_timeout) as client:` -- creates new client per call. The class `__init__` does not create a persistent client, and `close()` (inherited from base) is a no-op.

### [335-339, 550-554] Unbounded `_raw_text` in JSON parse failure records
**What:** When JSON parsing fails (response claims `application/json` but body is invalid), the entire raw response text is stored in `response_body` as `{"_json_parse_failed": True, "_error": error, "_raw_text": response.text}`. This dict is passed to `record_call()` as `response_data`, which is then canonicalized and stored.
**Why it matters:** External APIs can return arbitrarily large error pages masquerading as JSON (HTML error pages with `Content-Type: application/json` header). A 10MB HTML error page would be stored inline in the audit trail, bypassing the payload store's size management. The comment on line 314 says "no truncation - payload store handles size" but the payload store only handles data passed through `canonical_json().encode()` -- it does not reject or truncate. This could cause:
1. Database bloat: SQLite performance degrades with large blobs.
2. Memory pressure: Canonicalizing a 10MB string involves multiple copies.
3. Export failure: Landscape exporter may timeout or OOM on giant call records.
**Evidence:** `http.py:339`: `"_raw_text": response.text` -- no size bound. Compare with the binary path at line 353 which stores `base64.b64encode(response.content)` also without bound, but binary responses are more predictably sized.

## Warnings

### [254-467, 469-682] Massive duplication between post() and get()
**What:** The `post()` method (lines 254-467) and `get()` method (lines 469-682) share approximately 80% identical code. The only differences are: (1) HTTP method name, (2) `json` parameter vs `params` parameter, (3) the actual httpx method call. The entire response processing, audit recording, telemetry emission, and error handling blocks are copy-pasted.
**Why it matters:** Any bug fix or behavioral change must be applied in two places. This has already created a subtle divergence risk -- if a developer fixes an issue in `post()` but forgets `get()`, the audit behavior differs by HTTP method. The duplication makes the file 683 lines when it could be ~400 with a shared `_execute_request()` internal method.
**Evidence:** Lines 294-299 (post) vs 509-514 (get): identical `request_data` construction. Lines 303-417 (post) vs 518-631 (get): identical response processing and recording. Lines 420-467 (post) vs 635-682 (get): identical error handling.

### [148-155] Overly broad sensitive header detection heuristic
**What:** `_is_sensitive_header()` matches headers containing substrings "auth", "key", "secret", or "token" anywhere in the lowercased name.
**Why it matters:** This will match legitimate non-sensitive headers:
- `Content-Type` contains "t" in "ent" -- wait, no, it checks for "token" not "t". But:
- `X-Request-Token` (a correlation ID, not a secret) -- would be filtered
- `Cache-Control` contains nothing problematic -- OK
- `X-Idempotency-Key` (a request identifier, not a secret) -- would be filtered as it contains "key"
- `X-Token-Count` (a metadata header) -- would be filtered as it contains "token"
- `ETag` or `X-Auth-Method` (method description, not credential) -- "auth" match would filter
This is fail-safe (over-filter is better than under-filter for secrets), but it means audit trail consumers may be missing useful debugging headers. The `_SENSITIVE_RESPONSE_HEADERS` frozenset on line 137 uses exact matches, but the fallback heuristic on lines 150-155 is very broad.
**Evidence:** `http.py:154`: `or "token" in lower_name` would match `X-Token-Count`, `X-Ratelimit-Remaining-Tokens`, etc.

### [116] Type annotation `Any` for limiter parameter
**What:** The `limiter` parameter is typed as `Any` with a comment `# RateLimiter | NoOpLimiter | None`, instead of using the actual type from the base class.
**Why it matters:** Defeats mypy's ability to catch incorrect limiter types passed to the HTTP client constructor. The base class `__init__` has the correct type annotation.
**Evidence:** `http.py:116`: `limiter: Any = None,  # RateLimiter | NoOpLimiter | None`

### [345-346, 560-561] Imprecise content-type detection
**What:** The `is_text_content` check uses substring matching: `content_type.startswith("text/") or "xml" in content_type or "form-urlencoded" in content_type`. The `"xml" in content_type` check would match `Content-Type: application/json; charset=xml-adjacent` (contrived but valid per HTTP spec).
**Why it matters:** Content-type headers can include parameters (charset, boundary). Substring matching on the full header value is fragile. For example, `application/octet-stream; description="xml data"` would incorrectly be treated as text. In practice this is unlikely for real APIs, but it violates the principle of precise boundary validation.
**Evidence:** `http.py:345`: `or "xml" in content_type` -- matches anywhere in the full content-type string.

### [282-289, 497-504] URL joining does not handle query strings on base_url
**What:** URL construction strips trailing slashes from base_url and leading slashes from path, then joins with `/`. This does not handle cases where `base_url` contains query parameters (e.g., `https://api.example.com?api-version=2024-02-01`).
**Why it matters:** Azure APIs commonly use query parameters in the base URL for API versioning. The current joining logic would produce `https://api.example.com?api-version=2024-02-01/v1/process` which is malformed. However, this may be mitigated by callers passing complete URLs rather than using base_url for Azure APIs.
**Evidence:** `http.py:286-287`: `base = self._base_url.rstrip("/")` then `full_url = f"{base}/{path}"`.

## Observations

### [175] Lazy import of security module
**What:** `_filter_request_headers` imports `get_fingerprint_key` and `secret_fingerprint` inside the method body rather than at module level.
**Why it matters:** This is intentional to avoid circular imports or heavy import chains, and is a common pattern in the codebase. However, it means the import cost is paid on every HTTP call. For high-throughput scenarios, this could add measurable overhead. Python caches imports so the actual cost after first call is minimal (dict lookup).

### [178] ELSPETH_ALLOW_RAW_SECRETS environment variable checked per call
**What:** `os.environ.get("ELSPETH_ALLOW_RAW_SECRETS")` is read on every `_filter_request_headers` call rather than once at construction.
**Why it matters:** Very minor performance issue. More importantly, the value could theoretically change mid-pipeline if something modifies the environment, leading to inconsistent audit behavior within a single run. This violates the "one run = one configuration" principle mentioned in CLAUDE.md.

### General: No support for PUT, PATCH, DELETE, HEAD, OPTIONS
**What:** Only `post()` and `get()` are implemented. No other HTTP methods are available.
**Why it matters:** Currently all callers use `post()` (LLM transforms, Azure transforms) or `get()` (web scraping). If a future sink or transform needs PUT or DELETE, a new method would need to be added. Given the duplication between post/get, this further motivates refactoring to a shared internal method.

## Verdict
**Status:** NEEDS_ATTENTION
**Recommended action:** (1) Refactor post/get into a shared internal `_execute_request()` method to eliminate duplication. (2) Create a persistent httpx.Client in `__init__` and close it in `close()`, rather than creating per-request. (3) Add a size bound on `_raw_text` in JSON parse failure cases (e.g., truncate to 64KB). (4) Read `ELSPETH_ALLOW_RAW_SECRETS` once at construction time.
**Confidence:** HIGH -- Full read of all 683 lines, all callers inspected, dependencies reviewed.
