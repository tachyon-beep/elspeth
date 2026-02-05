"""Web scraping transform with audit trail integration.

Fetches webpages, extracts content, and generates fingerprints for change detection.
Designed for compliance monitoring use cases with full audit trail integration.

Security Features:
- SSRF prevention (blocks private IPs, cloud metadata)
- URL scheme validation (HTTP/HTTPS only)
- Configurable timeouts
- Rate limiting support

Audit Trail:
- Records all HTTP calls via AuditedHTTPClient
- Stores request, raw response, and processed content in PayloadStore
- Generates fingerprints for change detection
"""

from typing import Any

import httpx
from pydantic import Field

from elspeth.contracts import Determinism
from elspeth.core.security import validate_ip, validate_url_scheme
from elspeth.plugins.base import BaseTransform
from elspeth.plugins.clients.http import AuditedHTTPClient
from elspeth.plugins.config_base import TransformDataConfig
from elspeth.plugins.context import PluginContext
from elspeth.plugins.results import TransformResult
from elspeth.plugins.schema_factory import create_schema_from_config
from elspeth.plugins.transforms.web_scrape_errors import (
    ForbiddenError,
    NetworkError,
    NotFoundError,
    RateLimitError,
    ServerError,
    UnauthorizedError,
    WebScrapeError,
)
from elspeth.plugins.transforms.web_scrape_extraction import extract_content
from elspeth.plugins.transforms.web_scrape_fingerprint import compute_fingerprint


class WebScrapeConfig(TransformDataConfig):
    """Configuration for web scrape transform."""

    url_field: str
    content_field: str
    fingerprint_field: str
    format: str = "markdown"
    fingerprint_mode: str = "content"
    strip_elements: list[str] = Field(default_factory=lambda: ["script", "style"])
    http: dict[str, Any]


class WebScrapeTransform(BaseTransform):
    """Fetch webpages, extract content, generate fingerprints.

    Designed for compliance monitoring use cases. Features:
    - Security: SSRF prevention, URL validation
    - Audit: Full request/response recording
    - Extraction: HTML → Markdown, Text, or Raw
    - Fingerprinting: Change detection with normalization

    Configuration:
        url_field: Field containing URL to fetch
        content_field: Field to store extracted content
        fingerprint_field: Field to store content fingerprint
        format: Output format ("markdown", "text", "raw")
        fingerprint_mode: Fingerprinting mode ("content", "full")
        strip_elements: HTML tags to remove (default: ["script", "style"])
        http:
            abuse_contact: Email for abuse reports (required)
            scraping_reason: Why we're scraping (required)
            timeout: Request timeout in seconds (default: 30)

    Error Handling (follows LLM plugin pattern):
        - Retryable errors (5xx, 429, network): Re-raised for engine retry
        - Non-retryable errors (4xx, SSRF): Return TransformResult.error()

    Example:
        transforms:
          - plugin: web_scrape
            options:
              schema: {mode: observed}
              url_field: url
              content_field: page_content
              fingerprint_field: page_fingerprint
              format: markdown
              http:
                abuse_contact: compliance@example.com
                scraping_reason: Regulatory monitoring
    """

    name = "web_scrape"
    determinism = Determinism.EXTERNAL_CALL
    plugin_version = "1.0.0"

    def __init__(self, options: dict[str, Any]) -> None:
        super().__init__(options)

        # Parse and validate config
        cfg = WebScrapeConfig.from_dict(options)

        # Required fields
        self._url_field = cfg.url_field
        self._content_field = cfg.content_field
        self._fingerprint_field = cfg.fingerprint_field

        # Format and fingerprint mode
        self._format = cfg.format
        self._fingerprint_mode = cfg.fingerprint_mode

        # HTTP config
        http_config = cfg.http
        self._abuse_contact = http_config["abuse_contact"]
        self._scraping_reason = http_config["scraping_reason"]
        self._timeout = http_config.get("timeout", 30)

        # Element stripping
        self._strip_elements = cfg.strip_elements

        # Schema
        assert cfg.schema_config is not None
        schema = create_schema_from_config(
            cfg.schema_config,
            "WebScrapeSchema",
            allow_coercion=False,
        )
        self.input_schema = schema
        self.output_schema = schema

    def process(self, row: dict[str, Any] | Any, ctx: PluginContext) -> TransformResult:
        """Fetch URL and enrich row with content and fingerprint.

        Args:
            row: Input row containing URL field
            ctx: Plugin context with landscape, payload_store, etc.

        Returns:
            TransformResult.success() with enriched row, or
            TransformResult.error() for non-retryable failures

        Raises:
            WebScrapeError: For retryable failures (5xx, 429, network)
                Engine RetryManager handles these with exponential backoff
        """
        url = row[self._url_field]

        # Validate URL security (SSRF prevention)
        try:
            validate_url_scheme(url)
            parsed = httpx.URL(url)
            if parsed.host:
                validate_ip(parsed.host)
        except Exception as e:
            # Security violations are non-retryable
            return TransformResult.error(
                {
                    "reason": "validation_failed",
                    "error": str(e),
                    "error_type": type(e).__name__,
                }
            )

        # Fetch URL
        try:
            response = self._fetch_url(url, ctx)
        except WebScrapeError as e:
            if e.retryable:
                # Re-raise retryable errors for engine RetryManager
                raise
            # Non-retryable errors return error result
            return TransformResult.error(
                {
                    "reason": "api_error",
                    "error": str(e),
                    "error_type": type(e).__name__,
                }
            )

        # Extract content
        content = extract_content(
            response.text,
            format=self._format,
            strip_elements=self._strip_elements,
        )

        # Compute fingerprint
        fingerprint = compute_fingerprint(content, mode=self._fingerprint_mode)

        # Store payloads for forensic recovery
        # Context is guaranteed to have these - executor sets them
        assert ctx.payload_store is not None
        request_hash = ctx.payload_store.store(f"GET {url}".encode())
        response_raw_hash = ctx.payload_store.store(response.content)
        response_processed_hash = ctx.payload_store.store(content.encode())

        # Enrich row with scraped data
        # Use explicit to_dict() conversion (preferred pattern for PipelineRow)
        output = row.to_dict()
        output[self._content_field] = content
        output[self._fingerprint_field] = fingerprint
        output["fetch_status"] = response.status_code
        output["fetch_url_final"] = str(response.url)
        output["fetch_request_hash"] = request_hash
        output["fetch_response_raw_hash"] = response_raw_hash
        output["fetch_response_processed_hash"] = response_processed_hash

        return TransformResult.success(
            output,
            success_reason={
                "action": "enriched",
                "fields_added": [self._content_field, self._fingerprint_field],
            },
        )

    def _fetch_url(self, url: str, ctx: PluginContext) -> httpx.Response:
        """Fetch URL with audit recording.

        Args:
            url: URL to fetch
            ctx: Plugin context

        Returns:
            httpx.Response object

        Raises:
            WebScrapeError: For retryable or non-retryable failures
        """
        # Get rate limiter
        # Context is guaranteed to have these - executor sets them
        assert ctx.rate_limit_registry is not None
        assert ctx.landscape is not None
        assert ctx.state_id is not None
        limiter = ctx.rate_limit_registry.get_limiter("web_scrape")

        # Create audited client (records to Landscape)
        client = AuditedHTTPClient(
            recorder=ctx.landscape,
            state_id=ctx.state_id,
            run_id=ctx.run_id,
            telemetry_emit=ctx.telemetry_emit,
            timeout=self._timeout,
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
            # AuditedHTTPClient.get() already returns httpx.Response, but
            # we want to ensure we're working with the right type
            response = http_response

            # Check status code and raise appropriate errors
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
            raise NetworkError(f"Timeout fetching {url}: {e}") from e
        except httpx.ConnectError as e:
            raise NetworkError(f"Connection error fetching {url}: {e}") from e

    def close(self) -> None:
        """Release resources."""
        pass
