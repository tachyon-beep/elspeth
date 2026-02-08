# tests/unit/contracts/transform_contracts/test_web_scrape_contract.py
"""Contract tests for WebScrapeTransform.

Note: WebScrapeTransform does NOT inherit BatchTransformMixin yet,
so we use TransformContractPropertyTestBase. This will change when
we add concurrency in a later task.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import Mock, patch

import pytest

from elspeth.contracts.plugin_context import PluginContext
from elspeth.plugins.transforms.web_scrape import WebScrapeTransform

from .test_transform_protocol import TransformContractPropertyTestBase

if TYPE_CHECKING:
    from elspeth.plugins.protocols import TransformProtocol


def _create_mock_http_response() -> Mock:
    """Create a mock HTTP response for testing."""
    response = Mock()
    response.status_code = 200
    response.content = b"<html><body>Test content</body></html>"
    response.text = "<html><body>Test content</body></html>"
    response.headers = {"content-type": "text/html"}
    response.raise_for_status = Mock()
    return response


class TestWebScrapeContract(TransformContractPropertyTestBase):
    """Verify WebScrapeTransform satisfies plugin contract."""

    @pytest.fixture(autouse=True)
    def mock_httpx(self):
        """Mock httpx.Client for all contract tests."""
        with patch("httpx.Client") as mock_client_class:
            mock_response = _create_mock_http_response()
            mock_client_instance = Mock()
            mock_client_instance.get.return_value = mock_response
            mock_client_instance.__enter__ = Mock(return_value=mock_client_instance)
            mock_client_instance.__exit__ = Mock(return_value=False)
            mock_client_class.return_value = mock_client_instance
            yield mock_client_class

    @pytest.fixture
    def transform(self) -> TransformProtocol:
        """Create a WebScrapeTransform instance with valid configuration."""
        return WebScrapeTransform(
            {
                "schema": {"mode": "observed"},
                "url_field": "url",
                "content_field": "page_content",
                "fingerprint_field": "page_fingerprint",
                "http": {
                    "abuse_contact": "test@example.com",
                    "scraping_reason": "Contract testing web scrape transform",
                },
            }
        )

    @pytest.fixture
    def valid_input(self) -> dict[str, Any]:
        """Provide a valid input row with a URL field."""
        return {"url": "https://example.com"}

    @pytest.fixture
    def ctx(self) -> PluginContext:
        """Provide a PluginContext with required dependencies for WebScrapeTransform."""
        # Create mock rate limiter
        mock_limiter = Mock()
        mock_limiter.try_acquire.return_value = True

        # Create mock rate limit registry
        mock_registry = Mock()
        mock_registry.get_limiter.return_value = mock_limiter

        # Create mock landscape recorder
        mock_landscape = Mock()
        mock_landscape.record_call = Mock()

        # Create mock payload store
        mock_payload_store = Mock()
        mock_payload_store.store.return_value = "mock-blob-id"

        return PluginContext(
            run_id="test-run-001",
            config={},
            node_id="test-transform",
            plugin_name="test",
            rate_limit_registry=mock_registry,
            landscape=mock_landscape,
            state_id="test-state-001",
            payload_store=mock_payload_store,
        )
