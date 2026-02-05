"""Security tests for WebScrapeTransform (SSRF prevention)."""

from unittest.mock import Mock, patch

import httpx
import pytest
import respx

from elspeth.plugins.context import PluginContext
from elspeth.plugins.transforms.web_scrape import WebScrapeTransform


@pytest.fixture
def transform():
    return WebScrapeTransform(
        {
            "schema": {"mode": "observed"},
            "url_field": "url",
            "content_field": "page_content",
            "fingerprint_field": "page_fingerprint",
            "http": {
                "abuse_contact": "test@example.com",
                "scraping_reason": "Security testing",
            },
        }
    )


@pytest.fixture
def mock_ctx(payload_store):
    """Create PluginContext with required attributes for security testing."""
    landscape = Mock()
    rate_limit_registry = Mock()
    rate_limit_registry.get_limiter.return_value = None

    ctx = PluginContext(
        run_id="test-run-456",
        config={},
        landscape=landscape,
        rate_limit_registry=rate_limit_registry,
        payload_store=payload_store,
        state_id="state-123",
    )

    return ctx


def test_ssrf_blocks_file_scheme(transform, mock_ctx):
    """file:// URLs should be blocked."""
    result = transform.process({"url": "file:///etc/passwd"}, mock_ctx)

    assert result.status == "error"
    assert result.reason["error_type"] == "SSRFBlockedError"
    assert "file" in result.reason["error"].lower()


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
    respx.get("https://example.com/page").mock(return_value=httpx.Response(200, text="<html>Content</html>"))

    with patch("socket.gethostbyname", return_value="8.8.8.8"):
        result = transform.process({"url": "https://example.com/page"}, mock_ctx)

        assert result.status == "success"
