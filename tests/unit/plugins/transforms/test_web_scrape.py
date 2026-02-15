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
from elspeth.plugins.config_base import PluginConfigError
from elspeth.plugins.transforms.web_scrape import WebScrapeTransform
from elspeth.plugins.transforms.web_scrape_errors import (
    NetworkError,
    RateLimitError,
    ServerError,
)
from elspeth.testing import make_field, make_pipeline_row, make_row

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


def test_web_scrape_wires_on_success_and_on_error() -> None:
    """WebScrapeTransform routing is set via BaseTransform properties (bridge injection)."""
    transform = WebScrapeTransform(
        {
            "schema": {"mode": "observed"},
            "url_field": "url",
            "content_field": "page_content",
            "fingerprint_field": "page_fingerprint",
            "http": {
                "abuse_contact": "test@example.com",
                "scraping_reason": "Unit testing web scrape transform",
            },
        }
    )

    # Routing is injected by the instantiation bridge, not config
    assert transform.on_success is None
    assert transform.on_error is None

    # Verify bridge-style injection works
    transform.on_success = "output"
    transform.on_error = "errors"
    assert transform.on_success == "output"
    assert transform.on_error == "errors"


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
    fields = (make_field("url", str, original_name="url", required=True, source="declared"),)
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


@respx.mock
def test_web_scrape_extract_content_exception_returns_error(mock_ctx):
    """When extract_content() raises, process() returns TransformResult.error() instead of crashing.

    This is the Tier 3 boundary protection: response.text is external data and parsing it
    can fail in ways we can't predict. The pipeline must quarantine the row, not crash.
    """
    respx.get(f"https://{_TEST_IP}:443/bad").mock(return_value=httpx.Response(200, text="<html>valid</html>"))

    transform = WebScrapeTransform(
        {
            "schema": {"mode": "observed"},
            "url_field": "url",
            "content_field": "page_content",
            "fingerprint_field": "page_fingerprint",
            "format": "markdown",
            "http": {
                "abuse_contact": "test@example.com",
                "scraping_reason": "Testing parse error",
            },
        }
    )

    # Simulate extract_content() raising an unexpected exception
    with (
        patch("socket.getaddrinfo", _mock_getaddrinfo()),
        patch(
            "elspeth.plugins.transforms.web_scrape.extract_content",
            side_effect=RuntimeError("html2text internal error"),
        ),
    ):
        result = transform.process(make_pipeline_row({"url": "https://example.com/bad"}), mock_ctx)

    assert result.status == "error"
    assert result.reason["reason"] == "content_extraction_failed"
    assert "html2text internal error" in result.reason["error"]
    assert result.reason["error_type"] == "RuntimeError"
    assert result.reason["url"] == "https://example.com/bad"


@respx.mock
def test_web_scrape_binary_response_does_not_crash(mock_ctx):
    """Binary content in response.text should be handled gracefully.

    When a server returns binary data (image, PDF) with a text content-type,
    httpx will attempt UTF-8 decoding. If extraction fails on the result,
    we should get an error result, not a pipeline crash.
    """
    # Binary data that httpx will lossy-decode to replacement characters
    binary_content = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + b"\xff\xfe" * 100
    respx.get(f"https://{_TEST_IP}:443/binary").mock(
        return_value=httpx.Response(200, content=binary_content, headers={"content-type": "text/html"})
    )

    transform = WebScrapeTransform(
        {
            "schema": {"mode": "observed"},
            "url_field": "url",
            "content_field": "page_content",
            "fingerprint_field": "page_fingerprint",
            "format": "markdown",
            "http": {
                "abuse_contact": "test@example.com",
                "scraping_reason": "Testing binary response",
            },
        }
    )

    with patch("socket.getaddrinfo", _mock_getaddrinfo()):
        result = transform.process(make_pipeline_row({"url": "https://example.com/binary"}), mock_ctx)

    # Should either succeed (BeautifulSoup is very forgiving) or return error — never crash
    assert result.status in ("success", "error")


@respx.mock
def test_web_scrape_unicode_decode_error_returns_error(mock_ctx):
    """UnicodeDecodeError during extraction returns error result."""
    respx.get(f"https://{_TEST_IP}:443/encoding").mock(return_value=httpx.Response(200, text="<html>ok</html>"))

    transform = WebScrapeTransform(
        {
            "schema": {"mode": "observed"},
            "url_field": "url",
            "content_field": "page_content",
            "fingerprint_field": "page_fingerprint",
            "format": "markdown",
            "http": {
                "abuse_contact": "test@example.com",
                "scraping_reason": "Testing encoding error",
            },
        }
    )

    with (
        patch("socket.getaddrinfo", _mock_getaddrinfo()),
        patch(
            "elspeth.plugins.transforms.web_scrape.extract_content",
            side_effect=UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte"),
        ),
    ):
        result = transform.process(make_pipeline_row({"url": "https://example.com/encoding"}), mock_ctx)

    assert result.status == "error"
    assert result.reason["reason"] == "content_extraction_failed"
    assert result.reason["error_type"] == "UnicodeDecodeError"


# --- Config validation tests (WebScrapeHTTPConfig sub-model) ---


def _base_config(**overrides: Any) -> dict[str, Any]:
    """Build a valid WebScrapeTransform config dict, with overrides applied."""
    cfg: dict[str, Any] = {
        "schema": {"mode": "observed"},
        "url_field": "url",
        "content_field": "page_content",
        "fingerprint_field": "page_fingerprint",
        "http": {
            "abuse_contact": "test@example.com",
            "scraping_reason": "Testing",
        },
    }
    cfg.update(overrides)
    return cfg


def test_http_config_missing_abuse_contact_raises() -> None:
    """Missing required abuse_contact must raise PluginConfigError."""
    with pytest.raises(PluginConfigError, match="abuse_contact"):
        WebScrapeTransform(_base_config(http={"scraping_reason": "Testing"}))


def test_http_config_missing_scraping_reason_raises() -> None:
    """Missing required scraping_reason must raise PluginConfigError."""
    with pytest.raises(PluginConfigError, match="scraping_reason"):
        WebScrapeTransform(_base_config(http={"abuse_contact": "test@example.com"}))


def test_http_config_extra_field_raises() -> None:
    """Unknown fields in http config must be rejected (extra=forbid)."""
    with pytest.raises(PluginConfigError, match="extra_field"):
        WebScrapeTransform(
            _base_config(
                http={
                    "abuse_contact": "test@example.com",
                    "scraping_reason": "Testing",
                    "extra_field": "should fail",
                }
            )
        )


def test_http_config_timeout_zero_raises() -> None:
    """Timeout must be > 0."""
    with pytest.raises(PluginConfigError, match="timeout"):
        WebScrapeTransform(
            _base_config(
                http={
                    "abuse_contact": "test@example.com",
                    "scraping_reason": "Testing",
                    "timeout": 0,
                }
            )
        )


def test_http_config_timeout_negative_raises() -> None:
    """Negative timeout must be rejected."""
    with pytest.raises(PluginConfigError, match="timeout"):
        WebScrapeTransform(
            _base_config(
                http={
                    "abuse_contact": "test@example.com",
                    "scraping_reason": "Testing",
                    "timeout": -5,
                }
            )
        )


def test_http_config_timeout_default() -> None:
    """Timeout defaults to 30 when not specified."""
    transform = WebScrapeTransform(_base_config())
    assert transform._timeout == 30


def test_http_config_timeout_custom() -> None:
    """Custom timeout value is respected."""
    transform = WebScrapeTransform(
        _base_config(
            http={
                "abuse_contact": "test@example.com",
                "scraping_reason": "Testing",
                "timeout": 60,
            }
        )
    )
    assert transform._timeout == 60


class TestWebScrapeDeclaredOutputFields:
    """Tests for declared_output_fields — centralized collision detection support.

    Field collision detection is enforced centrally by TransformExecutor
    (see TestTransformExecutor in test_executors.py). These tests verify
    that WebScrapeTransform correctly declares its output fields so the
    executor can perform pre-execution collision checks.
    """

    def test_declared_output_fields_contains_hardcoded_fields(self):
        """declared_output_fields includes hardcoded fetch_* audit fields."""
        transform = WebScrapeTransform(
            {
                "schema": {"mode": "observed"},
                "url_field": "url",
                "content_field": "page_content",
                "fingerprint_field": "page_fingerprint",
                "http": {
                    "abuse_contact": "test@example.com",
                    "scraping_reason": "Testing declared fields",
                },
            }
        )

        assert "fetch_status" in transform.declared_output_fields
        assert "fetch_url_final" in transform.declared_output_fields
        assert "fetch_request_hash" in transform.declared_output_fields
        assert "fetch_response_raw_hash" in transform.declared_output_fields
        assert "fetch_response_processed_hash" in transform.declared_output_fields

    def test_declared_output_fields_contains_configurable_fields(self):
        """declared_output_fields includes configurable content and fingerprint fields."""
        transform = WebScrapeTransform(
            {
                "schema": {"mode": "observed"},
                "url_field": "url",
                "content_field": "page_content",
                "fingerprint_field": "page_fingerprint",
                "http": {
                    "abuse_contact": "test@example.com",
                    "scraping_reason": "Testing declared fields",
                },
            }
        )

        assert "page_content" in transform.declared_output_fields
        assert "page_fingerprint" in transform.declared_output_fields

    def test_declared_output_fields_adapts_to_config(self):
        """declared_output_fields changes when content/fingerprint field names change."""
        transform = WebScrapeTransform(
            {
                "schema": {"mode": "observed"},
                "url_field": "url",
                "content_field": "scraped_html",
                "fingerprint_field": "content_hash",
                "http": {
                    "abuse_contact": "test@example.com",
                    "scraping_reason": "Testing declared fields",
                },
            }
        )

        assert "scraped_html" in transform.declared_output_fields
        assert "content_hash" in transform.declared_output_fields
        # Old names should NOT be present
        assert "page_content" not in transform.declared_output_fields
        assert "page_fingerprint" not in transform.declared_output_fields

    def test_transforms_adds_fields_is_true(self):
        """transforms_adds_fields flag is set for schema evolution recording."""
        transform = WebScrapeTransform(
            {
                "schema": {"mode": "observed"},
                "url_field": "url",
                "content_field": "page_content",
                "fingerprint_field": "page_fingerprint",
                "http": {
                    "abuse_contact": "test@example.com",
                    "scraping_reason": "Testing declared fields",
                },
            }
        )

        assert transform.transforms_adds_fields is True
