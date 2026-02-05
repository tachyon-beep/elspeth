"""Tests for WebScrapeTransform plugin."""

from typing import Any
from unittest.mock import Mock

import httpx
import pytest
import respx

from elspeth.contracts.schema_contract import FieldContract, PipelineRow, SchemaContract
from elspeth.plugins.context import PluginContext
from elspeth.plugins.transforms.web_scrape import WebScrapeTransform
from elspeth.plugins.transforms.web_scrape_errors import (
    NetworkError,
    RateLimitError,
    ServerError,
)


def _make_pipeline_row(data: dict[str, Any]) -> PipelineRow:
    """Create a PipelineRow with OBSERVED schema for testing."""
    fields = tuple(
        FieldContract(
            normalized_name=key,
            original_name=key,
            python_type=object,
            required=False,
            source="inferred",
        )
        for key in data
    )
    contract = SchemaContract(mode="OBSERVED", fields=fields, locked=True)
    return PipelineRow(data, contract)


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

    result = transform.process(_make_pipeline_row({"url": "https://example.com/page"}), mock_ctx)

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

    result = transform.process(_make_pipeline_row({"url": "https://example.com/missing"}), mock_ctx)

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
        transform.process(_make_pipeline_row({"url": "https://example.com/error"}), mock_ctx)

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
        transform.process(_make_pipeline_row({"url": "https://example.com/throttled"}), mock_ctx)

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

    result = transform.process(_make_pipeline_row({"url": "ftp://example.com/file"}), mock_ctx)

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
    result = transform.process(_make_pipeline_row({"url": "http://169.254.169.254/metadata"}), mock_ctx)

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

    result = transform.process(_make_pipeline_row({"url": "https://example.com/page"}), mock_ctx)

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

    result = transform.process(_make_pipeline_row({"url": "https://example.com/page"}), mock_ctx)

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

    result = transform.process(_make_pipeline_row({"url": "https://example.com/page"}), mock_ctx)

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
        transform.process(_make_pipeline_row({"url": "https://example.com/slow"}), mock_ctx)

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
        transform.process(_make_pipeline_row({"url": "https://example.com/unreachable"}), mock_ctx)

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

    result = transform.process(_make_pipeline_row({"url": "https://example.com/forbidden"}), mock_ctx)

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

    result = transform.process(_make_pipeline_row({"url": "https://example.com/unauthorized"}), mock_ctx)

    assert result.status == "error"
    assert "UnauthorizedError" in result.reason["error_type"]
    assert "401" in result.reason["error"]


@respx.mock
def test_web_scrape_with_pipeline_row(mock_ctx):
    """Test that web_scrape works correctly with PipelineRow input."""
    from elspeth.contracts.schema_contract import FieldContract, PipelineRow, SchemaContract

    html_content = "<html><body><h1>Test</h1></body></html>"
    respx.get("https://example.com/test").mock(return_value=httpx.Response(200, text=html_content))

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
        FieldContract(
            normalized_name="url",
            original_name="url",
            python_type=str,
            required=True,
            source="declared",
        ),
    )
    contract = SchemaContract(mode="FIXED", fields=fields, locked=True)
    pipeline_row = PipelineRow({"url": "https://example.com/test"}, contract)

    # Process should work with PipelineRow (uses row.to_dict() internally)
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

    **Status:** This test documents desired behavior. httpx follows redirects
    by default, but testing this with respx mocking requires integration test setup.
    """
    # Set up redirect chain: /old -> /new
    respx.get("https://example.com/old").mock(return_value=httpx.Response(301, headers={"Location": "https://example.com/new"}))
    respx.get("https://example.com/new").mock(return_value=httpx.Response(200, text="<html><body><h1>New Location</h1></body></html>"))

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

    result = transform.process(_make_pipeline_row({"url": "https://example.com/old"}), mock_ctx)

    assert result.status == "success"
    assert "# New Location" in result.row["page_content"]
    assert result.row["fetch_status"] == 200
    assert result.row["fetch_url_final"] == "https://example.com/new"


@pytest.mark.xfail(reason="Redirect chain testing with respx requires integration test setup - documents desired behavior")
@respx.mock
def test_web_scrape_follows_redirect_chain(mock_ctx):
    """Multiple redirects (301->302->200) should be followed to final destination.

    Edge case: Redirect chains occur when multiple URL migrations happen over time
    or when CDNs/load balancers add intermediate redirects.

    **Status:** This test documents desired behavior. httpx follows redirect chains,
    but testing with respx mocking is complex and better suited for integration tests.
    """
    # Set up redirect chain: /start -> /middle -> /end
    respx.get("https://example.com/start").mock(return_value=httpx.Response(301, headers={"Location": "https://example.com/middle"}))
    respx.get("https://example.com/middle").mock(return_value=httpx.Response(302, headers={"Location": "https://example.com/end"}))
    respx.get("https://example.com/end").mock(return_value=httpx.Response(200, text="<html><body><h1>Final Destination</h1></body></html>"))

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

    result = transform.process(_make_pipeline_row({"url": "https://example.com/start"}), mock_ctx)

    assert result.status == "success"
    assert "# Final Destination" in result.row["page_content"]
    assert result.row["fetch_status"] == 200
    assert result.row["fetch_url_final"] == "https://example.com/end"


@pytest.mark.xfail(reason="Redirect loop testing with respx requires integration test setup - documents desired behavior")
@respx.mock
def test_web_scrape_redirect_limit_exceeded(mock_ctx):
    """Excessive redirects should fail with network error.

    Edge case: Redirect loops or very long redirect chains should be caught
    to prevent infinite loops and wasted resources.

    **Status:** This test documents desired behavior. httpx has redirect limits,
    but testing this with respx mocking is complex and better suited for integration tests.
    """
    # Set up circular redirect: /a -> /b -> /a (loop)
    respx.get("https://example.com/a").mock(return_value=httpx.Response(301, headers={"Location": "https://example.com/b"}))
    respx.get("https://example.com/b").mock(return_value=httpx.Response(301, headers={"Location": "https://example.com/a"}))

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

    # httpx has a default redirect limit of 20, circular redirects should hit it
    with pytest.raises(NetworkError, match=r"redirect|too many redirects"):
        transform.process(_make_pipeline_row({"url": "https://example.com/a"}), mock_ctx)


@respx.mock
def test_web_scrape_malformed_html_graceful_degradation(mock_ctx):
    """Malformed HTML should still extract text content without crashing.

    Edge case: Real-world HTML is often malformed (missing closing tags, invalid nesting).
    The scraper should handle this gracefully using BeautifulSoup's lenient parsing.
    """
    # Malformed HTML: unclosed tags, invalid nesting
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

    respx.get("https://example.com/malformed").mock(return_value=httpx.Response(200, text=malformed_html))

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

    result = transform.process(_make_pipeline_row({"url": "https://example.com/malformed"}), mock_ctx)

    # Should succeed despite malformed HTML
    assert result.status == "success"
    # Content should be extracted (BeautifulSoup auto-closes tags)
    assert "Title" in result.row["page_content"]
    assert "Paragraph without closing tag" in result.row["page_content"]
    assert "Nested paragraph" in result.row["page_content"]
    assert result.row["fetch_status"] == 200
