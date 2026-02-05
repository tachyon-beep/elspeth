# Analysis: src/elspeth/plugins/transforms/web_scrape.py

**Lines:** 293
**Role:** Web scrape transform -- fetches web pages during pipeline execution, extracts content (HTML to markdown/text/raw), computes fingerprints for change detection, and enriches the pipeline row with scraped data. Security-sensitive due to SSRF risk.
**Key dependencies:** `elspeth.core.security` (validate_ip, validate_url_scheme), `elspeth.plugins.clients.http.AuditedHTTPClient`, `elspeth.plugins.transforms.web_scrape_extraction.extract_content`, `elspeth.plugins.transforms.web_scrape_fingerprint.compute_fingerprint`, `elspeth.contracts.contract_propagation.narrow_contract_to_output`, `elspeth.plugins.base.BaseTransform`, `httpx`
**Analysis depth:** FULL

## Summary

This file is structurally sound and follows the ELSPETH patterns correctly. The SSRF protection is present but has a critical TOCTOU (time-of-check-time-of-use) vulnerability: the IP is validated pre-request, but DNS can resolve differently at request time. There is also an unguarded exception gap where `httpx` errors other than `TimeoutException` and `ConnectError` will escape the transform as unhandled exceptions (crash). The Tier 3 boundary handling for HTML content extraction is absent -- `extract_content` can crash on malformed HTML without wrapping, violating the external data trust model.

## Critical Findings

### [150-166] SSRF TOCTOU: DNS re-resolution between validation and fetch

**What:** The transform validates the IP address of the URL hostname at line 157 (`validate_ip(parsed.host)`), but the actual HTTP request at line 265 (`client.get(url, headers=headers)`) uses `httpx.Client` internally, which performs its own DNS resolution. Between the validation and the fetch, DNS can resolve to a different IP address (DNS rebinding attack).

**Why it matters:** An attacker controlling a DNS server can return a public IP on the first resolution (passes validation) and a private/metadata IP on the second resolution (used by httpx). This bypasses SSRF protection entirely, allowing access to cloud metadata endpoints (169.254.169.254), internal services, or other private network resources. This is a well-known attack vector against pre-resolution SSRF defenses.

**Evidence:**
```python
# Line 155-157: First resolution (validation)
parsed = httpx.URL(url)
if parsed.host:
    validate_ip(parsed.host)  # Resolves hostname -> checks IP

# Line 265: Second resolution (actual request - different DNS answer possible)
http_response = client.get(url, headers=headers)
```

The `validate_ip` function in `core/security/web.py` calls `socket.gethostbyname(hostname)` which does DNS resolution. Then `httpx.Client.get()` does its own independent DNS resolution. These are two separate DNS lookups.

### [184-192] Unprotected Tier 3 boundary: extract_content can crash on malformed HTML

**What:** The `extract_content` function (from `web_scrape_extraction.py`) calls BeautifulSoup and html2text on the response body. Neither the call at line 185 nor the extraction module itself wraps parsing in try/except. A malformed HTML response (external data, Tier 3) that causes BeautifulSoup or html2text to raise an exception will crash the transform.

**Why it matters:** Per the Three-Tier Trust Model, HTTP response bodies are Tier 3 (external data, zero trust). Operations on external data must be wrapped. A malicious or broken web page that causes a parsing crash will crash the entire pipeline row processing, and since this is not a `WebScrapeError`, it won't be caught by the error handling in `process()` at lines 171-182. It will propagate as an unhandled exception.

**Evidence:**
```python
# Line 185-189: No try/except around external data parsing
content = extract_content(
    response.text,           # External data - could be anything
    format=self._format,
    strip_elements=self._strip_elements,
)
```

In `web_scrape_extraction.py`, `BeautifulSoup(html, "html.parser")` and `h.handle(cleaned_html)` are called without wrapping. While BeautifulSoup is generally tolerant, html2text has known edge cases with malformed HTML, and extremely large documents can cause memory issues.

### [264-289] Exception gap: httpx errors beyond TimeoutException and ConnectError are unhandled

**What:** The `_fetch_url` method catches `httpx.TimeoutException` and `httpx.ConnectError` but does not catch other `httpx` exceptions like `httpx.TooManyRedirects`, `httpx.DecodingError`, `httpx.InvalidURL`, `httpx.ProtocolError`, or `httpx.ReadError`. These will propagate as unhandled exceptions.

**Why it matters:** These are all Tier 3 boundary failures (external server misbehavior). A server that issues excessive redirects, serves invalid encoding, or violates HTTP protocol will crash the transform instead of producing a quarantinable error result. The crash will be treated as a plugin bug rather than external data failure.

**Evidence:**
```python
# Lines 286-289: Only two exception types caught
except httpx.TimeoutException as e:
    raise NetworkError(f"Timeout fetching {url}: {e}") from e
except httpx.ConnectError as e:
    raise NetworkError(f"Connection error fetching {url}: {e}") from e
# Missing: httpx.TooManyRedirects, httpx.DecodingError, httpx.ProtocolError,
#          httpx.ReadError, httpx.WriteError, httpx.CloseError
```

## Warnings

### [120] Defensive .get() on internal config dict

**What:** Line 120 uses `http_config.get("timeout", 30)` to access the timeout from `cfg.http`, which is a dict from Pydantic-validated config. The `abuse_contact` and `scraping_reason` fields at lines 118-119 are accessed directly via `[]`, but `timeout` uses `.get()` with a default.

**Why it matters:** This is inconsistent. Either all three fields should be accessed directly (if validated by config), or all should have defaults. The mixed pattern suggests `timeout` is intentionally optional in the `http` dict, but this is not enforced by the Pydantic model -- `http` is typed as `dict[str, Any]` with no schema. If `abuse_contact` or `scraping_reason` are missing, lines 118-119 will crash with KeyError. If `timeout` is truly optional, the config should use a Pydantic model for the `http` sub-config to make this explicit.

**Evidence:**
```python
http_config = cfg.http
self._abuse_contact = http_config["abuse_contact"]      # Crash if missing
self._scraping_reason = http_config["scraping_reason"]  # Crash if missing
self._timeout = http_config.get("timeout", 30)          # Silent default
```

### [55] http config is unvalidated dict[str, Any]

**What:** The `http` field in `WebScrapeConfig` is typed as `dict[str, Any]`. This means Pydantic cannot validate that required sub-fields (`abuse_contact`, `scraping_reason`) are present, or that `timeout` is a number.

**Why it matters:** Invalid configuration (missing `abuse_contact`, `timeout: "fast"`) will only fail at runtime during `__init__`, not at config validation time. This defeats the purpose of Pydantic config validation. A proper nested model would catch these errors during pipeline configuration validation (`elspeth validate`).

**Evidence:**
```python
class WebScrapeConfig(TransformDataConfig):
    http: dict[str, Any]  # No validation of sub-fields
```

### [156] SSRF validation skipped when host is None

**What:** The `if parsed.host:` guard at line 156 means that if `httpx.URL(url)` returns a parsed URL with no host (e.g., a malformed URL that httpx parses without error), the IP validation is completely skipped.

**Why it matters:** While `validate_url_scheme` at line 154 checks the scheme, a URL like `http:///etc/passwd` or scheme-relative URLs could potentially bypass the host check. The likelihood is low since httpx would fail to connect, but the security check should be explicit -- if there is no host to validate, the URL should be rejected rather than allowed to proceed.

**Evidence:**
```python
validate_url_scheme(url)
parsed = httpx.URL(url)
if parsed.host:           # Silently skips validation if host is None
    validate_ip(parsed.host)
```

### [273-282] HTTP status code handling misses 408 (Request Timeout)

**What:** The status code handling covers 404, 403, 401, 429, and 5xx, but does not handle 408 (Request Timeout), which the error hierarchy defines as retryable (`TimeoutError` in `web_scrape_errors.py`). Other potentially important codes like 402, 407, or 451 are also unhandled.

**Why it matters:** Any unhandled non-error status code (e.g., 3xx redirects, 408) will fall through and be returned as a "successful" response, potentially feeding garbage data into content extraction. HTTP 408 specifically should be retryable. HTTP 3xx should be handled or at least acknowledged (httpx may or may not follow redirects depending on configuration).

**Evidence:**
```python
if response.status_code == 404:
    raise NotFoundError(f"HTTP 404: {url}")
elif response.status_code == 403:
    raise ForbiddenError(f"HTTP 403: {url}")
# ... 401, 429, 5xx handled
# Missing: 408 (has error class), 3xx, other 4xx
```

### [249-256] New AuditedHTTPClient created per invocation

**What:** Every call to `_fetch_url` creates a new `AuditedHTTPClient` instance, which internally creates a new `httpx.Client` per request. There is no connection pooling or client reuse.

**Why it matters:** For pipelines processing many rows with web scraping, this means no TCP connection reuse, no HTTP keep-alive, and a new TLS handshake for every single request. This adds significant latency and load. The Content Safety and Prompt Shield transforms cache their HTTP clients per `state_id`; this transform does not.

## Observations

### [291-293] close() is empty

The `close()` method does nothing. Since `_fetch_url` creates and discards HTTP clients per call, there is nothing to clean up. This is correct given the current implementation, but if client caching were added (as recommended), `close()` would need to clean up cached clients.

### [196-199] Payload storage is thorough

The transform stores request, raw response, and processed content as separate payload hashes. This is excellent for forensic recovery and audit trail completeness. The request hash is a simple string representation (`f"GET {url}"`) rather than structured data, which is adequate but could be richer.

### [212-226] Contract propagation via narrow_contract_to_output

The use of `narrow_contract_to_output` correctly handles the fact that this transform adds fields to the output row. This follows the P2 bug fix pattern and ensures downstream transforms/sinks see the enriched schema.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** Three issues require remediation: (1) The SSRF TOCTOU vulnerability needs a fundamental fix -- either pin DNS resolution and pass the resolved IP to httpx, or use httpx transport-level hooks to validate the connected IP. (2) The `extract_content` call must be wrapped in try/except since it operates on Tier 3 external data. (3) The exception gap in `_fetch_url` should catch the broader `httpx.HTTPError` or `httpx.RequestError` base class to prevent unhandled crashes from external server misbehavior. The `http` config should also be refactored from `dict[str, Any]` to a proper Pydantic model.
**Confidence:** HIGH -- All findings are based on direct code analysis with full dependency context. The SSRF TOCTOU is a well-documented attack pattern. The exception gap and missing Tier 3 wrapping are straightforward to verify against the codebase conventions.
