# Web Scrape Transform Design

**Date:** 2026-02-03
**Status:** Draft - Revised per review feedback (2026-02-04)
**Author:** Brainstorming session
**Review:** [2026-02-03-web-scrape-transform-design.review.json](./2026-02-03-web-scrape-transform-design.review.json)

**Review Summary (2026-02-04):**
- ✅ Fixed 8 blocking issues: RateLimitRegistry API, test base class, plugin registration, security infrastructure, DNS timeout, signal.alarm, disk space, html2text determinism
- ✅ Addressed 7 warnings: Added storage estimates, pool size vs rate limit documentation
- ✅ Ready for implementation with correct patterns

## Overview

A transform plugin that fetches webpages from URLs in the input row, converts content to configurable formats (markdown/text/raw), and generates fingerprints for change detection. Designed for compliance monitoring use cases such as evaluating government agency transparency statements against policy requirements.

**Input:** Row with a URL field
**Output:** Row enriched with content, fingerprint, and metadata

---

## Section 1: Configuration

### Full Configuration Schema

```yaml
transforms:
  - plugin: web_scrape
    options:
      schema:
        mode: FLEXIBLE
        guaranteed_fields:
          - page_content
          - page_fingerprint
          - fetch_status
          - fetch_timestamp

      # Required: input/output field mapping
      url_field: url                       # Which field contains the URL
      content_field: page_content          # Output field for scraped content
      fingerprint_field: page_fingerprint  # Output field for fingerprint

      # Output format: markdown (default) | text | raw
      format: markdown

      # Fingerprint mode: content (normalized) | full (whitespace-sensitive) | structure (DOM only)
      fingerprint_mode: content

      # Optional: elements to remove before extraction
      strip_elements:
        - script
        - style
        - nav
        - footer
        - aside

      # HTTP settings
      http:
        timeout: 30                        # seconds (read timeout)
        connect_timeout: 10                # seconds (connection timeout)
        follow_redirects: true
        max_redirects: 5
        retries: 3
        retry_backoff: exponential         # exponential | fixed | none

        # REQUIRED: Responsible scraping headers (validation fails without these)
        abuse_contact: compliance-team@example.com
        scraping_reason: "Automated compliance monitoring for transparency statement verification"

        # Optional additional headers
        headers:
          User-Agent: "ELSPETH-Compliance/1.0"

      # Security settings (SSRF prevention)
      security:
        max_response_size_mb: 10           # Abort if response exceeds this (default: 10MB)
        allowed_schemes:                   # Whitelist (default: [https, http])
          - https
          - http
        blocked_ip_ranges:                 # CIDR ranges to block (defaults below)
          - "127.0.0.0/8"                  # Loopback
          - "10.0.0.0/8"                   # Private Class A
          - "172.16.0.0/12"                # Private Class B
          - "192.168.0.0/16"               # Private Class C
          - "169.254.0.0/16"               # Link-local (includes cloud metadata)
          - "::1/128"                      # IPv6 loopback
          - "fc00::/7"                     # IPv6 private
        validate_redirects: true           # Re-validate each redirect target (default: true)
        verify_ssl: true                   # Verify SSL certificates (default: true)

      # Concurrency settings (for high-volume scraping)
      concurrency:
        pool_size: 10                      # Max concurrent fetches (default: 10)

      # Rate limiting (integrates with ELSPETH's RateLimitRegistry)
      rate_limit:
        requests_per_minute: 60            # Per-domain limit
        burst: 10                          # Burst allowance

      # Error routing (standard ELSPETH pattern)
      on_error: quarantine  # or: discard, or sink name
```

### Mandatory Fields

| Field | Validation |
|-------|------------|
| `url_field` | Required - no magic field name detection |
| `content_field` | Required - explicit output field naming |
| `fingerprint_field` | Required - explicit output field naming |
| `http.abuse_contact` | Required - must be valid email format |
| `http.scraping_reason` | Required - minimum 10 characters |
| `security.max_response_size_mb` | Optional - defaults to 10MB |
| `security.blocked_ip_ranges` | Optional - defaults to private/loopback ranges |
| `rate_limit.requests_per_minute` | Optional - defaults to 60 |

### Responsible Scraping Headers

Every request includes:
- `X-Abuse-Contact: compliance-team@example.com`
- `X-Scraping-Reason: Automated compliance monitoring for transparency statement verification`

If someone can't fill these in, they probably shouldn't be scraping.

---

## Section 2: Output Schema and Fields

### Fields Added by WebScrapeTransform

| Field | Type | Description |
|-------|------|-------------|
| `{content_field}` | `str` | Extracted content in configured format |
| `{fingerprint_field}` | `str` | SHA-256 hash for change detection |
| `fetch_status` | `int` | HTTP status code (200, 301, etc.) |
| `fetch_timestamp` | `datetime` | UTC timestamp when fetch completed |
| `fetch_duration_ms` | `int` | Request duration in milliseconds |
| `fetch_url_final` | `str` | Final URL after redirects (may differ from input) |
| `fetch_content_type` | `str` | Response Content-Type header |
| `fetch_content_length` | `int \| None` | Response size in bytes (if available) |

### Audit Metadata Fields

| Field | Type | Description |
|-------|------|-------------|
| `{fingerprint_field}_mode` | `str` | `"content"`, `"full"`, or `"structure"` |
| `{content_field}_format` | `str` | `"markdown"`, `"text"`, or `"raw"` |
| `fetch_request_hash` | `str` | Hash of request payload (for reproducibility) |
| `fetch_response_raw_hash` | `str` | Hash of raw response payload |
| `fetch_response_processed_hash` | `str` | Hash of processed content payload |

### Payload Handling

Three payloads stored via ELSPETH's PayloadStore (content-addressable):

| Payload | Content | Hash Field |
|---------|---------|------------|
| **Request** | Full HTTP request (method, URL, headers) | `fetch_request_hash` |
| **Response Raw** | Complete HTTP response body (original HTML) | `fetch_response_raw_hash` |
| **Response Processed** | Extracted content (markdown/text) | `fetch_response_processed_hash` |

**Storage Strategy:**
```python
# Payloads stored via ctx.payload_store (content-addressable)
request_hash = ctx.payload_store.store(request_bytes)
response_raw_hash = ctx.payload_store.store(response_body)
response_processed_hash = ctx.payload_store.store(extracted_content.encode())

# Only hashes go in the row (audit trail stays lean)
output["fetch_request_hash"] = request_hash
output["fetch_response_raw_hash"] = response_raw_hash
output["fetch_response_processed_hash"] = response_processed_hash
```

**Forensic Recovery:**
```bash
elspeth payload get <fetch_request_hash>       # What we sent
elspeth payload get <fetch_response_raw_hash>  # What we got back
elspeth payload get <fetch_response_processed_hash>  # What we extracted
```

If `format: raw`, response_raw and response_processed point to same hash (deduplication).

**Storage Requirements:**

3 payloads per URL (request, response raw, response processed). Estimate based on average 5MB response size:

| URL Count | Payloads | Storage per Run | 30-day Retention | 90-day Retention |
|-----------|----------|-----------------|------------------|------------------|
| 1,000 | 3,000 | ~15 GB | ~450 GB | ~1.4 TB |
| 10,000 | 30,000 | ~150 GB | ~4.5 TB | ~14 TB |
| 100,000 | 300,000 | ~1.5 TB | ~45 TB | ~140 TB |

**Factors affecting storage:**
- Avg 5MB assumes mostly HTML pages (10MB max response size)
- Larger images/PDFs increase storage significantly
- Deduplication reduces storage when same content fetched multiple times
- Compression is applied by PayloadStore but not factored into estimates above

**Operational Planning:**
- Monitor disk space before large runs
- Configure retention policy appropriate for audit requirements (30-90 days typical)
- Use `elspeth purge --run <run_id>` to manually purge old payloads
- Reference: See CLAUDE.md Payload Store and `core/retention/` for retention policies

### Example Output Row

```python
{
    # Original fields preserved
    "url": "https://agency.gov/transparency",
    "agency_name": "Example Agency",

    # Content extraction
    "page_content": "# Transparency Statement\n\nThis agency...",
    "page_fingerprint": "a3f2b8c1d4e5...",

    # Fetch metadata
    "fetch_status": 200,
    "fetch_timestamp": "2026-02-03T14:30:00Z",
    "fetch_duration_ms": 342,
    "fetch_url_final": "https://agency.gov/transparency",
    "fetch_content_type": "text/html; charset=utf-8",
    "fetch_content_length": 15234,

    # Audit fields
    "page_fingerprint_mode": "content",
    "page_content_format": "markdown",
    "fetch_request_hash": "b7d9e2f1...",
    "fetch_response_raw_hash": "c8e0f3a2...",
    "fetch_response_processed_hash": "d9f1a4b3...",
}
```

---

## Section 3: Content Extraction Logic

### Format Conversion Pipeline

```
Raw HTML → Parse DOM → Strip Elements → Extract Content → Format Output
```

| Format | Process | Library |
|--------|---------|---------|
| `raw` | None - return response body as-is | N/A |
| `text` | Strip tags, decode entities, normalize whitespace | BeautifulSoup |
| `markdown` | Convert structure to markdown syntax | html2text |

### Library: html2text (20+ years mature)

Selected for stability and long-term maintenance over newer alternatives:

```python
import html2text

h = html2text.HTML2Text()
h.ignore_links = False          # Keep links (compliance requirement)
h.ignore_images = False         # Keep image references
h.body_width = 0                # Don't wrap lines (preserves structure)
h.ignore_tables = False         # Preserve table structure
h.ignore_emphasis = False       # Keep bold/italic markers

markdown_content = h.handle(html)
```

### Text Extraction

For `format: text`, use BeautifulSoup:

```python
from bs4 import BeautifulSoup

soup = BeautifulSoup(html, "html.parser")
# Remove configured elements
for tag in soup(strip_elements):
    tag.decompose()
text = soup.get_text(separator=" ", strip=True)
```

### Configurable Element Stripping

Applied before extraction for all formats:

```yaml
strip_elements:
  - script
  - style
  - nav
  - footer
  - aside
```

---

## Section 4: Fingerprinting

### Three Modes

| Mode | What It Hashes | Detects |
|------|----------------|---------|
| `content` | Normalized text content | Meaningful text/link changes |
| `full` | Raw extracted content | Any change including whitespace |
| `structure` | DOM element skeleton | Layout changes (sections added/removed) |

### Content Mode Normalization

```python
import hashlib
import re

def normalize_for_fingerprint(content: str) -> str:
    """Normalize content for change-resistant fingerprinting."""
    # Collapse all whitespace sequences to single space
    normalized = re.sub(r'\s+', ' ', content)
    # Strip leading/trailing
    normalized = normalized.strip()
    return normalized

def compute_fingerprint(content: str, mode: str) -> str:
    """Compute SHA-256 fingerprint."""
    if mode == "content":
        content = normalize_for_fingerprint(content)
    elif mode == "structure":
        content = extract_structure(content)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()
```

### Structure Mode (Experimental)

> ⚠️ **Limitations:** Structure mode is sensitive to DOM changes that may not reflect meaningful content changes (e.g., adding `<span>` wrappers for styling, reordering `<div>` sections). It may produce false positives for cosmetic changes and false negatives for text-only policy changes. **Recommended for:** Detecting major layout changes (sections added/removed). **Not recommended for:** Compliance monitoring where text changes matter.

Extracts the DOM "skeleton" - tag hierarchy without text content:

```python
from bs4 import BeautifulSoup

def extract_structure(html: str) -> str:
    """Extract DOM structure skeleton for fingerprinting.

    Captures: tag names, hierarchy, link hrefs, image srcs
    Ignores: text content, attributes (except href/src)
    """
    soup = BeautifulSoup(html, "html.parser")

    def skeleton(element) -> str:
        if element.name is None:  # NavigableString (text node)
            return ""

        parts = [f"<{element.name}"]

        # Preserve href/src (links and images matter for compliance)
        if element.get("href"):
            parts.append(f' href="{element.get("href")}"')
        if element.get("src"):
            parts.append(f' src="{element.get("src")}"')

        parts.append(">")

        # Recurse into children
        for child in element.children:
            parts.append(skeleton(child))

        parts.append(f"</{element.name}>")
        return "".join(parts)

    return skeleton(soup.body or soup)
```

### Fingerprint Comparison Example

| Fingerprint Mode | Text change only | Structure change |
|------------------|------------------|------------------|
| `content` | ⚠️ Changed | ⚠️ Changed |
| `full` | ⚠️ Changed | ⚠️ Changed |
| `structure` | ✅ Same | ⚠️ Changed |

### Downstream Gate Example

```yaml
gates:
  - name: change_detector
    condition: "row['page_fingerprint'] != row['previous_fingerprint']"
    routes:
      "true": changed_pages_sink    # Content changed - needs review
      "false": unchanged_sink        # No change - archive
```

---

## Section 5: Error Handling

### Error Classification (LLM Plugin Pattern)

Following the established pattern from `LLMClientError`:

| HTTP Status / Exception | Error Type | Retryable? | Behavior |
|-------------------------|------------|------------|----------|
| 429 | `RateLimitError` | ✅ Yes | Re-raise for engine RetryManager |
| 408 (Request Timeout) | `TimeoutError` | ✅ Yes | Re-raise for engine RetryManager |
| 425 (Too Early) | `ServerError` | ✅ Yes | Re-raise for engine RetryManager |
| 500, 502, 503, 504 | `ServerError` | ✅ Yes | Re-raise for engine RetryManager |
| `httpx.TimeoutException` | `NetworkError` | ✅ Yes | Re-raise for engine RetryManager |
| `httpx.ConnectError` | `NetworkError` | ✅ Yes | Re-raise for engine RetryManager |
| `httpx.ReadTimeout` | `NetworkError` | ✅ Yes | Re-raise for engine RetryManager |
| Connection refused | `NetworkError` | ✅ Yes | Re-raise for engine RetryManager |
| DNS resolution failure | `NetworkError` | ✅ Yes | Re-raise for engine RetryManager |
| 404 | `NotFoundError` | ❌ No | `TransformResult.error()` |
| 403 | `ForbiddenError` | ❌ No | `TransformResult.error()` |
| 401 | `UnauthorizedError` | ❌ No | `TransformResult.error()` |
| SSL/TLS failure | `SSLError` | ❌ No | `TransformResult.error()` |
| Invalid URL | `InvalidURLError` | ❌ No | `TransformResult.error()` |
| SSRF blocked (private IP) | `SSRFBlockedError` | ❌ No | `TransformResult.error()` |
| Response too large | `ResponseTooLargeError` | ❌ No | `TransformResult.error()` |
| Malformed response | `ParseError` | ❌ No | `TransformResult.error()` |
| HTML conversion timeout | `ConversionTimeoutError` | ❌ No | `TransformResult.error()` |

### Error Hierarchy

```python
class WebScrapeError(Exception):
    """Base error for web scrape transform."""
    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable

class RateLimitError(WebScrapeError):
    def __init__(self, message: str) -> None:
        super().__init__(message, retryable=True)

class NetworkError(WebScrapeError):
    def __init__(self, message: str) -> None:
        super().__init__(message, retryable=True)

class ServerError(WebScrapeError):
    def __init__(self, message: str) -> None:
        super().__init__(message, retryable=True)

class NotFoundError(WebScrapeError):
    def __init__(self, message: str) -> None:
        super().__init__(message, retryable=False)

class ForbiddenError(WebScrapeError):
    def __init__(self, message: str) -> None:
        super().__init__(message, retryable=False)

class UnauthorizedError(WebScrapeError):
    def __init__(self, message: str) -> None:
        super().__init__(message, retryable=False)

class SSLError(WebScrapeError):
    def __init__(self, message: str) -> None:
        super().__init__(message, retryable=False)

class InvalidURLError(WebScrapeError):
    def __init__(self, message: str) -> None:
        super().__init__(message, retryable=False)

class ParseError(WebScrapeError):
    def __init__(self, message: str) -> None:
        super().__init__(message, retryable=False)

class SSRFBlockedError(WebScrapeError):
    """URL resolves to blocked IP range (private, loopback, cloud metadata)."""
    def __init__(self, message: str) -> None:
        super().__init__(message, retryable=False)

class ResponseTooLargeError(WebScrapeError):
    """Response exceeds max_response_size_mb limit."""
    def __init__(self, message: str) -> None:
        super().__init__(message, retryable=False)

class ConversionTimeoutError(WebScrapeError):
    """HTML-to-text/markdown conversion exceeded timeout."""
    def __init__(self, message: str) -> None:
        super().__init__(message, retryable=False)

class TimeoutError(WebScrapeError):
    """HTTP 408 Request Timeout."""
    def __init__(self, message: str) -> None:
        super().__init__(message, retryable=True)
```

### Process Method Pattern

```python
def process(self, row: dict[str, Any], ctx: PluginContext) -> TransformResult:
    url = row[self._url_field]

    try:
        response = self._fetch(url)
    except WebScrapeError as e:
        if e.retryable:
            raise  # Engine RetryManager handles
        return TransformResult.error({
            "reason": type(e).__name__,
            "url": url,
            "error": str(e),
        })

    # ... extraction and fingerprinting
```

### Error Row Output

When `on_error` routes to a sink, the error row contains:

```python
{
    # Original row preserved
    "url": "https://agency.gov/missing-page",

    # Error details
    "_error_reason": "NotFoundError",
    "_error_message": "HTTP 404: Page not found",
    "_error_url": "https://agency.gov/missing-page",
    "_error_timestamp": "2026-02-03T14:30:00Z",
}
```

---

## Section 5.5: Security Controls

Web scraping introduces significant security risks. This section documents mandatory security controls.

### SSRF (Server-Side Request Forgery) Prevention

**Threat:** Attacker provides malicious URL to access internal systems, cloud metadata, or local files.

**Controls:**

1. **Scheme Whitelist** - Only `http` and `https` allowed:
   ```python
   ALLOWED_SCHEMES = {"http", "https"}

   def validate_scheme(url: str) -> None:
       parsed = urllib.parse.urlparse(url)
       if parsed.scheme.lower() not in ALLOWED_SCHEMES:
           raise SSRFBlockedError(f"Forbidden scheme: {parsed.scheme}")
   ```

2. **IP Range Blocklist** - Block private, loopback, and cloud metadata IPs:
   ```python
   import ipaddress
   import socket

   BLOCKED_RANGES = [
       ipaddress.ip_network("127.0.0.0/8"),      # Loopback
       ipaddress.ip_network("10.0.0.0/8"),       # Private Class A
       ipaddress.ip_network("172.16.0.0/12"),    # Private Class B
       ipaddress.ip_network("192.168.0.0/16"),   # Private Class C
       ipaddress.ip_network("169.254.0.0/16"),   # Link-local (AWS/Azure/GCP metadata)
       ipaddress.ip_network("::1/128"),          # IPv6 loopback
       ipaddress.ip_network("fc00::/7"),         # IPv6 private
   ]

   def validate_ip(hostname: str, timeout: float = 5.0) -> str:
       """Resolve hostname with timeout and validate IP is not blocked.

       Returns resolved IP address.

       **DNS Timeout:** Wraps socket.gethostbyname() in ThreadPoolExecutor with timeout.
       httpx timeout only covers network phase AFTER DNS resolution, so we need explicit
       DNS timeout to prevent indefinite hangs on slow/unavailable DNS servers.
       """
       from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

       def _resolve():
           try:
               return socket.gethostbyname(hostname)
           except socket.gaierror as e:
               raise NetworkError(f"DNS resolution failed: {hostname}: {e}")

       with ThreadPoolExecutor(max_workers=1, thread_name_prefix="dns_resolve") as executor:
           future = executor.submit(_resolve)
           try:
               ip_str = future.result(timeout=timeout)
           except FuturesTimeoutError:
               raise NetworkError(f"DNS resolution timeout ({timeout}s): {hostname}")

       ip = ipaddress.ip_address(ip_str)
       for blocked in BLOCKED_RANGES:
           if ip in blocked:
               raise SSRFBlockedError(f"Blocked IP range: {ip_str} in {blocked}")

       return ip_str
   ```

3. **DNS Pinning** - Prevent DNS rebinding attacks:
   ```python
   # Resolve DNS once, use resolved IP for the request
   resolved_ip = validate_ip(parsed.hostname)

   # Use httpx transport with pre-resolved IP
   # This prevents TOCTOU where DNS changes between validation and request
   transport = httpx.HTTPTransport(local_address=None)
   # ... or use resolved IP directly in URL (with Host header preserved)
   ```

### Redirect Validation

**Threat:** Initial URL passes validation, then redirects to forbidden target.

**Control:** Validate each redirect destination before following:

```python
def validate_redirect(response: httpx.Response) -> None:
    """Event hook called on each redirect."""
    if response.is_redirect:
        location = response.headers.get("location")
        if location:
            # Parse and validate redirect target
            parsed = urllib.parse.urlparse(location)
            validate_scheme(location)
            if parsed.hostname:
                validate_ip(parsed.hostname)

# Configure httpx to call hook on redirects
client = httpx.Client(
    event_hooks={"response": [validate_redirect]},
    follow_redirects=True,
    max_redirects=5,
)
```

### Response Size Limits

**Threat:** Attacker provides URL to massive file, causing memory exhaustion.

**Control:** Stream response and abort if size exceeded:

```python
async def fetch_with_size_limit(
    client: httpx.Client,
    url: str,
    max_size_bytes: int,
) -> bytes:
    """Fetch URL with response size limit."""
    # Check Content-Length header first (if available)
    head_response = client.head(url)
    content_length = head_response.headers.get("content-length")
    if content_length and int(content_length) > max_size_bytes:
        raise ResponseTooLargeError(
            f"Content-Length {content_length} exceeds limit {max_size_bytes}"
        )

    # Stream response and count bytes
    chunks = []
    total_size = 0
    with client.stream("GET", url) as response:
        for chunk in response.iter_bytes():
            total_size += len(chunk)
            if total_size > max_size_bytes:
                raise ResponseTooLargeError(
                    f"Response size {total_size} exceeds limit {max_size_bytes}"
                )
            chunks.append(chunk)

    return b"".join(chunks)
```

### HTML Conversion Timeout

**Threat:** Malicious HTML causes html2text/BeautifulSoup to hang or consume excessive CPU.

**Control:** Wrap conversion in timeout using ThreadPoolExecutor (cross-platform, thread-safe):

```python
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

def convert_html_with_timeout(html_content: str, format: str, timeout_seconds: int) -> str:
    """Convert HTML with timeout protection (cross-platform, thread-safe).

    Uses ThreadPoolExecutor to run conversion in background thread with timeout.

    **Thread-safe:** Compatible with BatchTransformMixin's worker pool. Each conversion
    runs in its own timeout-controlled thread, isolated from the worker pool threads.

    **Cross-platform:** Works on Unix, Windows, and macOS (unlike signal.alarm which
    is Unix-only and process-global).
    """
    def _convert():
        if format == "markdown":
            h = html2text.HTML2Text()
            h.ignore_links = False
            h.body_width = 0
            return h.handle(html_content)
        elif format == "text":
            soup = BeautifulSoup(html_content, "html.parser")
            return soup.get_text(separator=" ", strip=True)
        else:  # raw
            return html_content

    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="html_convert") as executor:
        future = executor.submit(_convert)
        try:
            return future.result(timeout=timeout_seconds)
        except FuturesTimeoutError:
            raise ConversionTimeoutError(
                f"HTML conversion exceeded {timeout_seconds}s timeout"
            )

# Usage
CONVERSION_TIMEOUT_SECONDS = 30

markdown = convert_html_with_timeout(html_content, "markdown", CONVERSION_TIMEOUT_SECONDS)
```

### Certificate Validation

**Control:** Always verify SSL certificates (httpx default):

```python
# httpx verifies certificates by default
# Explicitly document this is REQUIRED
client = httpx.Client(
    verify=True,  # Default, but explicit for clarity
    # NEVER set verify=False in production
)
```

### Security Configuration Summary

| Control | Config Key | Default | Description |
|---------|------------|---------|-------------|
| Scheme whitelist | `security.allowed_schemes` | `["https", "http"]` | Reject `file://`, `ftp://`, etc. |
| IP blocklist | `security.blocked_ip_ranges` | Private + loopback | Prevent SSRF to internal systems |
| Response size limit | `security.max_response_size_mb` | `10` | Abort if response exceeds limit |
| Redirect validation | `security.validate_redirects` | `true` | Re-validate each redirect target |
| SSL verification | `security.verify_ssl` | `true` | Verify certificates (never disable) |
| Conversion timeout | `security.conversion_timeout_s` | `30` | Abort HTML conversion if slow |

---

## Section 6: Dependencies and Implementation

### New Dependencies

| Package | Version | Purpose | Size |
|---------|---------|---------|------|
| `html2text` | `>=2024.2.26` | HTML→Markdown conversion | ~50KB |
| `beautifulsoup4` | `>=4.12,<5` | HTML parsing for text extraction and structure fingerprinting | ~500KB |
| `httpx` | `>=0.27` | Modern async-capable HTTP client | Already in core deps |
| `respx` | `>=0.21,<1` | httpx mocking for tests | Dev dependency |

**Why httpx over requests:**
- Built-in timeout handling (requests is notorious for hanging)
- HTTP/2 support (some gov sites use it)
- Better redirect handling
- Same API style, easier testing with respx
- Future-proofs for async parallelization

**Note:** `httpx` is already in ELSPETH's core dependencies. `beautifulsoup4` and `html2text` are new additions for the `[web]` optional dependency group.

### File Structure

```
src/elspeth/plugins/
├── transforms/
│   └── web_scrape.py           # Main transform (new)
├── clients/
│   └── http.py                 # AuditedHTTPClient (EXISTS - needs GET method)
```

### AuditedHTTPClient

> **Note:** `AuditedHTTPClient` already exists at `src/elspeth/plugins/clients/http.py` (413 lines). It currently only has a `post()` method. **Implementation task:** Add a `get()` method following the same audit pattern.

The existing client already provides:
- Request/response recording to Landscape via `calls` table
- Auth header fingerprinting (HMAC)
- Latency measurement
- Error recording
- Telemetry emission
- Rate limiting support via `limiter` parameter

**Required addition - `get()` method:**

```python
def get(
    self,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, str] | None = None,
) -> HTTPResponse:
    """Fetch URL with full audit recording.

    Follows same pattern as existing post() method:
    1. Record call start time
    2. Make request
    3. Record call to Landscape with request/response data
    4. Emit telemetry
    5. Return response or raise typed error
    """
    # Implementation mirrors post() but uses GET method
    ...
```

**Security integration** - The `get()` method must integrate with security controls:

```python
def get(self, url: str, ...) -> HTTPResponse:
    # 1. Validate URL scheme
    validate_scheme(url)

    # 2. Resolve DNS and validate IP (SSRF prevention)
    parsed = urllib.parse.urlparse(url)
    resolved_ip = validate_ip(parsed.hostname)

    # 3. Make request with redirect validation hook
    # 4. Stream response with size limit
    # 5. Record to Landscape
    # 6. Return response
```

### Registration

**No manual registration required.** Plugins are **auto-discovered** by pluggy's folder scanning mechanism in `src/elspeth/plugins/discovery.py`.

Simply create the file and the PluginManager will discover it automatically:

```python
# src/elspeth/plugins/transforms/web_scrape.py
from elspeth.plugins.base import BaseTransform

class WebScrapeTransform(BaseTransform):
    """Web scraping transform with concurrent fetch support."""

    # Plugin name used in configuration - REQUIRED for auto-discovery
    name = "web_scrape"

    def __init__(self, options: dict[str, Any]) -> None:
        super().__init__(options)
        # ... initialization
```

**Plugin discovery flow:**
1. `PluginManager` scans `src/elspeth/plugins/transforms/` directory on startup
2. Finds all Python files with `BaseTransform` subclasses that have a `name` attribute
3. Registers classes by their `name` attribute
4. User references `plugin: web_scrape` in YAML → manager instantiates `WebScrapeTransform`

**No `__init__.py` modifications needed.** The discovery mechanism handles everything.

### Optional Dependency Group

```toml
# pyproject.toml
[project.optional-dependencies]
web = [
    "html2text>=2024.2.26",
    "beautifulsoup4>=4.12,<5",
]
# Note: httpx is already in core dependencies

dev = [
    # ... existing dev deps ...
    "respx>=0.21,<1",  # httpx mocking for web scrape tests
]

all = [
    "elspeth[llm,azure,web]",  # Add web to 'all' group
]
```

Install with: `uv pip install -e ".[web]"`

---

## Section 6.5: Concurrency Model

Web scraping is I/O-bound. Without concurrency, 10,000 URLs at 3 seconds average = **8.3 hours**. This section documents the required concurrency architecture.

### BatchTransformMixin Integration

Following the pattern from LLM transforms (`azure_batch_llm.py`), `WebScrapeTransform` must inherit from `BatchTransformMixin` for concurrent processing:

```python
from elspeth.plugins.batching import BatchTransformMixin
from elspeth.plugins.pooling import PooledExecutor

class WebScrapeTransform(BatchTransformMixin, BaseTransform):
    """Web scraping transform with concurrent fetch support."""

    def __init__(self, options: dict[str, Any]) -> None:
        super().__init__(options)
        self._pool_size = options.get("concurrency", {}).get("pool_size", 10)

    def get_pool_executor(self) -> PooledExecutor:
        """Return thread pool for concurrent fetches."""
        return PooledExecutor(
            max_workers=self._pool_size,
            thread_name_prefix="web_scrape",
        )

    def process_batch(
        self,
        rows: list[dict[str, Any]],
        ctx: PluginContext,
    ) -> list[TransformResult]:
        """Process multiple URLs concurrently."""
        with self.get_pool_executor() as executor:
            futures = [
                executor.submit(self._fetch_and_extract, row, ctx)
                for row in rows
            ]
            return [f.result() for f in futures]
```

### Throughput Expectations

> **⚠️ Critical Note:** When rate limiting is enabled, **throughput is capped by the rate limit regardless of pool_size**. Thread pool concurrency only helps when rate limiting is disabled or when scraping multiple distinct domains with per-domain limits (not currently implemented).

| Configuration | Actual Throughput | Explanation |
|---------------|-------------------|-------------|
| Sequential (no batching, no rate limit) | ~1,200 URLs/hour | Network + processing time bottleneck |
| `pool_size: 10` **without** rate limiting | ~12,000 URLs/hour | True parallelism on I/O-bound work |
| `rate_limit: 60/min` (regardless of pool_size) | **3,600 URLs/hour** | Rate limiter serializes all requests |
| `rate_limit: 60/min` + `pool_size: 10` | **3,600 URLs/hour** | Pool size has no effect when rate-limited |

**For 10,000 URLs:**
- Without rate limiting: ~50 minutes (with pool_size=10)
- With rate_limit=60/min: **2.8 hours** (regardless of pool_size)

> ⚠️ **Pool Size vs Rate Limit Mismatch:** Setting `pool_size: 20` with `rate_limit: 60/min` (1 req/sec) means 19 threads will be blocked waiting for rate limit tokens while only 1 thread does useful work. Configure pool_size proportional to your rate limit: `pool_size ≤ requests_per_minute / 60` for full utilization.

> ⚠️ **Recommendation:** Set `pool_size: 1` when rate limiting is enabled to avoid thread pool overhead with no benefit.

### Rate Limiting Integration

Rate limiting is **mandatory** for responsible scraping. The transform integrates with ELSPETH's `RateLimitRegistry`:

```python
class WebScrapeTransform(BatchTransformMixin, BaseTransform):
    def __init__(self, options: dict[str, Any]) -> None:
        super().__init__(options)
        # Rate limiter config comes from pipeline settings via RuntimeRateLimitConfig
        # Transform just retrieves the limiter by service name

    def _fetch_and_extract(
        self,
        row: dict[str, Any],
        ctx: PluginContext,
    ) -> TransformResult:
        url = row[self._url_field]

        # Get limiter from registry (configured via pipeline settings)
        limiter = ctx.rate_limit_registry.get_limiter("web_scrape")

        # Create audited client - client handles rate limiting internally
        client = AuditedHTTPClient(
            landscape=ctx.landscape,  # Correct: ctx.landscape, not ctx.recorder
            state_id=ctx.state_id,
            run_id=ctx.run_id,
            limiter=limiter,  # Client calls limiter.acquire() before each request
            # ... other params
        )

        return self._do_fetch(client, url, row, ctx)
```

### Telemetry Integration

The transform emits telemetry events for operational visibility:

```python
# On fetch start
ctx.telemetry_emit({
    "event": "web_scrape.fetch_start",
    "url_domain": parsed.hostname,
    "pool_position": pool_position,
})

# On fetch complete
ctx.telemetry_emit({
    "event": "web_scrape.fetch_complete",
    "url_domain": parsed.hostname,
    "status_code": response.status_code,
    "duration_ms": duration_ms,
    "response_size_bytes": len(response.content),
})

# On fetch error
ctx.telemetry_emit({
    "event": "web_scrape.fetch_error",
    "url_domain": parsed.hostname,
    "error_type": type(e).__name__,
    "retryable": e.retryable if isinstance(e, WebScrapeError) else False,
})
```

---

## Section 7: Testing Strategy

### Test Structure

```
tests/
├── plugins/transforms/
│   ├── test_web_scrape.py              # Unit tests
│   └── test_web_scrape_integration.py  # Integration tests
├── contracts/transform_contracts/
│   └── test_web_scrape_contract.py     # Protocol compliance
└── plugins/clients/
    └── test_http_client.py             # AuditedHTTPClient tests
```

### Unit Tests (Mocked HTTP)

Using `respx` (httpx's official mock library):

```python
import respx
import pytest
from httpx import Response

from elspeth.plugins.transforms.web_scrape import WebScrapeTransform

@respx.mock
def test_successful_scrape_markdown():
    """Verify HTML is converted to markdown and fingerprinted."""
    respx.get("https://example.gov/page").mock(
        return_value=Response(200, html="<h1>Title</h1><p>Content</p>")
    )

    transform = WebScrapeTransform({
        "schema": {"fields": "dynamic"},
        "url_field": "url",
        "content_field": "content",
        "fingerprint_field": "fingerprint",
        "format": "markdown",
        "http": {
            "abuse_contact": "test@example.com",
            "scraping_reason": "Unit testing",
        },
    })

    result = transform.process({"url": "https://example.gov/page"}, ctx)

    assert result.is_success
    assert "# Title" in result.row["content"]
    assert result.row["fingerprint"] is not None
    assert result.row["fetch_status"] == 200

@respx.mock
def test_404_returns_error_not_retry():
    """Verify 404 is non-retryable error."""
    respx.get("https://example.gov/missing").mock(
        return_value=Response(404)
    )

    transform = make_transform()
    result = transform.process({"url": "https://example.gov/missing"}, ctx)

    assert result.is_error
    assert result.error["reason"] == "NotFoundError"

@respx.mock
def test_429_raises_for_retry():
    """Verify 429 is re-raised for engine retry."""
    respx.get("https://example.gov/rate-limited").mock(
        return_value=Response(429)
    )

    transform = make_transform()

    with pytest.raises(RateLimitError):
        transform.process({"url": "https://example.gov/rate-limited"}, ctx)
```

### Contract Tests

**Batch Transform Contract:** Since WebScrapeTransform uses `BatchTransformMixin`, it must use the batch transform contract test base:

```python
from tests.contracts.transform_contracts.test_batch_transform_protocol import (
    BatchTransformContractTestBase,
)

class TestWebScrapeContract(BatchTransformContractTestBase):
    @pytest.fixture
    def transform(self):
        return WebScrapeTransform({
            "schema": {"fields": "dynamic"},
            "url_field": "url",
            "content_field": "content",
            "fingerprint_field": "fingerprint",
            "http": {
                "abuse_contact": "test@example.com",
                "scraping_reason": "Contract testing",
            },
        })

    @pytest.fixture
    def valid_input(self):
        return {"url": "https://example.com"}
```

**Why BatchTransformContractTestBase:** This base class verifies batch processing behavior including:
- Concurrent row processing via thread pool
- FIFO ordering maintenance via `RowReorderBuffer`
- Backpressure handling when buffer is full
- Thread-safe state management

### Fingerprint Stability Tests

Critical for change detection - fingerprints must be deterministic:

```python
def test_fingerprint_deterministic():
    """Same content must produce same fingerprint."""
    html = "<h1>Test</h1><p>Content here</p>"

    fp1 = compute_fingerprint(html, mode="content")
    fp2 = compute_fingerprint(html, mode="content")

    assert fp1 == fp2

def test_fingerprint_content_mode_whitespace_insensitive():
    """Content mode ignores whitespace changes."""
    html1 = "<p>Hello world</p>"
    html2 = "<p>Hello   world</p>"
    html3 = "<p>Hello\n\nworld</p>"

    fp1 = compute_fingerprint(html1, mode="content")
    fp2 = compute_fingerprint(html2, mode="content")
    fp3 = compute_fingerprint(html3, mode="content")

    assert fp1 == fp2 == fp3

def test_fingerprint_full_mode_whitespace_sensitive():
    """Full mode detects whitespace changes."""
    html1 = "<p>Hello world</p>"
    html2 = "<p>Hello   world</p>"

    fp1 = compute_fingerprint(html1, mode="full")
    fp2 = compute_fingerprint(html2, mode="full")

    assert fp1 != fp2

def test_fingerprint_structure_mode_ignores_text():
    """Structure mode ignores text content changes."""
    html1 = "<main><h1>Title A</h1><p>Content A</p></main>"
    html2 = "<main><h1>Title B</h1><p>Content B</p></main>"

    fp1 = compute_fingerprint(html1, mode="structure")
    fp2 = compute_fingerprint(html2, mode="structure")

    assert fp1 == fp2

def test_fingerprint_structure_mode_detects_dom_changes():
    """Structure mode detects DOM changes."""
    html1 = "<main><h1>Title</h1></main>"
    html2 = "<main><h1>Title</h1><section><p>New</p></section></main>"

    fp1 = compute_fingerprint(html1, mode="structure")
    fp2 = compute_fingerprint(html2, mode="structure")

    assert fp1 != fp2
```

### html2text Determinism Tests (Audit Integrity)

**CRITICAL:** html2text must produce identical output for identical input to preserve audit integrity. If non-deterministic, retries will produce different `fetch_response_processed_hash` values for the same HTML, breaking the "same input = same hash" audit invariant.

```python
from hypothesis import given
from hypothesis.strategies import text
import html2text

def test_html2text_deterministic_simple():
    """html2text must produce identical output for identical input."""
    html = "<html><body><h1>Title</h1><p>Content</p></body></html>"

    h = html2text.HTML2Text()
    h.ignore_links = False
    h.body_width = 0

    result1 = h.handle(html)
    result2 = h.handle(html)

    assert result1 == result2, "html2text output is non-deterministic!"

@given(text(min_size=10, max_size=200))
def test_html2text_deterministic_property(content: str):
    """Property test: html2text must be deterministic for all inputs."""
    # Wrap content in minimal HTML structure
    html = f"<html><body><p>{content}</p></body></html>"

    h = html2text.HTML2Text()
    h.ignore_links = False
    h.body_width = 0

    result1 = h.handle(html)
    result2 = h.handle(html)

    assert result1 == result2, f"Non-deterministic for input: {html!r}"

def test_html2text_deterministic_across_instances():
    """Verify determinism even with separate HTML2Text instances."""
    html = "<html><body><h1>Test</h1><p>Content</p></body></html>"

    h1 = html2text.HTML2Text()
    h1.ignore_links = False
    h1.body_width = 0

    h2 = html2text.HTML2Text()
    h2.ignore_links = False
    h2.body_width = 0

    result1 = h1.handle(html)
    result2 = h2.handle(html)

    assert result1 == result2, "html2text not deterministic across instances!"
```

**If these tests fail:** html2text is non-deterministic. Evaluate alternatives or pin version strictly and document the determinism guarantee in dependency constraints.

### Integration Test (Real HTTP, Localhost)

```python
@pytest.mark.integration
def test_real_http_against_local_server(local_http_server):
    """Test against actual HTTP server (localhost)."""
    transform = make_transform()
    result = transform.process(
        {"url": f"http://localhost:{local_http_server.port}/test-page"},
        ctx,
    )
    assert result.is_success
```

### Security Tests (SSRF Prevention)

```python
@respx.mock
def test_ssrf_blocks_private_ip():
    """Verify private IPs are blocked."""
    # Mock DNS to return private IP
    with patch("socket.gethostbyname", return_value="192.168.1.1"):
        transform = make_transform()
        result = transform.process({"url": "https://evil.com/page"}, ctx)

        assert result.is_error
        assert result.error["reason"] == "SSRFBlockedError"

def test_ssrf_blocks_file_scheme():
    """Verify file:// URLs are rejected."""
    transform = make_transform()
    result = transform.process({"url": "file:///etc/passwd"}, ctx)

    assert result.is_error
    assert result.error["reason"] == "SSRFBlockedError"

def test_ssrf_blocks_cloud_metadata():
    """Verify cloud metadata endpoints are blocked."""
    with patch("socket.gethostbyname", return_value="169.254.169.254"):
        transform = make_transform()
        result = transform.process(
            {"url": "http://metadata.google.internal/computeMetadata/v1/"},
            ctx,
        )

        assert result.is_error
        assert result.error["reason"] == "SSRFBlockedError"

@respx.mock
def test_ssrf_blocks_redirect_to_private_ip():
    """Verify redirects to private IPs are blocked."""
    # First request returns redirect
    respx.get("https://example.com/page").mock(
        return_value=Response(302, headers={"Location": "http://192.168.1.1/admin"})
    )

    transform = make_transform()
    result = transform.process({"url": "https://example.com/page"}, ctx)

    assert result.is_error
    assert result.error["reason"] == "SSRFBlockedError"
```

### Response Size Limit Tests

```python
@respx.mock
def test_response_too_large_aborted():
    """Verify large responses are aborted."""
    # Create response larger than limit
    large_content = "x" * (11 * 1024 * 1024)  # 11MB
    respx.get("https://example.com/huge").mock(
        return_value=Response(200, content=large_content)
    )

    transform = make_transform(security={"max_response_size_mb": 10})
    result = transform.process({"url": "https://example.com/huge"}, ctx)

    assert result.is_error
    assert result.error["reason"] == "ResponseTooLargeError"
```

### Timeout and Network Tests

```python
@respx.mock
def test_connect_timeout_is_retryable():
    """Verify connection timeout raises retryable error."""
    respx.get("https://slow.example.com/").mock(
        side_effect=httpx.ConnectTimeout("Connection timed out")
    )

    transform = make_transform()

    with pytest.raises(NetworkError) as exc:
        transform.process({"url": "https://slow.example.com/"}, ctx)

    assert exc.value.retryable is True

@respx.mock
def test_read_timeout_is_retryable():
    """Verify read timeout raises retryable error."""
    respx.get("https://slow.example.com/").mock(
        side_effect=httpx.ReadTimeout("Read timed out")
    )

    transform = make_transform()

    with pytest.raises(NetworkError) as exc:
        transform.process({"url": "https://slow.example.com/"}, ctx)

    assert exc.value.retryable is True
```

### Encoding and Edge Case Tests

```python
def test_malformed_html_handled():
    """Verify malformed HTML doesn't crash."""
    html = "<html><body><p>Unclosed tag<div>Nested wrong</html>"

    # Should not raise
    result = extract_content(html, format="text")
    assert isinstance(result, str)

def test_empty_response_handled():
    """Verify empty 200 OK is handled gracefully."""
    respx.get("https://example.com/empty").mock(
        return_value=Response(200, content=b"")
    )

    transform = make_transform()
    result = transform.process({"url": "https://example.com/empty"}, ctx)

    assert result.is_success
    assert result.row["page_content"] == ""

def test_charset_detection():
    """Verify charset is detected from Content-Type header."""
    respx.get("https://example.com/latin").mock(
        return_value=Response(
            200,
            content="Héllo wörld".encode("iso-8859-1"),
            headers={"Content-Type": "text/html; charset=iso-8859-1"},
        )
    )

    transform = make_transform()
    result = transform.process({"url": "https://example.com/latin"}, ctx)

    assert result.is_success
    assert "Héllo" in result.row["page_content"]
```

### Redirect Chain Tests

```python
@respx.mock
def test_redirect_chain_captured():
    """Verify final URL is captured after redirects."""
    respx.get("https://old.example.com/page").mock(
        return_value=Response(301, headers={"Location": "https://new.example.com/page"})
    )
    respx.get("https://new.example.com/page").mock(
        return_value=Response(200, html="<p>Content</p>")
    )

    transform = make_transform()
    result = transform.process({"url": "https://old.example.com/page"}, ctx)

    assert result.is_success
    assert result.row["fetch_url_final"] == "https://new.example.com/page"

@respx.mock
def test_max_redirects_exceeded():
    """Verify redirect limit is enforced."""
    # Create redirect loop
    for i in range(10):
        respx.get(f"https://example.com/r{i}").mock(
            return_value=Response(302, headers={"Location": f"https://example.com/r{i+1}"})
        )

    transform = make_transform(http={"max_redirects": 5})
    result = transform.process({"url": "https://example.com/r0"}, ctx)

    assert result.is_error
    # httpx raises TooManyRedirects
```

---

## Section 8: Summary and Next Steps

### Design Summary

| Aspect | Decision |
|--------|----------|
| **Plugin type** | Transform (enriches rows with URL field) |
| **Output formats** | Configurable: `markdown` (default), `text`, `raw` |
| **Fingerprint modes** | Configurable: `content` (normalized), `full`, `structure` |
| **HTTP client** | httpx (modern, async-ready, good timeout handling) |
| **HTML→Markdown** | html2text (20+ years mature, stable) |
| **Error handling** | LLM-style retryable vs non-retryable classification |
| **Payload storage** | Request, raw response, processed content via PayloadStore |
| **Responsible scraping** | Mandatory `abuse_contact` and `scraping_reason` headers |

### Example Pipeline

Complete compliance monitoring pipeline:

```yaml
source:
  plugin: csv
  options:
    path: agency_urls.csv
    schema:
      mode: OBSERVED

transforms:
  - plugin: web_scrape
    options:
      schema:
        mode: FLEXIBLE
        guaranteed_fields: [page_content, page_fingerprint]
      url_field: url
      content_field: page_content
      fingerprint_field: page_fingerprint
      format: markdown
      fingerprint_mode: content
      http:
        abuse_contact: compliance@example.gov
        scraping_reason: "Transparency statement compliance monitoring"
      on_error: scrape_errors

  - plugin: azure_llm
    options:
      model: gpt-4
      template: |
        Evaluate this transparency statement against policy requirements:

        {{ row.page_content }}

        Rate compliance on a scale of 1-5 and list any missing elements.
      response_field: compliance_assessment
      required_input_fields: [page_content]

gates:
  - name: compliance_check
    condition: "'non-compliant' in row['compliance_assessment'].lower()"
    routes:
      "true": needs_review
      "false": compliant

sinks:
  compliant:
    plugin: csv
    options:
      path: output/compliant.csv

  needs_review:
    plugin: csv
    options:
      path: output/needs_review.csv

  scrape_errors:
    plugin: csv
    options:
      path: output/scrape_errors.csv

default_sink: compliant
```

### Implementation Tasks

1. **Create shared security infrastructure** in `src/elspeth/core/security/web.py` ⚠️ **PRE-RELEASE CRITICAL**
   - Extract reusable validators: `validate_url_scheme()`, `validate_ip()`, `validate_redirect()`
   - `SSRFValidator` class with configurable blocklist
   - Export from `elspeth.core.security`
   - **Rationale:** Shared infrastructure prevents code duplication when other plugins need web requests
   - **This is a one-way door:** Once shipped without shared infrastructure, changing it is a breaking change

2. **Add `get()` method to `AuditedHTTPClient`** in `src/elspeth/plugins/clients/http.py`
   - Client already exists (413 lines) with `post()` method
   - Add `get()` following same audit pattern
   - Accept optional `validator: SSRFValidator` parameter
   - Call validator before DNS resolution
   - Add response size streaming with limit check

3. **Create `WebScrapeTransform`** in `src/elspeth/plugins/transforms/web_scrape.py`
   - Inherit from `BatchTransformMixin` for concurrent processing
   - Config validation (mandatory fields, security settings)
   - Content extraction (markdown/text/raw) with conversion timeout (ThreadPoolExecutor, not signal.alarm)
   - Fingerprinting (content/full modes - defer structure mode)
   - Integration with `AuditedHTTPClient.get()` and `ctx.rate_limit_registry.get_limiter()`
   - Telemetry emission for operational visibility
   - **Disk space check:** Add validation in `__init__()` or document as operational requirement

4. **Create error hierarchy** in `src/elspeth/plugins/transforms/web_scrape.py`
   - `WebScrapeError` base with `retryable` flag
   - Typed subclasses for each error category (see Section 5)
   - Include new security errors: `SSRFBlockedError`, `ResponseTooLargeError`, `ConversionTimeoutError`

5. **Add dependencies** to `pyproject.toml`
   - `html2text>=2024.2.26` to `[web]` group
   - `beautifulsoup4>=4.12,<5` to `[web]` group
   - `respx>=0.21,<1` to `[dev]` group
   - Add `[web]` to `[all]` group

6. **Write tests**
   - Unit tests with respx mocking
   - Contract tests (inherit from `BatchTransformContractTestBase` - not `TransformContractPropertyTestBase`)
   - Fingerprint stability tests
   - **html2text determinism test:** Property test verifying `handle(html) == handle(html)` (audit integrity)
   - Security tests (SSRF, response size, redirects)
   - Timeout and network error tests
   - Encoding edge case tests
   - Integration tests with local HTTP server
   - Telemetry emission tests
   - Rate limiter integration tests

### Open Questions (Resolved)

| Question | Resolution |
|----------|------------|
| Source or Transform? | Transform - input is URL list from source |
| Output format? | Configurable with markdown default |
| Fingerprint normalization? | Three modes: content, full, structure |
| HTTP library? | httpx (modern, async-ready) |
| HTML→Markdown library? | html2text (20+ years stable) |
| Error handling? | LLM-style retryable classification |

---

## Section 9: Limitations

This section documents known limitations and out-of-scope features.

### JavaScript-Rendered Content (Not Supported)

**Limitation:** This transform fetches raw HTML. Single-Page Applications (SPAs) built with React, Vue, Angular, etc., render content via JavaScript after page load. The transform will capture only the initial HTML skeleton.

**Symptoms:**
- Content field contains minimal text (e.g., "Loading..." or framework boilerplate)
- Fingerprints are stable but useless (always the same skeleton)
- No errors are raised - this is a silent data quality issue

**Detection heuristic (future enhancement):**
```python
# Detect SPA skeletons - emit warning if content looks like framework boilerplate
SPA_INDICATORS = [
    '<div id="root"></div>',
    '<div id="app"></div>',
    'window.__INITIAL_STATE__',
    'ng-app',
]

if any(indicator in html for indicator in SPA_INDICATORS):
    ctx.warn("Possible SPA detected - JavaScript rendering not supported")
```

**Workaround:** For JavaScript-heavy sites, use a headless browser solution (Playwright, Puppeteer) outside ELSPETH, then feed the rendered HTML to a file-based source.

**Future consideration:** A `WebScrapeBrowserTransform` using Playwright could be added as a separate plugin in a `[web-browser]` optional dependency group.

### Cookie and Session Handling (Not Supported)

**Limitation:** Each request is stateless. Cookies are not persisted between requests, and session-based authentication is not supported.

**Impact:**
- Sites requiring login will return login pages, not content
- Sites with cookie-based consent banners may show consent pages
- Multi-step navigation (click this, then click that) is not possible

**Workaround:** For authenticated sites, consider:
1. Using API endpoints instead of web pages (if available)
2. Manual cookie injection via custom headers (not recommended for compliance)
3. External session capture with cookie export

### Authentication (Not Supported)

**Limitation:** No built-in support for:
- Basic Auth
- OAuth / OAuth2
- API keys in query params
- Form-based login

**Workaround:** Basic Auth could be added via the `headers` config:
```yaml
http:
  headers:
    Authorization: "Basic base64encodedcredentials"
```

This is not recommended for compliance monitoring scenarios.

### robots.txt Compliance (Not Enforced)

**Limitation:** The transform does not check or respect `robots.txt` directives.

**Rationale:** Compliance monitoring of public government transparency statements typically does not require robots.txt compliance (monitoring your own pages or pages you have legal authority to access).

**Future consideration:** An optional `respect_robots_txt: true` config could be added for general-purpose scraping.

### HTTP Proxy Support (Not Implemented)

**Limitation:** No proxy configuration. All requests are made directly.

**Future consideration:** httpx supports proxies natively:
```python
client = httpx.Client(proxies="http://proxy.example.com:8080")
```

Could be exposed via config if needed.

### Caching (Not Implemented)

**Limitation:** No response caching. Each pipeline run fetches fresh content.

**Rationale:** For compliance monitoring, fresh content is typically required. Caching would complicate audit trail interpretation.

**Future consideration:** HTTP-standard caching (ETag, If-Modified-Since) could reduce bandwidth for unchanged pages.

### Summary of Limitations

| Feature | Status | Workaround Available? |
|---------|--------|----------------------|
| JavaScript rendering | ❌ Not supported | External headless browser |
| Cookie persistence | ❌ Not supported | Manual header injection |
| Session authentication | ❌ Not supported | None |
| Basic Auth | ⚠️ Manual via headers | Yes (not recommended) |
| OAuth | ❌ Not supported | None |
| robots.txt | ❌ Not checked | N/A for compliance use case |
| HTTP proxy | ❌ Not implemented | httpx supports it natively |
| Response caching | ❌ Not implemented | N/A for compliance use case |
