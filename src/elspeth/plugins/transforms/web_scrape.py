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

import ipaddress
from ipaddress import IPv4Network, IPv6Network
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field, field_validator, model_validator

from elspeth.contracts import Determinism
from elspeth.contracts.contexts import LifecycleContext, TransformContext
from elspeth.contracts.contract_propagation import narrow_contract_to_output
from elspeth.contracts.schema_contract import PipelineRow
from elspeth.core.security.web import (
    NetworkError as SSRFNetworkError,
)
from elspeth.core.security.web import (
    SSRFBlockedError,
    SSRFSafeRequest,
    validate_url_for_ssrf,
)
from elspeth.plugins.infrastructure.base import BaseTransform
from elspeth.plugins.infrastructure.clients.http import AuditedHTTPClient
from elspeth.plugins.infrastructure.config_base import TransformDataConfig
from elspeth.plugins.infrastructure.results import TransformResult
from elspeth.plugins.infrastructure.schema_factory import create_schema_from_config
from elspeth.plugins.transforms.web_scrape_errors import (
    ForbiddenError,
    InvalidURLError,
    NetworkError,
    NotFoundError,
    RateLimitError,
    ServerError,
    UnauthorizedError,
    WebScrapeError,
)
from elspeth.plugins.transforms.web_scrape_extraction import extract_content
from elspeth.plugins.transforms.web_scrape_fingerprint import compute_fingerprint


class WebScrapeHTTPConfig(BaseModel):
    """HTTP client configuration for web scrape transform.

    Controls responsible scraping behavior: abuse contact for transparency,
    scraping reason for audit trail, and timeout for resource management.
    """

    model_config = {"extra": "forbid"}

    abuse_contact: str = Field(
        ...,
        description="Email for abuse reports (required for responsible scraping)",
    )
    scraping_reason: str = Field(
        ...,
        description="Why we're scraping (recorded in audit trail)",
    )
    timeout: int = Field(
        default=30,
        gt=0,
        description="Request timeout in seconds",
    )
    allowed_hosts: str | list[str] = Field(
        default="public_only",
        description="SSRF allowlist: 'public_only' (default), 'allow_private', or list of CIDR ranges",
    )

    @field_validator("abuse_contact", "scraping_reason")
    @classmethod
    def _reject_empty(cls, v: str, info: Any) -> str:
        if not v.strip():
            raise ValueError(f"{info.field_name} must not be empty")
        return v

    @field_validator("allowed_hosts")
    @classmethod
    def _validate_allowed_hosts(cls, v: str | list[str]) -> str | list[str]:
        if isinstance(v, str):
            if v not in ("public_only", "allow_private"):
                raise ValueError(f"allowed_hosts must be 'public_only', 'allow_private', or a list of CIDR ranges, got {v!r}")
            return v
        if not v:
            raise ValueError("allowed_hosts list must not be empty (use 'allow_private' to allow all)")
        for entry in v:
            try:
                ipaddress.ip_network(entry, strict=False)
            except ValueError as e:
                raise ValueError(f"Invalid CIDR in allowed_hosts: {entry!r}: {e}") from e
        return v


class WebScrapeConfig(TransformDataConfig):
    """Configuration for web scrape transform."""

    url_field: str
    content_field: str
    fingerprint_field: str
    format: Literal["markdown", "text", "raw"] = "markdown"
    fingerprint_mode: Literal["content", "full"] = "content"
    strip_elements: list[str] = Field(default_factory=lambda: ["script", "style"])
    http: WebScrapeHTTPConfig

    @field_validator("url_field", "content_field", "fingerprint_field")
    @classmethod
    def _reject_empty_field_names(cls, v: str, info: Any) -> str:
        if not v:
            raise ValueError(f"{info.field_name} must not be empty")
        return v

    @model_validator(mode="after")
    def _reject_field_collisions(self) -> "WebScrapeConfig":
        if self.content_field == self.fingerprint_field:
            raise ValueError(f"content_field and fingerprint_field must differ, both are '{self.content_field}'")
        return self


def _parse_allowed_ranges(entries: list[str]) -> tuple[IPv4Network | IPv6Network, ...]:
    """Parse allowed_hosts list entries into ip_network objects.

    Single IPs (no /) are expanded to /32 (IPv4) or /128 (IPv6).
    Uses strict=False so "10.0.0.1/8" is accepted as "10.0.0.0/8".
    """
    networks: list[IPv4Network | IPv6Network] = []
    for entry in entries:
        network = ipaddress.ip_network(entry, strict=False)
        networks.append(network)
    return tuple(networks)


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

        # Declare output fields for centralized collision detection in TransformExecutor.
        self.declared_output_fields = frozenset(
            [
                cfg.content_field,
                cfg.fingerprint_field,
                "fetch_status",
                "fetch_url_final",
                "fetch_url_final_ip",
                "fetch_request_hash",
                "fetch_response_raw_hash",
                "fetch_response_processed_hash",
            ]
        )

        # Format and fingerprint mode
        self._format = cfg.format
        self._fingerprint_mode = cfg.fingerprint_mode

        # HTTP config — validated by WebScrapeHTTPConfig sub-model
        self._abuse_contact = cfg.http.abuse_contact
        self._scraping_reason = cfg.http.scraping_reason
        self._timeout = cfg.http.timeout

        # Compute allowed_ranges from allowed_hosts config
        allowed_hosts = cfg.http.allowed_hosts
        if allowed_hosts == "public_only":
            self._allowed_ranges: tuple[IPv4Network | IPv6Network, ...] = ()
        elif allowed_hosts == "allow_private":
            self._allowed_ranges = (
                ipaddress.ip_network("0.0.0.0/0"),
                ipaddress.ip_network("::/0"),
            )
        else:
            assert isinstance(allowed_hosts, list), (
                f"Pydantic validator bug: allowed_hosts should be list[str], got {type(allowed_hosts).__name__}"
            )
            self._allowed_ranges = _parse_allowed_ranges(allowed_hosts)

        # Element stripping
        self._strip_elements = cfg.strip_elements

        # Schema
        if cfg.schema_config is None:
            raise RuntimeError("WebScrapeTransform requires schema_config")
        schema = create_schema_from_config(
            cfg.schema_config,
            "WebScrapeSchema",
            allow_coercion=False,
        )
        self.input_schema = schema
        self.output_schema = schema

    def on_start(self, ctx: LifecycleContext) -> None:
        """Capture infrastructure dependencies at pipeline start."""
        super().on_start(ctx)
        if ctx.landscape is None:
            raise RuntimeError("WebScrapeTransform requires landscape for audited HTTP calls")
        if ctx.rate_limit_registry is None:
            raise RuntimeError("WebScrapeTransform requires rate_limit_registry")
        self._recorder = ctx.landscape
        self._limiter = ctx.rate_limit_registry
        self._telemetry_emit = ctx.telemetry_emit
        self._payload_store = ctx.payload_store

    def process(self, row: PipelineRow, ctx: TransformContext) -> TransformResult:
        """Fetch URL and enrich row with content and fingerprint.

        Args:
            row: Input row (PipelineRow guaranteed by engine)
            ctx: Transform context with token, state_id, run_id

        Returns:
            TransformResult.success() with enriched row, or
            TransformResult.error() for non-retryable failures

        Raises:
            WebScrapeError: For retryable failures (5xx, 429, network)
                Engine RetryManager handles these with exponential backoff
        """
        url = row[self._url_field]

        # Validate URL and pin resolved IP (SSRF prevention with DNS rebinding defense)
        try:
            safe_request = validate_url_for_ssrf(url, allowed_ranges=self._allowed_ranges)
        except (SSRFBlockedError, SSRFNetworkError, TypeError) as e:
            # Security violations, DNS failures, and invalid url types (e.g. None)
            # are non-retryable
            return TransformResult.error(
                {
                    "reason": "validation_failed",
                    "error": str(e),
                    "error_type": type(e).__name__,
                }
            )

        # Fetch URL using pinned IP (prevents DNS rebinding between validation and fetch)
        try:
            response, final_hostname_url = self._fetch_url(safe_request, ctx)
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

        # Extract content — response.text is Tier 3 (external data), validate at boundary
        try:
            content = extract_content(
                response.text,
                format=self._format,
                strip_elements=self._strip_elements,
            )
        except (ValueError, UnicodeDecodeError, UnicodeEncodeError, RuntimeError) as e:
            return TransformResult.error(
                {
                    "reason": "content_extraction_failed",
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "url": safe_request.original_url,
                }
            )

        # Compute fingerprint
        fingerprint = compute_fingerprint(content, mode=self._fingerprint_mode)

        # Field collision check already done before fetch — no need to re-check here.

        # Store payloads for forensic recovery (captured in on_start)
        if self._payload_store is None:
            raise RuntimeError("WebScrapeTransform requires payload_store (not wired by executor)")
        request_hash = self._payload_store.store(f"GET {url}".encode())
        response_raw_hash = self._payload_store.store(response.content)
        response_processed_hash = self._payload_store.store(content.encode())

        # Enrich row with scraped data
        # Use explicit to_dict() conversion (PipelineRow guaranteed by engine)
        output = row.to_dict()
        output[self._content_field] = content
        output[self._fingerprint_field] = fingerprint
        output["fetch_status"] = response.status_code
        output["fetch_url_final"] = final_hostname_url
        output["fetch_url_final_ip"] = str(response.url)
        output["fetch_request_hash"] = request_hash
        output["fetch_response_raw_hash"] = response_raw_hash
        output["fetch_response_processed_hash"] = response_processed_hash

        # Propagate contract so FIXED schemas can access fields added during enrichment
        output_contract = narrow_contract_to_output(
            input_contract=row.contract,
            output_row=output,
        )

        return TransformResult.success(
            PipelineRow(output, output_contract),
            success_reason={
                "action": "enriched",
                "fields_added": [self._content_field, self._fingerprint_field],
            },
        )

    def _fetch_url(self, safe_request: SSRFSafeRequest, ctx: TransformContext) -> tuple[httpx.Response, str]:
        """Fetch URL using SSRF-safe IP pinning with audit recording.

        Args:
            safe_request: Pre-validated SSRFSafeRequest with pinned IP
            ctx: Plugin context

        Returns:
            Tuple of (httpx.Response, final hostname URL as string).
            The hostname URL is the logical URL after redirects — distinct
            from response.url which is IP-based due to SSRF pinning.

        Raises:
            WebScrapeError: For retryable or non-retryable failures
        """
        # Infrastructure captured in on_start()
        if ctx.state_id is None:
            raise RuntimeError("ctx.state_id not set by executor")
        limiter = self._limiter.get_limiter("web_scrape")

        # Create audited client (records to Landscape)
        client = AuditedHTTPClient(
            recorder=self._recorder,
            state_id=ctx.state_id,
            run_id=ctx.run_id,
            telemetry_emit=self._telemetry_emit,
            timeout=self._timeout,
            limiter=limiter,
            token_id=ctx.token.token_id if ctx.token is not None else None,
        )

        # Add responsible scraping headers
        headers = {
            "X-Abuse-Contact": self._abuse_contact,
            "X-Scraping-Reason": self._scraping_reason,
        }

        try:
            response, final_hostname_url = client.get_ssrf_safe(
                safe_request,
                headers=headers,
                follow_redirects=True,
                allowed_ranges=self._allowed_ranges,
            )

            # Check status code and raise appropriate errors
            url = safe_request.original_url
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
            elif 300 <= response.status_code < 400:
                # Unresolved redirect (e.g. 3xx without Location header) — treat as error
                raise InvalidURLError(f"Unresolved redirect HTTP {response.status_code}: {url} (missing or empty Location header)")

            return response, final_hostname_url

        except httpx.TimeoutException as e:
            raise NetworkError(f"Timeout fetching {safe_request.original_url}: {e}") from e
        except httpx.ConnectError as e:
            raise NetworkError(f"Connection error fetching {safe_request.original_url}: {e}") from e
        except SSRFBlockedError as e:
            # Redirect hop resolved to a blocked IP — non-retryable security violation
            from elspeth.plugins.transforms.web_scrape_errors import SSRFBlockedError as WSSRFBlockedError

            raise WSSRFBlockedError(f"SSRF blocked during redirect: {safe_request.original_url}: {e}") from e
        except SSRFNetworkError as e:
            # DNS resolution failed during redirect hop
            raise NetworkError(f"DNS resolution failed during redirect: {safe_request.original_url}: {e}") from e
        except httpx.TooManyRedirects as e:
            raise InvalidURLError(f"Too many redirects: {safe_request.original_url}: {e}") from e
        except httpx.RequestError as e:
            raise NetworkError(f"HTTP request error fetching {safe_request.original_url}: {e}") from e
        finally:
            client.close()

    def close(self) -> None:
        """Release resources."""
        pass
