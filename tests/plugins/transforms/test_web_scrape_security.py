"""Security tests for WebScrapeTransform (SSRF prevention)."""

from typing import Any
from unittest.mock import Mock, patch

import httpx
import pytest
import respx

from elspeth.contracts import PipelineRow
from elspeth.contracts.schema_contract import FieldContract, SchemaContract
from elspeth.plugins.context import PluginContext
from elspeth.plugins.transforms.web_scrape import WebScrapeTransform


def _make_pipeline_row(data: dict[str, Any]) -> PipelineRow:
    """Create a PipelineRow with OBSERVED contract for testing."""
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
    result = transform.process(_make_pipeline_row({"url": "file:///etc/passwd"}), mock_ctx)

    assert result.status == "error"
    assert result.reason["error_type"] == "SSRFBlockedError"
    assert "file" in result.reason["error"].lower()


def test_ssrf_blocks_private_ip(transform, mock_ctx):
    """Private IPs should be blocked."""
    with patch("socket.gethostbyname", return_value="192.168.1.1"):
        result = transform.process(_make_pipeline_row({"url": "https://internal.example.com"}), mock_ctx)

        assert result.status == "error"
        assert result.reason["error_type"] == "SSRFBlockedError"


def test_ssrf_blocks_loopback(transform, mock_ctx):
    """Loopback IPs should be blocked."""
    with patch("socket.gethostbyname", return_value="127.0.0.1"):
        result = transform.process(_make_pipeline_row({"url": "http://localhost/admin"}), mock_ctx)

        assert result.status == "error"
        assert result.reason["error_type"] == "SSRFBlockedError"


def test_ssrf_blocks_cloud_metadata(transform, mock_ctx):
    """Cloud metadata endpoints should be blocked."""
    with patch("socket.gethostbyname", return_value="169.254.169.254"):
        result = transform.process(
            _make_pipeline_row({"url": "http://metadata.google.internal/computeMetadata/v1/"}),
            mock_ctx,
        )

        assert result.status == "error"
        assert result.reason["error_type"] == "SSRFBlockedError"


@respx.mock
def test_ssrf_allows_public_ip(transform, mock_ctx):
    """Public IPs should be allowed."""
    respx.get("https://example.com/page").mock(return_value=httpx.Response(200, text="<html>Content</html>"))

    with patch("socket.gethostbyname", return_value="8.8.8.8"):
        result = transform.process(_make_pipeline_row({"url": "https://example.com/page"}), mock_ctx)

        assert result.status == "success"


# ============================================================================
# Contract Propagation Tests
# ============================================================================


@respx.mock
def test_contract_includes_output_fields(transform, mock_ctx):
    """Output contract must include content_field, fingerprint_field, and fetch_* fields.

    P2 bug: WebScrapeTransform returned success without contract, causing executor
    to build contract from output_schema (which is same as input_schema). New fields
    were not accessible under FIXED schema mode.
    """
    respx.get("https://example.com/page").mock(return_value=httpx.Response(200, text="<html>Content</html>"))

    with patch("socket.gethostbyname", return_value="8.8.8.8"):
        result = transform.process(_make_pipeline_row({"url": "https://example.com/page"}), mock_ctx)

        assert result.status == "success"
        # Contract MUST be provided so executor can use it
        assert result.contract is not None, "TransformResult must include contract for new fields"

        # Contract must include all output fields
        field_names = {f.normalized_name for f in result.contract.fields}

        # Input field should be preserved
        assert "url" in field_names

        # New fields from transform must be in contract
        assert "page_content" in field_names, "content_field must be in output contract"
        assert "page_fingerprint" in field_names, "fingerprint_field must be in output contract"
        assert "fetch_status" in field_names, "fetch_status must be in output contract"
        assert "fetch_url_final" in field_names, "fetch_url_final must be in output contract"
        assert "fetch_request_hash" in field_names, "fetch_request_hash must be in output contract"
        assert "fetch_response_raw_hash" in field_names, "fetch_response_raw_hash must be in output contract"
        assert "fetch_response_processed_hash" in field_names, "fetch_response_processed_hash must be in output contract"


@respx.mock
def test_contract_field_types_are_correct(transform, mock_ctx):
    """Output contract fields should have correct types inferred from values."""
    respx.get("https://example.com/page").mock(return_value=httpx.Response(200, text="<html>Content</html>"))

    with patch("socket.gethostbyname", return_value="8.8.8.8"):
        result = transform.process(_make_pipeline_row({"url": "https://example.com/page"}), mock_ctx)

        assert result.contract is not None

        # Get field contracts by name
        field_by_name = {f.normalized_name: f for f in result.contract.fields}

        # Check types
        assert field_by_name["page_content"].python_type is str
        assert field_by_name["page_fingerprint"].python_type is str
        assert field_by_name["fetch_status"].python_type is int
        assert field_by_name["fetch_url_final"].python_type is str
        assert field_by_name["fetch_request_hash"].python_type is str
        assert field_by_name["fetch_response_raw_hash"].python_type is str
        assert field_by_name["fetch_response_processed_hash"].python_type is str
