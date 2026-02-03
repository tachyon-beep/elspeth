# Web Scrape Transform Design

**Date:** 2026-02-03
**Status:** Draft - Ready for Implementation
**Author:** Brainstorming session

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
        timeout: 30                        # seconds
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

### Structure Mode

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

| HTTP Status | Error Type | Retryable? | Behavior |
|-------------|------------|------------|----------|
| 429 | `RateLimitError` | ✅ Yes | Re-raise for engine RetryManager |
| 500, 502, 503, 504 | `ServerError` | ✅ Yes | Re-raise for engine RetryManager |
| Timeout / Connection refused | `NetworkError` | ✅ Yes | Re-raise for engine RetryManager |
| 404 | `NotFoundError` | ❌ No | `TransformResult.error()` |
| 403 | `ForbiddenError` | ❌ No | `TransformResult.error()` |
| 401 | `UnauthorizedError` | ❌ No | `TransformResult.error()` |
| SSL/TLS failure | `SSLError` | ❌ No | `TransformResult.error()` |
| Invalid URL | `InvalidURLError` | ❌ No | `TransformResult.error()` |
| Malformed response | `ParseError` | ❌ No | `TransformResult.error()` |

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

## Section 6: Dependencies and Implementation

### New Dependencies

| Package | Version | Purpose | Size |
|---------|---------|---------|------|
| `html2text` | `>=2024.2.26` | HTML→Markdown conversion | ~50KB |
| `httpx` | `>=0.27` | Modern async-capable HTTP client | ~200KB |

**Why httpx over requests:**
- Built-in timeout handling (requests is notorious for hanging)
- HTTP/2 support (some gov sites use it)
- Better redirect handling
- Same API style, easier testing with respx
- Future-proofs for async parallelization

**Note:** `beautifulsoup4` is already in ELSPETH's dependencies.

### File Structure

```
src/elspeth/plugins/
├── transforms/
│   └── web_scrape.py           # Main transform
├── clients/
│   └── http.py                 # AuditedHTTPClient (new)
```

### AuditedHTTPClient

Following the `AuditedLLMClient` pattern - wraps httpx with audit recording:

```python
class AuditedHTTPClient:
    """HTTP client with automatic audit trail recording."""

    def __init__(
        self,
        recorder: LandscapeRecorder,
        state_id: str,
        run_id: str,
        payload_store: PayloadStore,
        *,
        timeout: float = 30.0,
        max_redirects: int = 5,
        headers: dict[str, str] | None = None,
    ) -> None:
        self._recorder = recorder
        self._state_id = state_id
        self._run_id = run_id
        self._payload_store = payload_store

        self._client = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            max_redirects=max_redirects,
            headers=headers,
        )

    def get(self, url: str) -> HTTPResponse:
        """Fetch URL with full audit recording."""
        # Store request payload
        # Make request
        # Store response payload
        # Record call in Landscape
        # Return response or raise typed error
```

### Registration

```python
# src/elspeth/plugins/transforms/hookimpl.py
from elspeth.plugins.transforms.web_scrape import WebScrapeTransform

class ElspethBuiltinTransforms:
    @hookimpl
    def elspeth_get_transforms(self) -> list[type[Any]]:
        return [..., WebScrapeTransform]

# src/elspeth/cli.py
TRANSFORM_PLUGINS: dict[str, type[BaseTransform]] = {
    ...,
    "web_scrape": WebScrapeTransform,
}
```

### Optional Dependency Group

```toml
# pyproject.toml
[project.optional-dependencies]
web = [
    "html2text>=2024.2.26",
    "httpx>=0.27",
]
all = [
    "elspeth[llm,azure,web]",  # Add to 'all' group
]
```

Install with: `uv pip install -e ".[web]"`

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

Inherit from the standard base to get 15+ protocol tests free:

```python
from tests.contracts.transform_contracts.test_transform_protocol import (
    TransformContractPropertyTestBase,
)

class TestWebScrapeContract(TransformContractPropertyTestBase):
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

1. **Create `AuditedHTTPClient`** in `src/elspeth/plugins/clients/http.py`
   - Follow `AuditedLLMClient` pattern
   - Payload storage for request/response
   - Error classification (retryable vs non-retryable)

2. **Create `WebScrapeTransform`** in `src/elspeth/plugins/transforms/web_scrape.py`
   - Config validation (mandatory fields)
   - Content extraction (markdown/text/raw)
   - Fingerprinting (content/full/structure modes)
   - Integration with AuditedHTTPClient

3. **Create error hierarchy** in `src/elspeth/plugins/clients/http.py`
   - `WebScrapeError` base with `retryable` flag
   - Typed subclasses for each error category

4. **Add dependencies** to `pyproject.toml`
   - `html2text>=2024.2.26`
   - `httpx>=0.27`
   - New `[web]` optional dependency group

5. **Register plugin** in hookimpl.py and cli.py

6. **Write tests**
   - Unit tests with respx mocking
   - Contract tests (inherit from base)
   - Fingerprint stability tests
   - Integration tests with local HTTP server

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

## Appendix: Rate Limiting Consideration

For high-volume scraping, integrate with ELSPETH's existing rate limiting:

```yaml
rate_limit:
  enabled: true
  services:
    web_scrape:
      requests_per_minute: 60  # Respectful default
```

The `AuditedHTTPClient` should accept an optional `limiter` parameter (like `AuditedLLMClient`) to throttle requests per configured policy.
