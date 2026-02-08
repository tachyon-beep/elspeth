"""Tests for WebScrapeTransform plugin.

All tests mock socket.getaddrinfo so that validate_url_for_ssrf() produces a
known resolved IP, then mock respx to match the IP-based URL that
get_ssrf_safe() actually sends.
"""

import socket
from typing import Any
from unittest.mock import Mock, patch

import httpx
import pytest
import respx

from elspeth.contracts.plugin_context import PluginContext
from elspeth.contracts.schema_contract import SchemaContract
from elspeth.plugins.transforms.web_scrape import WebScrapeTransform
from elspeth.plugins.transforms.web_scrape_errors import (
    NetworkError,
    RateLimitError,
    ServerError,
)
from elspeth.testing import make_pipeline_row
from tests_v2.fixtures.factories import make_field, make_row

# Stable test IP used for all DNS resolution mocks
_TEST_IP = "104.18.27.120"


def _mock_getaddrinfo(ip: str = _TEST_IP) -> Any:
    """Create a mock getaddrinfo that returns the given IP."""

    def _getaddrinfo(
        host: str,
        port: Any,
        family: int = 0,
        type: int = 0,
        proto: int = 0,
        flags: int = 0,
    ) -> list[tuple[Any, ...]]:
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0))]

    return _getaddrinfo


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

    # Mock the IP-based URL that get_ssrf_safe() sends
    respx.get(f"https://{_TEST_IP}:443/page").mock(return_value=httpx.Response(200, text=html_content))

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

    with patch("socket.getaddrinfo", _mock_getaddrinfo()):
        result = transform.process(make_pipeline_row({"url": "https://example.com/page"}), mock_ctx)

    assert result.status == "success"
    assert "# Title" in result.row["page_content"]
    assert "Content here" in result.row["page_content"]
    assert result.row["page_fingerprint"] is not None
    assert len(result.row["page_fingerprint"]) == 64  # SHA-256
    assert result.row["fetch_status"] == 200


@respx.mock
def test_web_scrape_404_returns_error(mock_ctx):
    """404 should return error result (non-retryable)."""
    respx.get(f"https://{_TEST_IP}:443/missing").mock(return_value=httpx.Response(404))

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

    with patch("socket.getaddrinfo", _mock_getaddrinfo()):
        result = transform.process(make_pipeline_row({"url": "https://example.com/missing"}), mock_ctx)

    assert result.status == "error"
    assert "NotFoundError" in result.reason["error_type"]
    assert "404" in result.reason["error"]


@respx.mock
def test_web_scrape_500_raises_for_retry(mock_ctx):
    """HTTP 500 should raise ServerError (retryable)."""
    respx.get(f"https://{_TEST_IP}:443/error").mock(return_value=httpx.Response(500))

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

    with patch("socket.getaddrinfo", _mock_getaddrinfo()), pytest.raises(ServerError) as exc_info:
        transform.process(make_pipeline_row({"url": "https://example.com/error"}), mock_ctx)

    assert exc_info.value.retryable is True
    assert "500" in str(exc_info.value)


@respx.mock
def test_web_scrape_429_raises_for_retry(mock_ctx):
    """HTTP 429 should raise RateLimitError (retryable)."""
    respx.get(f"https://{_TEST_IP}:443/throttled").mock(return_value=httpx.Response(429))

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

    with patch("socket.getaddrinfo", _mock_getaddrinfo()), pytest.raises(RateLimitError) as exc_info:
        transform.process(make_pipeline_row({"url": "https://example.com/throttled"}), mock_ctx)

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

    result = transform.process(make_pipeline_row({"url": "ftp://example.com/file"}), mock_ctx)

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

    with patch("socket.getaddrinfo", _mock_getaddrinfo("169.254.169.254")):
        result = transform.process(make_pipeline_row({"url": "http://169.254.169.254/metadata"}), mock_ctx)

    assert result.status == "error"
    assert "SSRFBlockedError" in result.reason["error_type"]


@respx.mock
def test_web_scrape_text_format(mock_ctx):
    """Test text extraction format."""
    html_content = "<html><body><h1>Title</h1><p>Content here</p></body></html>"

    respx.get(f"https://{_TEST_IP}:443/page").mock(return_value=httpx.Response(200, text=html_content))

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

    with patch("socket.getaddrinfo", _mock_getaddrinfo()):
        result = transform.process(make_pipeline_row({"url": "https://example.com/page"}), mock_ctx)

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

    respx.get(f"https://{_TEST_IP}:443/page").mock(return_value=httpx.Response(200, text=html_content))

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

    with patch("socket.getaddrinfo", _mock_getaddrinfo()):
        result = transform.process(make_pipeline_row({"url": "https://example.com/page"}), mock_ctx)

    assert result.status == "success"
    assert "alert" not in result.row["page_content"]
    assert "malicious" not in result.row["page_content"]
    assert "Title" in result.row["page_content"]


@respx.mock
def test_web_scrape_payload_storage(mock_ctx):
    """Test that payloads are stored in payload store."""
    html_content = "<html><body><h1>Title</h1></body></html>"

    respx.get(f"https://{_TEST_IP}:443/page").mock(return_value=httpx.Response(200, text=html_content))

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

    with patch("socket.getaddrinfo", _mock_getaddrinfo()):
        result = transform.process(make_pipeline_row({"url": "https://example.com/page"}), mock_ctx)

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
    # Mock timeout by raising httpx.TimeoutException on the IP-based URL
    respx.get(f"https://{_TEST_IP}:443/slow").mock(side_effect=httpx.TimeoutException("Connection timeout"))

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

    with patch("socket.getaddrinfo", _mock_getaddrinfo()), pytest.raises(NetworkError) as exc_info:
        transform.process(make_pipeline_row({"url": "https://example.com/slow"}), mock_ctx)

    assert exc_info.value.retryable is True
    assert "timeout" in str(exc_info.value).lower()


@respx.mock
def test_web_scrape_connection_error_raises_network_error(mock_ctx):
    """Connection error should raise NetworkError (retryable)."""
    respx.get(f"https://{_TEST_IP}:443/unreachable").mock(side_effect=httpx.ConnectError("Connection refused"))

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

    with patch("socket.getaddrinfo", _mock_getaddrinfo()), pytest.raises(NetworkError) as exc_info:
        transform.process(make_pipeline_row({"url": "https://example.com/unreachable"}), mock_ctx)

    assert exc_info.value.retryable is True
    assert "connection" in str(exc_info.value).lower()


@respx.mock
def test_web_scrape_403_returns_error(mock_ctx):
    """HTTP 403 should return error result (non-retryable)."""
    respx.get(f"https://{_TEST_IP}:443/forbidden").mock(return_value=httpx.Response(403))

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

    with patch("socket.getaddrinfo", _mock_getaddrinfo()):
        result = transform.process(make_pipeline_row({"url": "https://example.com/forbidden"}), mock_ctx)

    assert result.status == "error"
    assert "ForbiddenError" in result.reason["error_type"]
    assert "403" in result.reason["error"]


@respx.mock
def test_web_scrape_401_returns_error(mock_ctx):
    """HTTP 401 should return error result (non-retryable)."""
    respx.get(f"https://{_TEST_IP}:443/unauthorized").mock(return_value=httpx.Response(401))

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

    with patch("socket.getaddrinfo", _mock_getaddrinfo()):
        result = transform.process(make_pipeline_row({"url": "https://example.com/unauthorized"}), mock_ctx)

    assert result.status == "error"
    assert "UnauthorizedError" in result.reason["error_type"]
    assert "401" in result.reason["error"]


@respx.mock
def test_web_scrape_with_pipeline_row(mock_ctx):
    """Test that web_scrape works correctly with PipelineRow input."""
    html_content = "<html><body><h1>Test</h1></body></html>"
    respx.get(f"https://{_TEST_IP}:443/test").mock(return_value=httpx.Response(200, text=html_content))

    transform = WebScrapeTransform(
        {
            "schema": {"mode": "observed"},
            "url_field": "url",
            "content_field": "page_content",
            "fingerprint_field": "page_fingerprint",
            "format": "markdown",
            "http": {
                "abuse_contact": "test@example.com",
                "scraping_reason": "Testing PipelineRow compatibility",
            },
        }
    )

    # Create PipelineRow input (simulates what engine passes to transforms)
    fields = (
        make_field("url", str, original_name="url", required=True, source="declared"),
    )
    contract = SchemaContract(mode="FIXED", fields=fields, locked=True)
    pipeline_row = make_row({"url": "https://example.com/test"}, contract=contract)

    # Process should work with PipelineRow (uses row.to_dict() internally)
    with patch("socket.getaddrinfo", _mock_getaddrinfo()):
        result = transform.process(pipeline_row, mock_ctx)

    assert result.status == "success"
    assert "# Test" in result.row["page_content"]
    assert result.row["page_fingerprint"] is not None
    assert result.row["fetch_status"] == 200


@pytest.mark.xfail(reason="Redirect testing with respx requires special httpx configuration - documents desired behavior")
@respx.mock
def test_web_scrape_follows_redirects_301(mock_ctx):
    """HTTP 301 redirect should be followed and final URL recorded.

    Edge case: 301 Moved Permanently redirects are common for URL migrations.
    The scraper should follow the redirect and record both the requested URL
    and the final URL after redirect resolution.

    **Status:** This test documents desired behavior. The redirect following now
    happens via _follow_redirects_safe() which re-validates each hop for SSRF.
    """
    respx.get(f"https://{_TEST_IP}:443/old").mock(return_value=httpx.Response(301, headers={"Location": "https://example.com/new"}))
    respx.get(f"https://{_TEST_IP}:443/new").mock(return_value=httpx.Response(200, text="<html><body><h1>New Location</h1></body></html>"))

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
                "scraping_reason": "Testing redirect handling",
            },
        }
    )

    with patch("socket.getaddrinfo", _mock_getaddrinfo()):
        result = transform.process(make_pipeline_row({"url": "https://example.com/old"}), mock_ctx)

    assert result.status == "success"
    assert "# New Location" in result.row["page_content"]
    assert result.row["fetch_status"] == 200
    assert result.row["fetch_url_final"] == "https://example.com/new"


@pytest.mark.xfail(reason="Redirect chain testing with respx requires integration test setup - documents desired behavior")
@respx.mock
def test_web_scrape_follows_redirect_chain(mock_ctx):
    """Multiple redirects (301->302->200) should be followed to final destination."""
    respx.get(f"https://{_TEST_IP}:443/start").mock(return_value=httpx.Response(301, headers={"Location": "https://example.com/middle"}))
    respx.get(f"https://{_TEST_IP}:443/middle").mock(return_value=httpx.Response(302, headers={"Location": "https://example.com/end"}))
    respx.get(f"https://{_TEST_IP}:443/end").mock(
        return_value=httpx.Response(200, text="<html><body><h1>Final Destination</h1></body></html>")
    )

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
                "scraping_reason": "Testing redirect chain",
            },
        }
    )

    with patch("socket.getaddrinfo", _mock_getaddrinfo()):
        result = transform.process(make_pipeline_row({"url": "https://example.com/start"}), mock_ctx)

    assert result.status == "success"
    assert "# Final Destination" in result.row["page_content"]
    assert result.row["fetch_status"] == 200
    assert result.row["fetch_url_final"] == "https://example.com/end"


@pytest.mark.xfail(reason="Redirect loop testing with respx requires integration test setup - documents desired behavior")
@respx.mock
def test_web_scrape_redirect_limit_exceeded(mock_ctx):
    """Excessive redirects should fail with network error."""
    respx.get(f"https://{_TEST_IP}:443/a").mock(return_value=httpx.Response(301, headers={"Location": "https://example.com/b"}))
    respx.get(f"https://{_TEST_IP}:443/b").mock(return_value=httpx.Response(301, headers={"Location": "https://example.com/a"}))

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
                "scraping_reason": "Testing redirect limit",
            },
        }
    )

    with patch("socket.getaddrinfo", _mock_getaddrinfo()), pytest.raises(NetworkError, match=r"redirect|too many redirects"):
        transform.process(make_pipeline_row({"url": "https://example.com/a"}), mock_ctx)


@respx.mock
def test_web_scrape_malformed_html_graceful_degradation(mock_ctx):
    """Malformed HTML should still extract text content without crashing."""
    malformed_html = """
    <html>
    <body>
        <h1>Title
        <p>Paragraph without closing tag
        <div>
            <p>Nested paragraph
        </div>
        <!-- Missing closing tags for body and html -->
    """

    respx.get(f"https://{_TEST_IP}:443/malformed").mock(return_value=httpx.Response(200, text=malformed_html))

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
                "scraping_reason": "Testing malformed HTML",
            },
        }
    )

    with patch("socket.getaddrinfo", _mock_getaddrinfo()):
        result = transform.process(make_pipeline_row({"url": "https://example.com/malformed"}), mock_ctx)

    # Should succeed despite malformed HTML
    assert result.status == "success"
    # Content should be extracted (BeautifulSoup auto-closes tags)
    assert "Title" in result.row["page_content"]
    assert "Paragraph without closing tag" in result.row["page_content"]
    assert "Nested paragraph" in result.row["page_content"]
    assert result.row["fetch_status"] == 200
