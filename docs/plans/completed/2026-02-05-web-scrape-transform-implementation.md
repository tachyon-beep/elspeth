# Web Scrape Transform Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement a production-ready web scraping transform that fetches URLs, converts HTML to markdown/text, generates fingerprints for change detection, and integrates with ELSPETH's audit trail.

**Architecture:** Transform plugin using BatchTransformMixin for concurrent fetches, AuditedHTTPClient for audit trail integration, shared security infrastructure for SSRF prevention, and PayloadStore for forensic recovery. Follows LLM plugin error handling pattern with retryable vs non-retryable classification.

**Tech Stack:** httpx (HTTP client), html2text (HTML→Markdown), BeautifulSoup4 (HTML parsing), respx (testing), ThreadPoolExecutor (conversion timeout), existing ELSPETH infrastructure (BatchTransformMixin, AuditedHTTPClient, RateLimitRegistry, PayloadStore)

---

## Task 1: Create Shared Security Infrastructure

**Files:**
- Create: `src/elspeth/core/security/web.py`
- Modify: `src/elspeth/core/security/__init__.py`
- Test: `tests/core/security/test_web.py`

**Rationale:** Extracting security validators into shared infrastructure prevents code duplication and is a one-way door decision (once shipped without shared infrastructure, changing it is breaking).

**Step 1: Write failing test for scheme validation**

Create `tests/core/security/test_web.py`:

```python
import pytest
from elspeth.core.security.web import validate_url_scheme, SSRFBlockedError


def test_validate_url_scheme_allows_https():
    """HTTPS URLs should pass validation."""
    # Should not raise
    validate_url_scheme("https://example.com/page")


def test_validate_url_scheme_allows_http():
    """HTTP URLs should pass validation."""
    # Should not raise
    validate_url_scheme("http://example.com/page")


def test_validate_url_scheme_blocks_file():
    """File URLs should be blocked."""
    with pytest.raises(SSRFBlockedError, match="Forbidden scheme: file"):
        validate_url_scheme("file:///etc/passwd")


def test_validate_url_scheme_blocks_ftp():
    """FTP URLs should be blocked."""
    with pytest.raises(SSRFBlockedError, match="Forbidden scheme: ftp"):
        validate_url_scheme("ftp://example.com/file")
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/core/security/test_web.py::test_validate_url_scheme_allows_https -v`

Expected: FAIL with "ModuleNotFoundError: No module named 'elspeth.core.security.web'"

**Step 3: Write minimal implementation for scheme validation**

Create `src/elspeth/core/security/web.py`:

```python
"""Web security infrastructure for SSRF prevention and URL validation."""

import urllib.parse


class SSRFBlockedError(Exception):
    """URL validation failed due to security policy (SSRF prevention)."""
    pass


ALLOWED_SCHEMES = {"http", "https"}


def validate_url_scheme(url: str) -> None:
    """Validate URL scheme is in allowlist (http/https only).

    Args:
        url: URL to validate

    Raises:
        SSRFBlockedError: If scheme is not in allowlist
    """
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise SSRFBlockedError(f"Forbidden scheme: {parsed.scheme}")
```

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/core/security/test_web.py::test_validate_url_scheme_allows_https -v`

Expected: PASS

**Step 5: Commit scheme validation**

```bash
git add tests/core/security/test_web.py src/elspeth/core/security/web.py
git commit -m "feat(security): add URL scheme validation for SSRF prevention"
```

**Step 6: Write failing test for IP validation**

Add to `tests/core/security/test_web.py`:

```python
from unittest.mock import patch
from elspeth.core.security.web import validate_ip, NetworkError


def test_validate_ip_allows_public_ip():
    """Public IPs should pass validation."""
    with patch("socket.gethostbyname", return_value="8.8.8.8"):
        ip = validate_ip("example.com")
        assert ip == "8.8.8.8"


def test_validate_ip_blocks_loopback():
    """Loopback IPs should be blocked."""
    with patch("socket.gethostbyname", return_value="127.0.0.1"):
        with pytest.raises(SSRFBlockedError, match="Blocked IP range: 127.0.0.1"):
            validate_ip("localhost")


def test_validate_ip_blocks_private_class_a():
    """Private Class A IPs should be blocked."""
    with patch("socket.gethostbyname", return_value="10.0.0.1"):
        with pytest.raises(SSRFBlockedError, match="Blocked IP range: 10.0.0.1"):
            validate_ip("internal.example.com")


def test_validate_ip_blocks_cloud_metadata():
    """Cloud metadata IPs should be blocked."""
    with patch("socket.gethostbyname", return_value="169.254.169.254"):
        with pytest.raises(SSRFBlockedError, match="Blocked IP range: 169.254.169.254"):
            validate_ip("metadata.google.internal")


def test_validate_ip_dns_timeout():
    """DNS resolution timeout should raise NetworkError."""
    def slow_dns(hostname):
        import time
        time.sleep(10)
        return "8.8.8.8"

    with patch("socket.gethostbyname", side_effect=slow_dns):
        with pytest.raises(NetworkError, match="DNS resolution timeout"):
            validate_ip("slow.example.com", timeout=0.1)


def test_validate_ip_dns_failure():
    """DNS resolution failure should raise NetworkError."""
    import socket
    with patch("socket.gethostbyname", side_effect=socket.gaierror("DNS failed")):
        with pytest.raises(NetworkError, match="DNS resolution failed"):
            validate_ip("nonexistent.example.com")
```

**Step 7: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/core/security/test_web.py::test_validate_ip_allows_public_ip -v`

Expected: FAIL with "ImportError: cannot import name 'validate_ip'"

**Step 8: Write IP validation implementation**

Add to `src/elspeth/core/security/web.py`:

```python
import ipaddress
import socket
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError


class NetworkError(Exception):
    """Network operation failed (DNS, connection, etc.)."""
    pass


# Private, loopback, and cloud metadata IP ranges
BLOCKED_IP_RANGES = [
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

    Args:
        hostname: Hostname to resolve
        timeout: DNS resolution timeout in seconds

    Returns:
        Resolved IP address as string

    Raises:
        NetworkError: If DNS resolution fails or times out
        SSRFBlockedError: If resolved IP is in blocked ranges
    """
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
    for blocked in BLOCKED_IP_RANGES:
        if ip in blocked:
            raise SSRFBlockedError(f"Blocked IP range: {ip_str} in {blocked}")

    return ip_str
```

**Step 9: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/core/security/test_web.py -v`

Expected: All tests PASS

**Step 10: Export from security module**

Modify `src/elspeth/core/security/__init__.py`:

```python
"""Security infrastructure for ELSPETH."""

from elspeth.core.security.web import (
    NetworkError,
    SSRFBlockedError,
    validate_ip,
    validate_url_scheme,
)

__all__ = [
    "NetworkError",
    "SSRFBlockedError",
    "validate_ip",
    "validate_url_scheme",
]
```

**Step 11: Commit IP validation**

```bash
git add tests/core/security/test_web.py src/elspeth/core/security/web.py src/elspeth/core/security/__init__.py
git commit -m "feat(security): add IP validation with DNS timeout and blocklist"
```

---

## Task 2: Add Dependencies to pyproject.toml

**Files:**
- Modify: `pyproject.toml`

**Step 1: Add web optional dependency group**

Find the `[project.optional-dependencies]` section and add:

```toml
web = [
    "html2text>=2024.2.26",
    "beautifulsoup4>=4.12,<5",
]
```

**Step 2: Add respx to dev dependencies**

In the `dev` list, add:

```toml
dev = [
    # ... existing deps ...
    "respx>=0.21,<1",  # httpx mocking for web scrape tests
]
```

**Step 3: Add web to all group**

Modify the `all` list to include `web`:

```toml
all = [
    "elspeth[llm,azure,web]",
]
```

**Step 4: Install new dependencies**

Run: `uv pip install -e ".[web,dev]"`

Expected: Successfully installs html2text, beautifulsoup4, respx

**Step 5: Commit dependency changes**

```bash
git add pyproject.toml
git commit -m "build: add web optional dependency group (html2text, beautifulsoup4)"
```

---

## Task 3: Extend AuditedHTTPClient with GET Method

**Files:**
- Modify: `src/elspeth/plugins/clients/http.py`
- Test: `tests/plugins/clients/test_http_client.py`

**Step 1: Write failing test for GET method**

Add to `tests/plugins/clients/test_http_client.py`:

```python
import respx
from httpx import Response
from elspeth.plugins.clients.http import AuditedHTTPClient


@respx.mock
def test_audited_http_client_get_success(mock_landscape, mock_ctx):
    """GET request should record to landscape and return response."""
    respx.get("https://example.com/page").mock(
        return_value=Response(200, text="<html>Content</html>")
    )

    client = AuditedHTTPClient(
        landscape=mock_landscape,
        state_id="state-123",
        run_id="run-456",
    )

    response = client.get("https://example.com/page")

    assert response.status_code == 200
    assert response.text == "<html>Content</html>"

    # Verify landscape recording
    assert mock_landscape.record_call.called


@respx.mock
def test_audited_http_client_get_with_params(mock_landscape, mock_ctx):
    """GET with query params should include params in request."""
    respx.get("https://example.com/api").mock(
        return_value=Response(200, json={"result": "ok"})
    )

    client = AuditedHTTPClient(
        landscape=mock_landscape,
        state_id="state-123",
        run_id="run-456",
    )

    response = client.get("https://example.com/api", params={"key": "value"})

    assert response.status_code == 200
    # Verify params were included
    assert "key=value" in str(respx.calls.last.request.url)
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/plugins/clients/test_http_client.py::test_audited_http_client_get_success -v`

Expected: FAIL with "AttributeError: 'AuditedHTTPClient' object has no attribute 'get'"

**Step 3: Add GET method to AuditedHTTPClient**

Add to `src/elspeth/plugins/clients/http.py` (after the `post` method):

```python
def get(
    self,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, str] | None = None,
) -> HTTPResponse:
    """Execute GET request with full audit recording.

    Args:
        url: URL to fetch
        headers: Optional request headers
        params: Optional query parameters

    Returns:
        HTTPResponse with status, content, headers

    Raises:
        HTTPError: On request failure
    """
    start_time = time.time()

    # Merge headers with responsible scraping headers if configured
    merged_headers = dict(headers or {})

    # Fingerprint auth headers if present
    auth_fingerprint = None
    if "Authorization" in merged_headers:
        auth_fingerprint = self._fingerprint_auth(merged_headers["Authorization"])

    # Make request with rate limiting
    if self._limiter:
        self._limiter.acquire()

    try:
        response = self._client.get(url, headers=merged_headers, params=params)
        response.raise_for_status()

        duration_ms = int((time.time() - start_time) * 1000)

        # Record call to landscape
        self._landscape.record_call(
            state_id=self._state_id,
            call_type="http_get",
            request_data={
                "url": url,
                "headers": merged_headers,
                "params": params,
                "auth_fingerprint": auth_fingerprint,
            },
            response_data={
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "content_length": len(response.content),
            },
            duration_ms=duration_ms,
        )

        # Emit telemetry if configured
        if self._telemetry_emit:
            self._telemetry_emit({
                "event": "http.get",
                "url": url,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            })

        return HTTPResponse(
            status_code=response.status_code,
            content=response.content,
            headers=dict(response.headers),
        )

    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)

        # Record error to landscape
        self._landscape.record_call(
            state_id=self._state_id,
            call_type="http_get",
            request_data={"url": url, "headers": merged_headers, "params": params},
            response_data={"error": str(e)},
            duration_ms=duration_ms,
            error=str(e),
        )

        raise HTTPError(f"GET {url} failed: {e}") from e
```

**Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/plugins/clients/test_http_client.py::test_audited_http_client_get_success -v`

Expected: PASS

**Step 5: Commit GET method**

```bash
git add src/elspeth/plugins/clients/http.py tests/plugins/clients/test_http_client.py
git commit -m "feat(http): add GET method to AuditedHTTPClient with audit trail"
```

---

## Task 4: Create Error Hierarchy for Web Scraping

**Files:**
- Create: `src/elspeth/plugins/transforms/web_scrape_errors.py`
- Test: `tests/plugins/transforms/test_web_scrape_errors.py`

**Step 1: Write failing test for error hierarchy**

Create `tests/plugins/transforms/test_web_scrape_errors.py`:

```python
import pytest
from elspeth.plugins.transforms.web_scrape_errors import (
    WebScrapeError,
    RateLimitError,
    NetworkError,
    ServerError,
    NotFoundError,
    ForbiddenError,
    SSRFBlockedError,
    ResponseTooLargeError,
)


def test_rate_limit_error_is_retryable():
    """RateLimitError should be retryable."""
    error = RateLimitError("Rate limit exceeded")
    assert error.retryable is True


def test_network_error_is_retryable():
    """NetworkError should be retryable."""
    error = NetworkError("Connection timeout")
    assert error.retryable is True


def test_server_error_is_retryable():
    """ServerError should be retryable."""
    error = ServerError("503 Service Unavailable")
    assert error.retryable is True


def test_not_found_error_is_not_retryable():
    """NotFoundError should not be retryable."""
    error = NotFoundError("404 Not Found")
    assert error.retryable is False


def test_forbidden_error_is_not_retryable():
    """ForbiddenError should not be retryable."""
    error = ForbiddenError("403 Forbidden")
    assert error.retryable is False


def test_ssrf_blocked_error_is_not_retryable():
    """SSRFBlockedError should not be retryable."""
    error = SSRFBlockedError("Blocked IP: 127.0.0.1")
    assert error.retryable is False


def test_response_too_large_error_is_not_retryable():
    """ResponseTooLargeError should not be retryable."""
    error = ResponseTooLargeError("Response exceeds 10MB")
    assert error.retryable is False
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/plugins/transforms/test_web_scrape_errors.py::test_rate_limit_error_is_retryable -v`

Expected: FAIL with "ModuleNotFoundError: No module named 'elspeth.plugins.transforms.web_scrape_errors'"

**Step 3: Write error hierarchy implementation**

Create `src/elspeth/plugins/transforms/web_scrape_errors.py`:

```python
"""Error hierarchy for web scraping transform.

Follows LLM plugin pattern: retryable errors are re-raised for engine
RetryManager, non-retryable errors return TransformResult.error().
"""


class WebScrapeError(Exception):
    """Base error for web scrape transform."""

    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


# Retryable errors (re-raise for engine retry)

class RateLimitError(WebScrapeError):
    """HTTP 429 or rate limit exceeded."""

    def __init__(self, message: str) -> None:
        super().__init__(message, retryable=True)


class NetworkError(WebScrapeError):
    """Network/connection errors (DNS, timeout, connection refused)."""

    def __init__(self, message: str) -> None:
        super().__init__(message, retryable=True)


class ServerError(WebScrapeError):
    """HTTP 5xx server errors."""

    def __init__(self, message: str) -> None:
        super().__init__(message, retryable=True)


class TimeoutError(WebScrapeError):
    """HTTP 408 Request Timeout."""

    def __init__(self, message: str) -> None:
        super().__init__(message, retryable=True)


# Non-retryable errors (return TransformResult.error())

class NotFoundError(WebScrapeError):
    """HTTP 404 Not Found."""

    def __init__(self, message: str) -> None:
        super().__init__(message, retryable=False)


class ForbiddenError(WebScrapeError):
    """HTTP 403 Forbidden."""

    def __init__(self, message: str) -> None:
        super().__init__(message, retryable=False)


class UnauthorizedError(WebScrapeError):
    """HTTP 401 Unauthorized."""

    def __init__(self, message: str) -> None:
        super().__init__(message, retryable=False)


class SSLError(WebScrapeError):
    """SSL/TLS certificate validation failure."""

    def __init__(self, message: str) -> None:
        super().__init__(message, retryable=False)


class InvalidURLError(WebScrapeError):
    """Malformed or invalid URL."""

    def __init__(self, message: str) -> None:
        super().__init__(message, retryable=False)


class ParseError(WebScrapeError):
    """HTML parsing or conversion failed."""

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
```

**Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/plugins/transforms/test_web_scrape_errors.py -v`

Expected: All tests PASS

**Step 5: Commit error hierarchy**

```bash
git add src/elspeth/plugins/transforms/web_scrape_errors.py tests/plugins/transforms/test_web_scrape_errors.py
git commit -m "feat(web-scrape): add error hierarchy with retryable classification"
```

---

## Task 5: Implement Content Extraction (HTML → Markdown/Text)

**Files:**
- Create: `src/elspeth/plugins/transforms/web_scrape_extraction.py`
- Test: `tests/plugins/transforms/test_web_scrape_extraction.py`

**Step 1: Write failing test for markdown extraction**

Create `tests/plugins/transforms/test_web_scrape_extraction.py`:

```python
import pytest
from elspeth.plugins.transforms.web_scrape_extraction import extract_content


def test_extract_content_markdown():
    """HTML should convert to markdown."""
    html = "<html><body><h1>Title</h1><p>Content here</p></body></html>"

    result = extract_content(html, format="markdown")

    assert "# Title" in result
    assert "Content here" in result


def test_extract_content_text():
    """HTML should convert to plain text."""
    html = "<html><body><h1>Title</h1><p>Content</p></body></html>"

    result = extract_content(html, format="text")

    assert "Title" in result
    assert "Content" in result
    assert "<h1>" not in result  # No HTML tags


def test_extract_content_raw():
    """Raw format should return HTML unchanged."""
    html = "<html><body><h1>Test</h1></body></html>"

    result = extract_content(html, format="raw")

    assert result == html


def test_extract_content_strips_configured_elements():
    """Should remove configured HTML elements."""
    html = """
    <html>
        <head><script>alert('bad')</script></head>
        <body>
            <nav>Navigation</nav>
            <main><p>Content</p></main>
            <footer>Footer</footer>
        </body>
    </html>
    """

    result = extract_content(
        html,
        format="text",
        strip_elements=["script", "nav", "footer"],
    )

    assert "Content" in result
    assert "Navigation" not in result
    assert "Footer" not in result
    assert "alert" not in result
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/plugins/transforms/test_web_scrape_extraction.py::test_extract_content_markdown -v`

Expected: FAIL with "ModuleNotFoundError: No module named 'elspeth.plugins.transforms.web_scrape_extraction'"

**Step 3: Write extraction implementation**

Create `src/elspeth/plugins/transforms/web_scrape_extraction.py`:

```python
"""Content extraction utilities for web scraping.

Converts HTML to markdown, text, or raw format with configurable
element stripping.
"""

from typing import Any

import html2text
from bs4 import BeautifulSoup


def extract_content(
    html: str,
    format: str,
    strip_elements: list[str] | None = None,
) -> str:
    """Extract content from HTML in specified format.

    Args:
        html: Raw HTML content
        format: Output format ("markdown", "text", "raw")
        strip_elements: HTML tags to remove before extraction

    Returns:
        Extracted content as string
    """
    if format == "raw":
        return html

    # Parse HTML and strip unwanted elements
    soup = BeautifulSoup(html, "html.parser")

    if strip_elements:
        for tag_name in strip_elements:
            for tag in soup.find_all(tag_name):
                tag.decompose()

    # Extract based on format
    if format == "markdown":
        # Get cleaned HTML back from soup
        cleaned_html = str(soup)

        h = html2text.HTML2Text()
        h.ignore_links = False
        h.ignore_images = False
        h.body_width = 0  # Don't wrap lines
        h.ignore_tables = False
        h.ignore_emphasis = False

        return h.handle(cleaned_html)

    elif format == "text":
        return soup.get_text(separator=" ", strip=True)

    else:
        raise ValueError(f"Unknown format: {format}")
```

**Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/plugins/transforms/test_web_scrape_extraction.py -v`

Expected: All tests PASS

**Step 5: Commit extraction implementation**

```bash
git add src/elspeth/plugins/transforms/web_scrape_extraction.py tests/plugins/transforms/test_web_scrape_extraction.py
git commit -m "feat(web-scrape): add HTML extraction (markdown/text/raw)"
```

---

## Task 6: Implement Fingerprinting

**Files:**
- Create: `src/elspeth/plugins/transforms/web_scrape_fingerprint.py`
- Test: `tests/plugins/transforms/test_web_scrape_fingerprint.py`

**Step 1: Write failing test for content fingerprinting**

Create `tests/plugins/transforms/test_web_scrape_fingerprint.py`:

```python
import pytest
from elspeth.plugins.transforms.web_scrape_fingerprint import compute_fingerprint


def test_fingerprint_deterministic():
    """Same content should produce same fingerprint."""
    content = "Hello world"

    fp1 = compute_fingerprint(content, mode="content")
    fp2 = compute_fingerprint(content, mode="content")

    assert fp1 == fp2
    assert len(fp1) == 64  # SHA-256 hex


def test_fingerprint_content_mode_whitespace_insensitive():
    """Content mode should ignore whitespace changes."""
    content1 = "Hello world"
    content2 = "Hello   world"
    content3 = "Hello\n\nworld"

    fp1 = compute_fingerprint(content1, mode="content")
    fp2 = compute_fingerprint(content2, mode="content")
    fp3 = compute_fingerprint(content3, mode="content")

    assert fp1 == fp2 == fp3


def test_fingerprint_full_mode_whitespace_sensitive():
    """Full mode should detect whitespace changes."""
    content1 = "Hello world"
    content2 = "Hello   world"

    fp1 = compute_fingerprint(content1, mode="full")
    fp2 = compute_fingerprint(content2, mode="full")

    assert fp1 != fp2


def test_fingerprint_content_mode_detects_text_changes():
    """Content mode should detect meaningful text changes."""
    content1 = "The policy is active"
    content2 = "The policy is inactive"

    fp1 = compute_fingerprint(content1, mode="content")
    fp2 = compute_fingerprint(content2, mode="content")

    assert fp1 != fp2
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/plugins/transforms/test_web_scrape_fingerprint.py::test_fingerprint_deterministic -v`

Expected: FAIL with "ModuleNotFoundError: No module named 'elspeth.plugins.transforms.web_scrape_fingerprint'"

**Step 3: Write fingerprint implementation**

Create `src/elspeth/plugins/transforms/web_scrape_fingerprint.py`:

```python
"""Fingerprinting utilities for web scraping change detection."""

import hashlib
import re


def normalize_for_fingerprint(content: str) -> str:
    """Normalize content for change-resistant fingerprinting.

    Collapses whitespace sequences to single space and strips
    leading/trailing whitespace.

    Args:
        content: Raw content

    Returns:
        Normalized content
    """
    # Collapse all whitespace sequences to single space
    normalized = re.sub(r'\s+', ' ', content)
    # Strip leading/trailing
    return normalized.strip()


def compute_fingerprint(content: str, mode: str) -> str:
    """Compute SHA-256 fingerprint of content.

    Args:
        content: Content to fingerprint
        mode: Fingerprint mode ("content", "full", "structure")

    Returns:
        SHA-256 hex digest (64 characters)
    """
    if mode == "content":
        content = normalize_for_fingerprint(content)
    elif mode == "structure":
        # Structure mode not implemented yet - defer to later task
        raise NotImplementedError("Structure mode not yet implemented")
    # mode == "full" uses raw content as-is

    return hashlib.sha256(content.encode("utf-8")).hexdigest()
```

**Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/plugins/transforms/test_web_scrape_fingerprint.py -v`

Expected: All tests PASS

**Step 5: Commit fingerprint implementation**

```bash
git add src/elspeth/plugins/transforms/web_scrape_fingerprint.py tests/plugins/transforms/test_web_scrape_fingerprint.py
git commit -m "feat(web-scrape): add content fingerprinting with normalization"
```

---

## Task 7: Implement WebScrapeTransform Core (Without Concurrency)

**Files:**
- Create: `src/elspeth/plugins/transforms/web_scrape.py`
- Test: `tests/plugins/transforms/test_web_scrape.py`

**Step 1: Write failing test for basic scrape**

Create `tests/plugins/transforms/test_web_scrape.py`:

```python
import pytest
import respx
from httpx import Response

from elspeth.plugins.transforms.web_scrape import WebScrapeTransform
from elspeth.plugins.context import PluginContext


@pytest.fixture
def mock_ctx(mocker):
    """Mock PluginContext with required attributes."""
    ctx = mocker.Mock(spec=PluginContext)
    ctx.state_id = "state-123"
    ctx.run_id = "run-456"
    ctx.landscape = mocker.Mock()
    ctx.rate_limit_registry = mocker.Mock()
    ctx.rate_limit_registry.get_limiter.return_value = None
    ctx.payload_store = mocker.Mock()
    ctx.payload_store.store.side_effect = lambda data: hashlib.sha256(data).hexdigest()
    ctx.telemetry_emit = mocker.Mock()
    return ctx


@respx.mock
def test_web_scrape_success_markdown(mock_ctx):
    """Successful scrape should enrich row with content and fingerprint."""
    html_content = "<html><body><h1>Title</h1><p>Content here</p></body></html>"

    respx.get("https://example.com/page").mock(
        return_value=Response(200, text=html_content)
    )

    transform = WebScrapeTransform({
        "schema": {"fields": "dynamic"},
        "url_field": "url",
        "content_field": "page_content",
        "fingerprint_field": "page_fingerprint",
        "format": "markdown",
        "fingerprint_mode": "content",
        "http": {
            "abuse_contact": "test@example.com",
            "scraping_reason": "Unit testing web scrape transform",
        },
    })

    result = transform.process({"url": "https://example.com/page"}, mock_ctx)

    assert result.status == "success"
    assert "# Title" in result.row["page_content"]
    assert "Content here" in result.row["page_content"]
    assert result.row["page_fingerprint"] is not None
    assert len(result.row["page_fingerprint"]) == 64  # SHA-256
    assert result.row["fetch_status"] == 200
    assert result.row["fetch_url_final"] == "https://example.com/page"


@respx.mock
def test_web_scrape_404_returns_error(mock_ctx):
    """404 should return error result (non-retryable)."""
    respx.get("https://example.com/missing").mock(
        return_value=Response(404)
    )

    transform = WebScrapeTransform({
        "schema": {"fields": "dynamic"},
        "url_field": "url",
        "content_field": "page_content",
        "fingerprint_field": "page_fingerprint",
        "http": {
            "abuse_contact": "test@example.com",
            "scraping_reason": "Testing",
        },
    })

    result = transform.process({"url": "https://example.com/missing"}, mock_ctx)

    assert result.status == "error"
    assert result.reason["error_type"] == "NotFoundError"
    assert "404" in result.reason["message"]
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/plugins/transforms/test_web_scrape.py::test_web_scrape_success_markdown -v`

Expected: FAIL with "ModuleNotFoundError: No module named 'elspeth.plugins.transforms.web_scrape'"

**Step 3: Write WebScrapeTransform skeleton**

Create `src/elspeth/plugins/transforms/web_scrape.py`:

```python
"""Web scraping transform with audit trail integration."""

from typing import Any

import httpx

from elspeth.contracts import Determinism
from elspeth.plugins.base import BaseTransform
from elspeth.plugins.config_base import TransformDataConfig
from elspeth.plugins.context import PluginContext
from elspeth.plugins.results import TransformResult
from elspeth.plugins.schema_factory import create_schema_from_config
from elspeth.plugins.clients.http import AuditedHTTPClient
from elspeth.core.security import validate_url_scheme, validate_ip

from elspeth.plugins.transforms.web_scrape_errors import (
    WebScrapeError,
    RateLimitError,
    NetworkError,
    ServerError,
    NotFoundError,
    ForbiddenError,
    UnauthorizedError,
    SSRFBlockedError,
)
from elspeth.plugins.transforms.web_scrape_extraction import extract_content
from elspeth.plugins.transforms.web_scrape_fingerprint import compute_fingerprint


class WebScrapeTransform(BaseTransform):
    """Fetch webpages, extract content, generate fingerprints.

    Designed for compliance monitoring use cases.
    """

    name = "web_scrape"
    determinism = Determinism.EXTERNAL_CALL
    plugin_version = "1.0.0"

    def __init__(self, options: dict[str, Any]) -> None:
        super().__init__(options)

        # Required fields
        self._url_field = options["url_field"]
        self._content_field = options["content_field"]
        self._fingerprint_field = options["fingerprint_field"]

        # Format and fingerprint mode
        self._format = options.get("format", "markdown")
        self._fingerprint_mode = options.get("fingerprint_mode", "content")

        # HTTP config
        http_config = options.get("http", {})
        self._abuse_contact = http_config["abuse_contact"]
        self._scraping_reason = http_config["scraping_reason"]
        self._timeout = http_config.get("timeout", 30)

        # Element stripping
        self._strip_elements = options.get("strip_elements", ["script", "style"])

        # Schema
        cfg = TransformDataConfig.from_dict(options)
        assert cfg.schema_config is not None
        schema = create_schema_from_config(
            cfg.schema_config,
            "WebScrapeSchema",
            allow_coercion=False,
        )
        self.input_schema = schema
        self.output_schema = schema

    def process(self, row: dict[str, Any], ctx: PluginContext) -> TransformResult:
        """Fetch URL and enrich row with content and fingerprint."""
        url = row[self._url_field]

        # Validate URL security
        try:
            validate_url_scheme(url)
            parsed = httpx.URL(url)
            if parsed.host:
                validate_ip(parsed.host)
        except Exception as e:
            return TransformResult.error({
                "error_type": type(e).__name__,
                "message": str(e),
                "url": url,
            })

        # Fetch URL
        try:
            response = self._fetch_url(url, ctx)
        except WebScrapeError as e:
            if e.retryable:
                raise  # Engine RetryManager handles
            return TransformResult.error({
                "error_type": type(e).__name__,
                "message": str(e),
                "url": url,
            })

        # Extract content
        content = extract_content(
            response.content.decode("utf-8"),
            format=self._format,
            strip_elements=self._strip_elements,
        )

        # Compute fingerprint
        fingerprint = compute_fingerprint(content, mode=self._fingerprint_mode)

        # Store payloads
        request_hash = ctx.payload_store.store(f"GET {url}".encode())
        response_raw_hash = ctx.payload_store.store(response.content)
        response_processed_hash = ctx.payload_store.store(content.encode())

        # Enrich row
        output = dict(row)
        output[self._content_field] = content
        output[self._fingerprint_field] = fingerprint
        output["fetch_status"] = response.status_code
        output["fetch_url_final"] = str(response.url)
        output["fetch_request_hash"] = request_hash
        output["fetch_response_raw_hash"] = response_raw_hash
        output["fetch_response_processed_hash"] = response_processed_hash

        return TransformResult.success(output)

    def _fetch_url(self, url: str, ctx: PluginContext) -> httpx.Response:
        """Fetch URL with audit recording."""
        # Get rate limiter
        limiter = ctx.rate_limit_registry.get_limiter("web_scrape")

        # Create audited client
        client = AuditedHTTPClient(
            landscape=ctx.landscape,
            state_id=ctx.state_id,
            run_id=ctx.run_id,
            limiter=limiter,
        )

        # Add responsible scraping headers
        headers = {
            "X-Abuse-Contact": self._abuse_contact,
            "X-Scraping-Reason": self._scraping_reason,
        }

        try:
            http_response = client.get(url, headers=headers)

            # Convert to httpx.Response for return
            response = httpx.Response(
                status_code=http_response.status_code,
                content=http_response.content,
                headers=http_response.headers,
            )

            # Check status code
            if response.status_code == 404:
                raise NotFoundError(f"HTTP 404: {url}")
            elif response.status_code == 403:
                raise ForbiddenError(f"HTTP 403: {url}")
            elif response.status_code == 401:
                raise UnauthorizedError(f"HTTP 401: {url}")
            elif response.status_code == 429:
                raise RateLimitError(f"HTTP 429: {url}")
            elif 500 <= response.status_code < 600:
                raise ServerError(f"HTTP {response.status_code}: {url}")

            return response

        except httpx.TimeoutException as e:
            raise NetworkError(f"Timeout fetching {url}: {e}")
        except httpx.ConnectError as e:
            raise NetworkError(f"Connection error fetching {url}: {e}")

    def close(self) -> None:
        """Release resources."""
        pass
```

**Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/plugins/transforms/test_web_scrape.py -v`

Expected: Tests PASS

**Step 5: Commit core transform**

```bash
git add src/elspeth/plugins/transforms/web_scrape.py tests/plugins/transforms/test_web_scrape.py
git commit -m "feat(web-scrape): implement core WebScrapeTransform with audit trail"
```

---

## Task 8: Add Contract Tests

**Files:**
- Create: `tests/contracts/transform_contracts/test_web_scrape_contract.py`

**Step 1: Write contract test**

Create `tests/contracts/transform_contracts/test_web_scrape_contract.py`:

```python
"""Contract tests for WebScrapeTransform.

Note: WebScrapeTransform does NOT inherit BatchTransformMixin yet,
so we use TransformContractPropertyTestBase. This will change when
we add concurrency in a later task.
"""

import pytest
from elspeth.plugins.transforms.web_scrape import WebScrapeTransform
from tests.contracts.transform_contracts.test_transform_protocol import (
    TransformContractPropertyTestBase,
)


class TestWebScrapeContract(TransformContractPropertyTestBase):
    """Verify WebScrapeTransform satisfies plugin contract."""

    @pytest.fixture
    def transform(self):
        return WebScrapeTransform({
            "schema": {"fields": "dynamic"},
            "url_field": "url",
            "content_field": "page_content",
            "fingerprint_field": "page_fingerprint",
            "http": {
                "abuse_contact": "test@example.com",
                "scraping_reason": "Contract testing web scrape transform",
            },
        })

    @pytest.fixture
    def valid_input(self):
        return {"url": "https://example.com"}
```

**Step 2: Run contract tests**

Run: `.venv/bin/python -m pytest tests/contracts/transform_contracts/test_web_scrape_contract.py -v`

Expected: All contract tests PASS

**Step 3: Commit contract tests**

```bash
git add tests/contracts/transform_contracts/test_web_scrape_contract.py
git commit -m "test(web-scrape): add contract tests for WebScrapeTransform"
```

---

## Task 9: Add html2text Determinism Tests

**Files:**
- Test: `tests/plugins/transforms/test_web_scrape_extraction.py`

**Step 1: Write determinism property test**

Add to `tests/plugins/transforms/test_web_scrape_extraction.py`:

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

**Step 2: Run determinism tests**

Run: `.venv/bin/python -m pytest tests/plugins/transforms/test_web_scrape_extraction.py::test_html2text_deterministic_simple -v`

Expected: PASS (verifies html2text is deterministic for audit integrity)

**Step 3: Commit determinism tests**

```bash
git add tests/plugins/transforms/test_web_scrape_extraction.py
git commit -m "test(web-scrape): add html2text determinism tests for audit integrity"
```

---

## Task 10: Add Security Tests (SSRF Prevention)

**Files:**
- Test: `tests/plugins/transforms/test_web_scrape_security.py`

**Step 1: Write SSRF security tests**

Create `tests/plugins/transforms/test_web_scrape_security.py`:

```python
"""Security tests for WebScrapeTransform (SSRF prevention)."""

import pytest
import respx
from httpx import Response
from unittest.mock import patch

from elspeth.plugins.transforms.web_scrape import WebScrapeTransform


@pytest.fixture
def transform():
    return WebScrapeTransform({
        "schema": {"fields": "dynamic"},
        "url_field": "url",
        "content_field": "page_content",
        "fingerprint_field": "page_fingerprint",
        "http": {
            "abuse_contact": "test@example.com",
            "scraping_reason": "Security testing",
        },
    })


@pytest.fixture
def mock_ctx(mocker):
    ctx = mocker.Mock()
    ctx.state_id = "state-123"
    ctx.run_id = "run-456"
    ctx.landscape = mocker.Mock()
    ctx.rate_limit_registry = mocker.Mock()
    ctx.rate_limit_registry.get_limiter.return_value = None
    ctx.payload_store = mocker.Mock()
    ctx.payload_store.store.side_effect = lambda data: hashlib.sha256(data).hexdigest()
    return ctx


def test_ssrf_blocks_file_scheme(transform, mock_ctx):
    """file:// URLs should be blocked."""
    result = transform.process({"url": "file:///etc/passwd"}, mock_ctx)

    assert result.status == "error"
    assert result.reason["error_type"] == "SSRFBlockedError"
    assert "file" in result.reason["message"]


def test_ssrf_blocks_private_ip(transform, mock_ctx):
    """Private IPs should be blocked."""
    with patch("socket.gethostbyname", return_value="192.168.1.1"):
        result = transform.process({"url": "https://internal.example.com"}, mock_ctx)

        assert result.status == "error"
        assert result.reason["error_type"] == "SSRFBlockedError"


def test_ssrf_blocks_loopback(transform, mock_ctx):
    """Loopback IPs should be blocked."""
    with patch("socket.gethostbyname", return_value="127.0.0.1"):
        result = transform.process({"url": "http://localhost/admin"}, mock_ctx)

        assert result.status == "error"
        assert result.reason["error_type"] == "SSRFBlockedError"


def test_ssrf_blocks_cloud_metadata(transform, mock_ctx):
    """Cloud metadata endpoints should be blocked."""
    with patch("socket.gethostbyname", return_value="169.254.169.254"):
        result = transform.process(
            {"url": "http://metadata.google.internal/computeMetadata/v1/"},
            mock_ctx,
        )

        assert result.status == "error"
        assert result.reason["error_type"] == "SSRFBlockedError"


@respx.mock
def test_ssrf_allows_public_ip(transform, mock_ctx):
    """Public IPs should be allowed."""
    respx.get("https://example.com/page").mock(
        return_value=Response(200, text="<html>Content</html>")
    )

    with patch("socket.gethostbyname", return_value="8.8.8.8"):
        result = transform.process({"url": "https://example.com/page"}, mock_ctx)

        assert result.status == "success"
```

**Step 2: Run security tests**

Run: `.venv/bin/python -m pytest tests/plugins/transforms/test_web_scrape_security.py -v`

Expected: All tests PASS

**Step 3: Commit security tests**

```bash
git add tests/plugins/transforms/test_web_scrape_security.py
git commit -m "test(web-scrape): add SSRF prevention security tests"
```

---

## Task 11: Documentation and Final Integration

**Files:**
- Create: `docs/plugins/web-scrape-transform.md`
- Modify: `README.md` (add web scraping to features list)

**Step 1: Write plugin documentation**

Create `docs/plugins/web-scrape-transform.md`:

```markdown
# Web Scrape Transform

Fetch webpages from URLs, convert content to markdown/text, and generate fingerprints for change detection.

## Configuration

```yaml
transforms:
  - plugin: web_scrape
    options:
      url_field: url
      content_field: page_content
      fingerprint_field: page_fingerprint
      format: markdown  # markdown | text | raw
      fingerprint_mode: content  # content | full

      http:
        abuse_contact: compliance@example.com
        scraping_reason: "Compliance monitoring"
        timeout: 30

      strip_elements:
        - script
        - style
        - nav
```

## Output Fields

| Field | Type | Description |
|-------|------|-------------|
| `{content_field}` | str | Extracted content |
| `{fingerprint_field}` | str | SHA-256 fingerprint |
| `fetch_status` | int | HTTP status code |
| `fetch_url_final` | str | Final URL after redirects |

## Security

- SSRF prevention (blocks private IPs, loopback, cloud metadata)
- Scheme whitelist (http/https only)
- SSL certificate verification (always enabled)

## Installation

```bash
uv pip install -e ".[web]"
```
```

**Step 2: Run full test suite**

Run: `.venv/bin/python -m pytest tests/plugins/transforms/test_web_scrape*.py tests/contracts/transform_contracts/test_web_scrape_contract.py -v`

Expected: All tests PASS

**Step 3: Commit documentation**

```bash
git add docs/plugins/web-scrape-transform.md
git commit -m "docs(web-scrape): add plugin documentation"
```

**Step 4: Final commit message**

```bash
git commit --allow-empty -m "feat(web-scrape): complete WebScrapeTransform implementation

- Shared security infrastructure (SSRF prevention, IP validation)
- Error hierarchy with retryable classification
- Content extraction (HTML → markdown/text/raw)
- Fingerprinting for change detection
- Full audit trail integration
- Comprehensive test coverage (unit, contract, security)
"
```

---

## Summary

**Total Tasks:** 11
**Estimated Time:** 4-6 hours
**Testing Approach:** TDD (test-first for all features)
**Commit Frequency:** After each passing test or logical unit

**Key Architecture Decisions:**
- Shared security infrastructure in `core/security/web.py` (one-way door)
- Following LLM plugin error pattern (retryable vs non-retryable)
- AuditedHTTPClient integration for full audit trail
- PayloadStore for forensic recovery
- html2text determinism verified for audit integrity

**Not Included (Future Tasks):**
- Concurrency via BatchTransformMixin (requires separate task)
- Response size limits with streaming
- HTML conversion timeout with ThreadPoolExecutor
- Structure fingerprint mode
- Rate limiting configuration examples
- Integration test with real HTTP server

**Next Steps After This Plan:**
- Review and execute plan task-by-task
- Add concurrency in follow-up task (BatchTransformMixin integration)
- Add response size limits and conversion timeout
- Document deployment and operational considerations
