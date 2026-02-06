# src/elspeth/plugins/clients/http.py
"""Audited HTTP client with automatic call recording.

Provides SSRF-safe HTTP methods via get_ssrf_safe() which uses IP pinning
to prevent DNS rebinding attacks. See core/security/web.py for details.
"""

from __future__ import annotations

import base64
import json
import math
import os
import time
from datetime import UTC, datetime
from json import JSONDecodeError
from typing import TYPE_CHECKING, Any

import httpx
import structlog

from elspeth.contracts import CallStatus, CallType
from elspeth.core.canonical import stable_hash
from elspeth.core.security.web import (
    SSRFSafeRequest,
    validate_url_for_ssrf,
)
from elspeth.plugins.clients.base import AuditedClientBase, TelemetryEmitCallback
from elspeth.telemetry.events import ExternalCallCompleted

logger = structlog.get_logger(__name__)


def _contains_non_finite(obj: Any) -> bool:
    """Recursively check if object contains NaN or Infinity float values.

    This is a Tier 3 boundary check: external JSON may contain non-finite values
    (Python's json module accepts them), but canonicalization rejects them. We
    detect these at the HTTP boundary to record as parse failure rather than
    crashing during audit recording.

    Args:
        obj: Any JSON-parsed value (dict, list, or primitive)

    Returns:
        True if any float value is NaN or Infinity
    """
    if isinstance(obj, float):
        return math.isnan(obj) or math.isinf(obj)
    if isinstance(obj, dict):
        return any(_contains_non_finite(v) for v in obj.values())
    if isinstance(obj, list):
        return any(_contains_non_finite(v) for v in obj)
    return False


def _parse_json_strict(text: str) -> tuple[Any, str | None]:
    """Parse JSON with strict rejection of NaN/Infinity.

    Python's stdlib json module accepts non-finite values by default, but
    these cannot be canonicalized. This function parses and validates in
    one step at the Tier 3 boundary.

    Args:
        text: JSON string to parse

    Returns:
        Tuple of (parsed_value, error_message)
        - On success: (parsed_dict_or_list, None)
        - On failure: (None, error_message)
    """
    try:
        parsed = json.loads(text)
    except JSONDecodeError as e:
        return None, str(e)

    # Check for non-finite values that canonicalization would reject
    if _contains_non_finite(parsed):
        return None, "JSON contains non-finite values (NaN or Infinity)"

    return parsed, None


if TYPE_CHECKING:
    from elspeth.core.landscape.recorder import LandscapeRecorder


class AuditedHTTPClient(AuditedClientBase):
    """HTTP client that automatically records all calls to audit trail.

    Wraps httpx to ensure every HTTP call is recorded to the Landscape
    audit trail. Supports:
    - Automatic request/response recording
    - Auth header fingerprinting (HMAC fingerprint stored, not raw secrets)
    - Latency measurement
    - Error recording
    - Telemetry emission after successful audit recording
    - Rate limiting (when limiter provided)

    Example:
        client = AuditedHTTPClient(
            recorder=recorder,
            state_id=state_id,
            run_id=run_id,
            telemetry_emit=telemetry_emit,
            base_url="https://api.example.com",
            headers={"Authorization": "Bearer ..."},
            limiter=registry.get_limiter("api.example.com"),
        )

        response = client.post("/v1/process", json={"data": "value"})
        print(response.json())
    """

    def __init__(
        self,
        recorder: LandscapeRecorder,
        state_id: str,
        run_id: str,
        telemetry_emit: TelemetryEmitCallback,
        *,
        timeout: float = 30.0,
        base_url: str | None = None,
        headers: dict[str, str] | None = None,
        limiter: Any = None,  # RateLimiter | NoOpLimiter | None
    ) -> None:
        """Initialize audited HTTP client.

        Args:
            recorder: LandscapeRecorder for audit trail storage
            state_id: Node state ID to associate calls with
            run_id: Pipeline run ID for telemetry correlation
            telemetry_emit: Callback to emit telemetry events
            timeout: Request timeout in seconds (default: 30.0)
            base_url: Optional base URL to prepend to all requests
            headers: Default headers for all requests
            limiter: Optional rate limiter for throttling requests
        """
        super().__init__(recorder, state_id, run_id, telemetry_emit, limiter=limiter)
        self._timeout = timeout
        self._base_url = base_url
        self._default_headers = headers or {}

    # Headers that may contain secrets - fingerprinted in audit trail
    _SENSITIVE_REQUEST_HEADERS = frozenset({"authorization", "x-api-key", "api-key", "x-auth-token", "proxy-authorization"})
    _SENSITIVE_RESPONSE_HEADERS = frozenset({"set-cookie", "www-authenticate", "proxy-authenticate", "x-auth-token"})

    def _is_sensitive_header(self, header_name: str) -> bool:
        """Check if a header name indicates sensitive content.

        Args:
            header_name: Header name to check

        Returns:
            True if header likely contains secrets
        """
        lower_name = header_name.lower()
        return (
            lower_name in self._SENSITIVE_REQUEST_HEADERS
            or "auth" in lower_name
            or "key" in lower_name
            or "secret" in lower_name
            or "token" in lower_name
        )

    def _filter_request_headers(self, headers: dict[str, str]) -> dict[str, str]:
        """Fingerprint sensitive request headers for audit recording.

        Sensitive headers (auth, api keys, tokens) are replaced with HMAC
        fingerprints so that:
        1. Raw secrets are NEVER stored in the audit trail
        2. Different credentials produce different fingerprints
        3. Replay/verify can distinguish requests by credential identity

        In dev mode (ELSPETH_ALLOW_RAW_SECRETS=true), sensitive headers are
        removed entirely (no fingerprint key required).

        Args:
            headers: Full headers dict

        Returns:
            Headers dict with sensitive values fingerprinted (or removed in dev mode)
        """
        from elspeth.core.security import get_fingerprint_key, secret_fingerprint

        # Check if fingerprint key is available
        allow_raw = os.environ.get("ELSPETH_ALLOW_RAW_SECRETS", "").lower() == "true"

        try:
            get_fingerprint_key()
            have_key = True
        except ValueError:
            have_key = False

        result: dict[str, str] = {}

        for k, v in headers.items():
            if self._is_sensitive_header(k):
                if have_key:
                    # Fingerprint the sensitive value
                    fp = secret_fingerprint(v)
                    result[k] = f"<fingerprint:{fp}>"
                elif not allow_raw:
                    # No key and not dev mode - this shouldn't happen in production
                    # Remove header to avoid leaking secrets (fail-safe)
                    logger.warning(
                        "Sensitive header '%s' dropped: no fingerprint key available. "
                        "Set ELSPETH_FINGERPRINT_KEY or ELSPETH_ALLOW_RAW_SECRETS=true",
                        k,
                    )
                    # Don't include this header
                else:
                    # Dev mode: remove header (don't store secrets, don't require key)
                    pass
            else:
                # Non-sensitive header: include as-is
                result[k] = v

        return result

    def _filter_response_headers(self, headers: dict[str, str]) -> dict[str, str]:
        """Filter out sensitive response headers from audit recording.

        Response headers that may contain secrets (cookies, auth challenges)
        are not recorded.

        Args:
            headers: Full headers dict

        Returns:
            Headers dict with sensitive headers removed
        """
        return {
            k: v
            for k, v in headers.items()
            if k.lower() not in self._SENSITIVE_RESPONSE_HEADERS
            and "auth" not in k.lower()
            and "key" not in k.lower()
            and "secret" not in k.lower()
            and "token" not in k.lower()
        }

    def _extract_provider(self, url: str) -> str:
        """Extract provider (host) from URL for telemetry.

        SECURITY: This method MUST NOT leak credentials. URLs may contain
        embedded userinfo (e.g., https://user:pass@host/). We use hostname
        only, which strips the userinfo component per RFC 3986.

        Args:
            url: Full URL

        Returns:
            Host portion of URL (e.g., "api.example.com"), without credentials
        """
        from urllib.parse import urlparse

        parsed = urlparse(url)
        # SECURITY: Use hostname (not netloc) to avoid leaking credentials.
        # netloc = [userinfo@]host[:port], hostname = just the host
        return parsed.hostname or "unknown"

    def post(
        self,
        url: str,
        *,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> httpx.Response:
        """Make POST request with automatic audit recording.

        Args:
            url: URL path (appended to base_url if configured)
            json: JSON body to send (optional)
            headers: Additional headers for this request
            timeout: Request timeout in seconds (uses client default if None)

        Returns:
            httpx.Response object

        Raises:
            httpx.HTTPError: For network/HTTP errors
        """
        # Acquire rate limit permission before making external call
        self._acquire_rate_limit()

        call_index = self._next_call_index()

        # Properly join base_url and url, handling slash combinations
        if self._base_url:
            # Normalize: strip trailing slash from base, leading slash from path
            # Then join with exactly one slash
            base = self._base_url.rstrip("/")
            path = url.lstrip("/")
            full_url = f"{base}/{path}"
        else:
            full_url = url
        merged_headers = {**self._default_headers, **(headers or {})}
        effective_timeout = timeout if timeout is not None else self._timeout

        # Filter sensitive headers from recorded request
        request_data = {
            "method": "POST",
            "url": full_url,
            "json": json,
            "headers": self._filter_request_headers(merged_headers),
        }

        start = time.perf_counter()

        try:
            with httpx.Client(timeout=effective_timeout) as client:
                response = client.post(
                    full_url,
                    json=json,
                    headers=merged_headers,
                )

            latency_ms = (time.perf_counter() - start) * 1000

            # Build response data with full body for audit trail
            # Try JSON first, then text, then binary (no truncation - payload store handles size)
            response_body: Any = None
            content_type = response.headers.get("content-type", "")

            if "application/json" in content_type:
                # Parse JSON strictly at Tier 3 boundary - reject NaN/Infinity
                # that canonicalization cannot handle
                parsed, error = _parse_json_strict(response.text)
                if error is not None:
                    # JSON parse failed or contains non-canonicalizable values
                    # This is a Tier 3 boundary issue - external data doesn't match contract
                    # Record the failure explicitly for audit trail completeness
                    logger.warning(
                        "JSON parse failed despite Content-Type: application/json",
                        extra={
                            "url": full_url,
                            "status_code": response.status_code,
                            "body_preview": response.text[:200],
                            "error": error,
                        },
                    )
                    response_body = {
                        "_json_parse_failed": True,
                        "_error": error,
                        "_raw_text": response.text,
                    }
                else:
                    response_body = parsed
            else:
                # For non-JSON, detect text vs binary content
                # Text content types: text/*, application/xml, application/x-www-form-urlencoded
                is_text_content = content_type.startswith("text/") or "xml" in content_type or "form-urlencoded" in content_type

                if is_text_content:
                    # Store full text (payload store auto-persist handles large responses)
                    response_body = response.text
                else:
                    # Store binary content as base64 for JSON serialization
                    # This handles images, PDFs, and other binary formats
                    response_body = {"_binary": base64.b64encode(response.content).decode("ascii")}

            # Determine status based on HTTP response code
            # 2xx = SUCCESS, 4xx/5xx = ERROR (audit must reflect what application sees)
            is_success = 200 <= response.status_code < 300
            call_status = CallStatus.SUCCESS if is_success else CallStatus.ERROR

            response_data: dict[str, Any] = {
                "status_code": response.status_code,
                "headers": self._filter_response_headers(dict(response.headers)),
                "body_size": len(response.content),
                "body": response_body,
            }

            # For error responses, also include error details
            error_data: dict[str, Any] | None = None
            if not is_success:
                error_data = {
                    "type": "HTTPError",
                    "message": f"HTTP {response.status_code}",
                    "status_code": response.status_code,
                }

            self._recorder.record_call(
                state_id=self._state_id,
                call_index=call_index,
                call_type=CallType.HTTP,
                status=call_status,
                request_data=request_data,
                response_data=response_data,
                error=error_data,
                latency_ms=latency_ms,
            )

            # Telemetry emitted AFTER successful Landscape recording
            # Wrapped in try/except to prevent telemetry failures from corrupting audit trail
            try:
                self._telemetry_emit(
                    ExternalCallCompleted(
                        timestamp=datetime.now(UTC),
                        run_id=self._run_id,
                        call_type=CallType.HTTP,
                        provider=self._extract_provider(full_url),
                        status=call_status,
                        latency_ms=latency_ms,
                        state_id=self._state_id,  # Transform context
                        operation_id=None,  # Not in source/sink context
                        request_hash=stable_hash(request_data),
                        response_hash=stable_hash(response_data),
                        request_payload=request_data,  # Full request for observability
                        response_payload=response_data,  # Full response for observability
                        token_usage=None,  # HTTP calls don't have token usage
                    )
                )
            except Exception as tel_err:
                # Telemetry failure must not corrupt the successful call
                logger.warning(
                    "telemetry_emit_failed",
                    error=str(tel_err),
                    error_type=type(tel_err).__name__,
                    run_id=self._run_id,
                    state_id=self._state_id,
                    call_type="http",
                )

            return response

        except Exception as e:
            latency_ms = (time.perf_counter() - start) * 1000

            self._recorder.record_call(
                state_id=self._state_id,
                call_index=call_index,
                call_type=CallType.HTTP,
                status=CallStatus.ERROR,
                request_data=request_data,
                error={
                    "type": type(e).__name__,
                    "message": str(e),
                },
                latency_ms=latency_ms,
            )

            # Telemetry emitted AFTER successful Landscape recording (even for call errors)
            # Wrapped in try/except to prevent telemetry failures from corrupting error handling
            try:
                self._telemetry_emit(
                    ExternalCallCompleted(
                        timestamp=datetime.now(UTC),
                        run_id=self._run_id,
                        call_type=CallType.HTTP,
                        provider=self._extract_provider(full_url),
                        status=CallStatus.ERROR,
                        latency_ms=latency_ms,
                        state_id=self._state_id,  # Transform context
                        operation_id=None,  # Not in source/sink context
                        request_hash=stable_hash(request_data),
                        response_hash=None,  # No response on exception
                        request_payload=request_data,  # Full request for observability
                        response_payload=None,  # No response on exception
                        token_usage=None,
                    )
                )
            except Exception as tel_err:
                # Telemetry failure must not corrupt the error handling flow
                logger.warning(
                    "telemetry_emit_failed",
                    error=str(tel_err),
                    error_type=type(tel_err).__name__,
                    run_id=self._run_id,
                    state_id=self._state_id,
                    call_type="http",
                )

            raise

    def get(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, str | int | float] | None = None,
        timeout: float | None = None,
    ) -> httpx.Response:
        """Make GET request with automatic audit recording.

        Args:
            url: URL path (appended to base_url if configured)
            headers: Additional headers for this request
            params: Query parameters to append to URL
            timeout: Request timeout in seconds (uses client default if None)

        Returns:
            httpx.Response object

        Raises:
            httpx.HTTPError: For network/HTTP errors
        """
        # Acquire rate limit permission before making external call
        self._acquire_rate_limit()

        call_index = self._next_call_index()

        # Properly join base_url and url, handling slash combinations
        if self._base_url:
            # Normalize: strip trailing slash from base, leading slash from path
            # Then join with exactly one slash
            base = self._base_url.rstrip("/")
            path = url.lstrip("/")
            full_url = f"{base}/{path}"
        else:
            full_url = url
        merged_headers = {**self._default_headers, **(headers or {})}
        effective_timeout = timeout if timeout is not None else self._timeout

        # Filter sensitive headers from recorded request
        request_data = {
            "method": "GET",
            "url": full_url,
            "params": params,
            "headers": self._filter_request_headers(merged_headers),
        }

        start = time.perf_counter()

        try:
            with httpx.Client(timeout=effective_timeout) as client:
                response = client.get(
                    full_url,
                    params=params,
                    headers=merged_headers,
                )

            latency_ms = (time.perf_counter() - start) * 1000

            # Build response data with full body for audit trail
            # Try JSON first, then text, then binary (no truncation - payload store handles size)
            response_body: Any = None
            content_type = response.headers.get("content-type", "")

            if "application/json" in content_type:
                # Parse JSON strictly at Tier 3 boundary - reject NaN/Infinity
                # that canonicalization cannot handle
                parsed, error = _parse_json_strict(response.text)
                if error is not None:
                    # JSON parse failed or contains non-canonicalizable values
                    # This is a Tier 3 boundary issue - external data doesn't match contract
                    # Record the failure explicitly for audit trail completeness
                    logger.warning(
                        "JSON parse failed despite Content-Type: application/json",
                        extra={
                            "url": full_url,
                            "status_code": response.status_code,
                            "body_preview": response.text[:200],
                            "error": error,
                        },
                    )
                    response_body = {
                        "_json_parse_failed": True,
                        "_error": error,
                        "_raw_text": response.text,
                    }
                else:
                    response_body = parsed
            else:
                # For non-JSON, detect text vs binary content
                # Text content types: text/*, application/xml, application/x-www-form-urlencoded
                is_text_content = content_type.startswith("text/") or "xml" in content_type or "form-urlencoded" in content_type

                if is_text_content:
                    # Store full text (payload store auto-persist handles large responses)
                    response_body = response.text
                else:
                    # Store binary content as base64 for JSON serialization
                    # This handles images, PDFs, and other binary formats
                    response_body = {"_binary": base64.b64encode(response.content).decode("ascii")}

            # Determine status based on HTTP response code
            # 2xx = SUCCESS, 4xx/5xx = ERROR (audit must reflect what application sees)
            is_success = 200 <= response.status_code < 300
            call_status = CallStatus.SUCCESS if is_success else CallStatus.ERROR

            response_data: dict[str, Any] = {
                "status_code": response.status_code,
                "headers": self._filter_response_headers(dict(response.headers)),
                "body_size": len(response.content),
                "body": response_body,
            }

            # For error responses, also include error details
            error_data: dict[str, Any] | None = None
            if not is_success:
                error_data = {
                    "type": "HTTPError",
                    "message": f"HTTP {response.status_code}",
                    "status_code": response.status_code,
                }

            self._recorder.record_call(
                state_id=self._state_id,
                call_index=call_index,
                call_type=CallType.HTTP,
                status=call_status,
                request_data=request_data,
                response_data=response_data,
                error=error_data,
                latency_ms=latency_ms,
            )

            # Telemetry emitted AFTER successful Landscape recording
            # Wrapped in try/except to prevent telemetry failures from corrupting audit trail
            try:
                self._telemetry_emit(
                    ExternalCallCompleted(
                        timestamp=datetime.now(UTC),
                        run_id=self._run_id,
                        call_type=CallType.HTTP,
                        provider=self._extract_provider(full_url),
                        status=call_status,
                        latency_ms=latency_ms,
                        state_id=self._state_id,  # Transform context
                        operation_id=None,  # Not in source/sink context
                        request_hash=stable_hash(request_data),
                        response_hash=stable_hash(response_data),
                        request_payload=request_data,  # Full request for observability
                        response_payload=response_data,  # Full response for observability
                        token_usage=None,  # HTTP calls don't have token usage
                    )
                )
            except Exception as tel_err:
                # Telemetry failure must not corrupt the successful call
                logger.warning(
                    "telemetry_emit_failed",
                    error=str(tel_err),
                    error_type=type(tel_err).__name__,
                    run_id=self._run_id,
                    state_id=self._state_id,
                    call_type="http",
                )

            return response

        except Exception as e:
            latency_ms = (time.perf_counter() - start) * 1000

            self._recorder.record_call(
                state_id=self._state_id,
                call_index=call_index,
                call_type=CallType.HTTP,
                status=CallStatus.ERROR,
                request_data=request_data,
                error={
                    "type": type(e).__name__,
                    "message": str(e),
                },
                latency_ms=latency_ms,
            )

            # Telemetry emitted AFTER successful Landscape recording (even for call errors)
            # Wrapped in try/except to prevent telemetry failures from corrupting error handling
            try:
                self._telemetry_emit(
                    ExternalCallCompleted(
                        timestamp=datetime.now(UTC),
                        run_id=self._run_id,
                        call_type=CallType.HTTP,
                        provider=self._extract_provider(full_url),
                        status=CallStatus.ERROR,
                        latency_ms=latency_ms,
                        state_id=self._state_id,  # Transform context
                        operation_id=None,  # Not in source/sink context
                        request_hash=stable_hash(request_data),
                        response_hash=None,  # No response on exception
                        request_payload=request_data,  # Full request for observability
                        response_payload=None,  # No response on exception
                        token_usage=None,
                    )
                )
            except Exception as tel_err:
                # Telemetry failure must not corrupt the error handling flow
                logger.warning(
                    "telemetry_emit_failed",
                    error=str(tel_err),
                    error_type=type(tel_err).__name__,
                    run_id=self._run_id,
                    state_id=self._state_id,
                    call_type="http",
                )

            raise

    def get_ssrf_safe(
        self,
        request: SSRFSafeRequest,
        *,
        headers: dict[str, str] | None = None,
        follow_redirects: bool = False,
        max_redirects: int = 10,
    ) -> httpx.Response:
        """GET with SSRF-safe IP pinning and redirect validation.

        Connects to the pre-validated IP in the SSRFSafeRequest, setting the
        Host header and TLS SNI to the original hostname. Each redirect hop
        is independently validated against the SSRF blocklist.

        Args:
            request: SSRFSafeRequest from validate_url_for_ssrf()
            headers: Additional headers for this request
            follow_redirects: Whether to follow HTTP redirects (default: False)
            max_redirects: Maximum redirect hops when follow_redirects=True

        Returns:
            httpx.Response object

        Raises:
            httpx.HTTPError: For network/HTTP errors
            SSRFBlockedError: If redirect target resolves to blocked IP
        """
        self._acquire_rate_limit()

        call_index = self._next_call_index()

        merged_headers = {
            **self._default_headers,
            **(headers or {}),
            "Host": request.host_header,
        }

        connection_url = request.connection_url
        effective_timeout = self._timeout

        # TLS SNI: use original hostname for certificate verification
        extensions: dict[str, str] = {}
        if request.scheme == "https":
            extensions["sni_hostname"] = request.sni_hostname

        # Record original URL and resolved IP in audit trail
        request_data: dict[str, Any] = {
            "method": "GET",
            "url": request.original_url,
            "resolved_ip": request.resolved_ip,
            "headers": self._filter_request_headers(merged_headers),
        }

        start = time.perf_counter()

        try:
            with httpx.Client(
                timeout=effective_timeout,
                follow_redirects=False,
            ) as client:
                response = client.get(
                    connection_url,
                    headers=merged_headers,
                    extensions=extensions if extensions else None,
                )

            # Handle redirects with SSRF validation at each hop
            if follow_redirects:
                response = self._follow_redirects_safe(response, max_redirects, effective_timeout, merged_headers)

            latency_ms = (time.perf_counter() - start) * 1000

            response_body: Any = None
            content_type = response.headers.get("content-type", "")

            if "application/json" in content_type:
                parsed, error = _parse_json_strict(response.text)
                if error is not None:
                    logger.warning(
                        "JSON parse failed despite Content-Type: application/json",
                        extra={
                            "url": request.original_url,
                            "status_code": response.status_code,
                            "body_preview": response.text[:200],
                            "error": error,
                        },
                    )
                    response_body = {
                        "_json_parse_failed": True,
                        "_error": error,
                        "_raw_text": response.text,
                    }
                else:
                    response_body = parsed
            else:
                is_text_content = content_type.startswith("text/") or "xml" in content_type or "form-urlencoded" in content_type
                if is_text_content:
                    response_body = response.text
                else:
                    response_body = {"_binary": base64.b64encode(response.content).decode("ascii")}

            is_success = 200 <= response.status_code < 300
            call_status = CallStatus.SUCCESS if is_success else CallStatus.ERROR

            response_data: dict[str, Any] = {
                "status_code": response.status_code,
                "headers": self._filter_response_headers(dict(response.headers)),
                "body_size": len(response.content),
                "body": response_body,
            }

            error_data: dict[str, Any] | None = None
            if not is_success:
                error_data = {
                    "type": "HTTPError",
                    "message": f"HTTP {response.status_code}",
                    "status_code": response.status_code,
                }

            self._recorder.record_call(
                state_id=self._state_id,
                call_index=call_index,
                call_type=CallType.HTTP,
                status=call_status,
                request_data=request_data,
                response_data=response_data,
                error=error_data,
                latency_ms=latency_ms,
            )

            try:
                self._telemetry_emit(
                    ExternalCallCompleted(
                        timestamp=datetime.now(UTC),
                        run_id=self._run_id,
                        call_type=CallType.HTTP,
                        provider=request.host_header,
                        status=call_status,
                        latency_ms=latency_ms,
                        state_id=self._state_id,
                        operation_id=None,
                        request_hash=stable_hash(request_data),
                        response_hash=stable_hash(response_data),
                        request_payload=request_data,
                        response_payload=response_data,
                        token_usage=None,
                    )
                )
            except Exception as tel_err:
                logger.warning(
                    "telemetry_emit_failed",
                    error=str(tel_err),
                    error_type=type(tel_err).__name__,
                    run_id=self._run_id,
                    state_id=self._state_id,
                    call_type="http_ssrf_safe",
                )

            return response

        except Exception as e:
            latency_ms = (time.perf_counter() - start) * 1000

            self._recorder.record_call(
                state_id=self._state_id,
                call_index=call_index,
                call_type=CallType.HTTP,
                status=CallStatus.ERROR,
                request_data=request_data,
                error={
                    "type": type(e).__name__,
                    "message": str(e),
                },
                latency_ms=latency_ms,
            )

            try:
                self._telemetry_emit(
                    ExternalCallCompleted(
                        timestamp=datetime.now(UTC),
                        run_id=self._run_id,
                        call_type=CallType.HTTP,
                        provider=request.host_header,
                        status=CallStatus.ERROR,
                        latency_ms=latency_ms,
                        state_id=self._state_id,
                        operation_id=None,
                        request_hash=stable_hash(request_data),
                        response_hash=None,
                        request_payload=request_data,
                        response_payload=None,
                        token_usage=None,
                    )
                )
            except Exception as tel_err:
                logger.warning(
                    "telemetry_emit_failed",
                    error=str(tel_err),
                    error_type=type(tel_err).__name__,
                    run_id=self._run_id,
                    state_id=self._state_id,
                    call_type="http_ssrf_safe",
                )

            raise

    def _follow_redirects_safe(
        self,
        response: httpx.Response,
        max_redirects: int,
        timeout: float,
        original_headers: dict[str, str],
    ) -> httpx.Response:
        """Follow HTTP redirects with SSRF validation at each hop.

        Each redirect target is independently resolved and validated against
        the SSRF blocklist, preventing redirect-based SSRF attacks like:
        attacker.com -> 301 -> http://169.254.169.254/

        Args:
            response: Initial response (may be a redirect)
            max_redirects: Maximum number of redirect hops
            timeout: Request timeout for each hop
            original_headers: Headers from original request (minus Host, which is set per-hop)

        Returns:
            Final non-redirect response

        Raises:
            SSRFBlockedError: If any redirect target resolves to a blocked IP
            httpx.TooManyRedirects: If redirect chain exceeds max_redirects
        """
        redirects_followed = 0

        while response.is_redirect and redirects_followed < max_redirects:
            location = response.headers.get("location")
            if not location:
                break

            # Resolve relative URLs against the current URL
            redirect_url = str(response.url.join(location))

            # CRITICAL: Validate the redirect target for SSRF
            redirect_request = validate_url_for_ssrf(redirect_url)

            # Build headers for this hop (Host header for virtual hosting)
            hop_headers = {k: v for k, v in original_headers.items() if k.lower() != "host"}
            hop_headers["Host"] = redirect_request.host_header

            # TLS SNI for this hop
            extensions: dict[str, str] = {}
            if redirect_request.scheme == "https":
                extensions["sni_hostname"] = redirect_request.sni_hostname

            with httpx.Client(timeout=timeout, follow_redirects=False) as client:
                response = client.get(
                    redirect_request.connection_url,
                    headers=hop_headers,
                    extensions=extensions if extensions else None,
                )

            redirects_followed += 1

        if response.is_redirect and redirects_followed >= max_redirects:
            raise httpx.TooManyRedirects(
                f"Exceeded {max_redirects} redirects",
                request=response.request,
            )

        return response
