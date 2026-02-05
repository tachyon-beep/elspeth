"""Tests for WebScrapeTransform plugin."""

from unittest.mock import Mock

import httpx
import pytest
import respx

from elspeth.plugins.context import PluginContext
from elspeth.plugins.transforms.web_scrape import WebScrapeTransform
from elspeth.plugins.transforms.web_scrape_errors import (
    NetworkError,
    RateLimitError,
    ServerError,
)


@pytest.fixture
def mock_ctx(payload_store):
    """Create PluginContext with required attributes for web scraping."""
    # Mock landscape recorder
    landscape = Mock()

    # Mock rate limit registry
    rate_limit_registry = Mock()
    rate_limit_registry.get_limiter.return_value = None

    # Create context
    ctx = PluginContext(
        run_id="test-run-456",
        config={},
        landscape=landscape,
        rate_limit_registry=rate_limit_registry,
        payload_store=payload_store,
        state_id="state-123",
    )

    return ctx


@respx.mock
def test_web_scrape_success_markdown(mock_ctx):
    """Successful scrape should enrich row with content and fingerprint."""
    html_content = "<html><body><h1>Title</h1><p>Content here</p></body></html>"

    respx.get("https://example.com/page").mock(return_value=httpx.Response(200, text=html_content))

    transform = WebScrapeTransform(
        {
            "schema": {"mode": "observed"},
            "url_field": "url",
            "content_field": "page_content",
            "fingerprint_field": "page_fingerprint",
            "format": "markdown",
            "fingerprint_mode": "content",
            "http": {
                "abuse_contact": "test@example.com",
                "scraping_reason": "Unit testing web scrape transform",
            },
        }
    )

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
    respx.get("https://example.com/missing").mock(return_value=httpx.Response(404))

    transform = WebScrapeTransform(
        {
            "schema": {"mode": "observed"},
            "url_field": "url",
            "content_field": "page_content",
            "fingerprint_field": "page_fingerprint",
            "http": {
                "abuse_contact": "test@example.com",
                "scraping_reason": "Testing",
            },
        }
    )

    result = transform.process({"url": "https://example.com/missing"}, mock_ctx)

    assert result.status == "error"
    assert "NotFoundError" in result.reason["error_type"]
    assert "404" in result.reason["error"]


@respx.mock
def test_web_scrape_500_raises_for_retry(mock_ctx):
    """HTTP 500 should raise ServerError (retryable)."""
    respx.get("https://example.com/error").mock(return_value=httpx.Response(500))

    transform = WebScrapeTransform(
        {
            "schema": {"mode": "observed"},
            "url_field": "url",
            "content_field": "page_content",
            "fingerprint_field": "page_fingerprint",
            "http": {
                "abuse_contact": "test@example.com",
                "scraping_reason": "Testing",
            },
        }
    )

    with pytest.raises(ServerError) as exc_info:
        transform.process({"url": "https://example.com/error"}, mock_ctx)

    assert exc_info.value.retryable is True
    assert "500" in str(exc_info.value)


@respx.mock
def test_web_scrape_429_raises_for_retry(mock_ctx):
    """HTTP 429 should raise RateLimitError (retryable)."""
    respx.get("https://example.com/throttled").mock(return_value=httpx.Response(429))

    transform = WebScrapeTransform(
        {
            "schema": {"mode": "observed"},
            "url_field": "url",
            "content_field": "page_content",
            "fingerprint_field": "page_fingerprint",
            "http": {
                "abuse_contact": "test@example.com",
                "scraping_reason": "Testing",
            },
        }
    )

    with pytest.raises(RateLimitError) as exc_info:
        transform.process({"url": "https://example.com/throttled"}, mock_ctx)

    assert exc_info.value.retryable is True
    assert "429" in str(exc_info.value)


def test_web_scrape_invalid_scheme_returns_error(mock_ctx):
    """Non-HTTP scheme should return error (security violation)."""
    transform = WebScrapeTransform(
        {
            "schema": {"mode": "observed"},
            "url_field": "url",
            "content_field": "page_content",
            "fingerprint_field": "page_fingerprint",
            "http": {
                "abuse_contact": "test@example.com",
                "scraping_reason": "Testing",
            },
        }
    )

    result = transform.process({"url": "file:///etc/passwd"}, mock_ctx)

    assert result.status == "error"
    assert "SSRFBlockedError" in result.reason["error_type"]
    assert "scheme" in result.reason["error"].lower()


def test_web_scrape_private_ip_returns_error(mock_ctx):
    """Private IP should return error (SSRF prevention)."""
    transform = WebScrapeTransform(
        {
            "schema": {"mode": "observed"},
            "url_field": "url",
            "content_field": "page_content",
            "fingerprint_field": "page_fingerprint",
            "http": {
                "abuse_contact": "test@example.com",
                "scraping_reason": "Testing",
            },
        }
    )

    # Use http://localhost which should be blocked after hostname resolution
    result = transform.process({"url": "http://127.0.0.1/admin"}, mock_ctx)

    assert result.status == "error"
    assert "SSRFBlockedError" in result.reason["error_type"]


@respx.mock
def test_web_scrape_text_format(mock_ctx):
    """Test text extraction format."""
    html_content = "<html><body><h1>Title</h1><p>Content here</p></body></html>"

    respx.get("https://example.com/page").mock(return_value=httpx.Response(200, text=html_content))

    transform = WebScrapeTransform(
        {
            "schema": {"mode": "observed"},
            "url_field": "url",
            "content_field": "page_content",
            "fingerprint_field": "page_fingerprint",
            "format": "text",
            "http": {
                "abuse_contact": "test@example.com",
                "scraping_reason": "Testing",
            },
        }
    )

    result = transform.process({"url": "https://example.com/page"}, mock_ctx)

    assert result.status == "success"
    # Text format should not include markdown
    assert "#" not in result.row["page_content"]
    assert "Title" in result.row["page_content"]
    assert "Content here" in result.row["page_content"]


@respx.mock
def test_web_scrape_strips_script_tags(mock_ctx):
    """Test that script tags are stripped by default."""
    html_content = """
    <html>
        <body>
            <h1>Title</h1>
            <script>alert('malicious');</script>
            <p>Content here</p>
        </body>
    </html>
    """

    respx.get("https://example.com/page").mock(return_value=httpx.Response(200, text=html_content))

    transform = WebScrapeTransform(
        {
            "schema": {"mode": "observed"},
            "url_field": "url",
            "content_field": "page_content",
            "fingerprint_field": "page_fingerprint",
            "format": "text",
            "http": {
                "abuse_contact": "test@example.com",
                "scraping_reason": "Testing",
            },
        }
    )

    result = transform.process({"url": "https://example.com/page"}, mock_ctx)

    assert result.status == "success"
    assert "alert" not in result.row["page_content"]
    assert "malicious" not in result.row["page_content"]
    assert "Title" in result.row["page_content"]


@respx.mock
def test_web_scrape_payload_storage(mock_ctx):
    """Test that payloads are stored in payload store."""
    html_content = "<html><body><h1>Title</h1></body></html>"

    respx.get("https://example.com/page").mock(return_value=httpx.Response(200, text=html_content))

    transform = WebScrapeTransform(
        {
            "schema": {"mode": "observed"},
            "url_field": "url",
            "content_field": "page_content",
            "fingerprint_field": "page_fingerprint",
            "http": {
                "abuse_contact": "test@example.com",
                "scraping_reason": "Testing",
            },
        }
    )

    result = transform.process({"url": "https://example.com/page"}, mock_ctx)

    assert result.status == "success"
    # Check payload hashes were stored and are valid SHA-256 hashes
    assert "fetch_request_hash" in result.row
    assert len(result.row["fetch_request_hash"]) == 64
    assert "fetch_response_raw_hash" in result.row
    assert len(result.row["fetch_response_raw_hash"]) == 64
    assert "fetch_response_processed_hash" in result.row
    assert len(result.row["fetch_response_processed_hash"]) == 64
    # Verify payloads can be retrieved
    assert mock_ctx.payload_store.exists(result.row["fetch_request_hash"])
    assert mock_ctx.payload_store.exists(result.row["fetch_response_raw_hash"])
    assert mock_ctx.payload_store.exists(result.row["fetch_response_processed_hash"])


@respx.mock
def test_web_scrape_timeout_raises_network_error(mock_ctx):
    """Timeout should raise NetworkError (retryable)."""
    # Mock timeout by raising httpx.TimeoutException
    respx.get("https://example.com/slow").mock(side_effect=httpx.TimeoutException("Connection timeout"))

    transform = WebScrapeTransform(
        {
            "schema": {"mode": "observed"},
            "url_field": "url",
            "content_field": "page_content",
            "fingerprint_field": "page_fingerprint",
            "http": {
                "abuse_contact": "test@example.com",
                "scraping_reason": "Testing",
                "timeout": 1,
            },
        }
    )

    with pytest.raises(NetworkError) as exc_info:
        transform.process({"url": "https://example.com/slow"}, mock_ctx)

    assert exc_info.value.retryable is True
    assert "timeout" in str(exc_info.value).lower()


@respx.mock
def test_web_scrape_connection_error_raises_network_error(mock_ctx):
    """Connection error should raise NetworkError (retryable)."""
    respx.get("https://example.com/unreachable").mock(side_effect=httpx.ConnectError("Connection refused"))

    transform = WebScrapeTransform(
        {
            "schema": {"mode": "observed"},
            "url_field": "url",
            "content_field": "page_content",
            "fingerprint_field": "page_fingerprint",
            "http": {
                "abuse_contact": "test@example.com",
                "scraping_reason": "Testing",
            },
        }
    )

    with pytest.raises(NetworkError) as exc_info:
        transform.process({"url": "https://example.com/unreachable"}, mock_ctx)

    assert exc_info.value.retryable is True
    assert "connection" in str(exc_info.value).lower()


@respx.mock
def test_web_scrape_403_returns_error(mock_ctx):
    """HTTP 403 should return error result (non-retryable)."""
    respx.get("https://example.com/forbidden").mock(return_value=httpx.Response(403))

    transform = WebScrapeTransform(
        {
            "schema": {"mode": "observed"},
            "url_field": "url",
            "content_field": "page_content",
            "fingerprint_field": "page_fingerprint",
            "http": {
                "abuse_contact": "test@example.com",
                "scraping_reason": "Testing",
            },
        }
    )

    result = transform.process({"url": "https://example.com/forbidden"}, mock_ctx)

    assert result.status == "error"
    assert "ForbiddenError" in result.reason["error_type"]
    assert "403" in result.reason["error"]


@respx.mock
def test_web_scrape_401_returns_error(mock_ctx):
    """HTTP 401 should return error result (non-retryable)."""
    respx.get("https://example.com/unauthorized").mock(return_value=httpx.Response(401))

    transform = WebScrapeTransform(
        {
            "schema": {"mode": "observed"},
            "url_field": "url",
            "content_field": "page_content",
            "fingerprint_field": "page_fingerprint",
            "http": {
                "abuse_contact": "test@example.com",
                "scraping_reason": "Testing",
            },
        }
    )

    result = transform.process({"url": "https://example.com/unauthorized"}, mock_ctx)

    assert result.status == "error"
    assert "UnauthorizedError" in result.reason["error_type"]
    assert "401" in result.reason["error"]
