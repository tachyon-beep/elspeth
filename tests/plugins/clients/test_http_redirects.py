"""Tests for redirect URL resolution and audit recording in _follow_redirects_safe().

Verifies that:
1. Relative redirects resolve against the original hostname URL, not the
   IP-based connection URL.
2. Each redirect hop is individually recorded in the audit trail as
   CallType.HTTP_REDIRECT with correct lineage data.
"""

from unittest.mock import Mock, patch

import httpx
import pytest

from elspeth.contracts import CallStatus, CallType
from elspeth.core.security.web import SSRFSafeRequest
from elspeth.plugins.clients.http import AuditedHTTPClient


@pytest.fixture
def http_client():
    """Create AuditedHTTPClient with mocked dependencies."""
    with patch("elspeth.plugins.clients.http.httpx.Client"):
        recorder = Mock()
        recorder.record_call = Mock()
        yield AuditedHTTPClient(
            recorder=recorder,
            state_id="test-state-001",
            run_id="test-run-001",
            telemetry_emit=Mock(),
            timeout=30.0,
        )


def _make_redirect_response(location: str, status_code: int = 301, url: str = "https://93.184.216.34:443/old-path") -> httpx.Response:
    """Create a redirect response with an IP-based URL (as httpx would see it)."""
    request = httpx.Request("GET", url)
    return httpx.Response(
        status_code=status_code,
        headers={"location": location},
        request=request,
    )


def _make_final_response(url: str = "https://93.184.216.34:443/final") -> httpx.Response:
    """Create a 200 OK response."""
    request = httpx.Request("GET", url)
    return httpx.Response(200, text="OK", request=request)


def _make_ssrf_request(url: str, ip: str = "93.184.216.34") -> SSRFSafeRequest:
    """Create an SSRFSafeRequest for the given URL."""
    parsed = httpx.URL(url)
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    path = str(parsed.raw_path, "ascii") if parsed.raw_path else "/"
    return SSRFSafeRequest(
        original_url=url,
        resolved_ip=ip,
        host_header=parsed.host,
        port=port,
        path=path,
        scheme=parsed.scheme,
    )


class TestRelativeRedirectResolution:
    """Relative redirects must resolve against hostname, not IP."""

    @patch("elspeth.plugins.clients.http.validate_url_for_ssrf")
    def test_relative_redirect_resolves_against_hostname(self, mock_validate, http_client):
        """Location: /new-path should produce https://example.com/new-path, not https://93.184.216.34/new-path."""
        redirect_response = _make_redirect_response("/new-path")
        final_response = _make_final_response()

        mock_validate.return_value = _make_ssrf_request("https://example.com/new-path")
        http_client._client.get.return_value = final_response

        result, count = http_client._follow_redirects_safe(
            response=redirect_response,
            max_redirects=5,
            timeout=10.0,
            original_headers={"User-Agent": "test"},
            original_url="https://example.com/old-path",
        )

        # validate_url_for_ssrf should receive hostname-based URL
        mock_validate.assert_called_once_with("https://example.com/new-path")
        assert result.status_code == 200
        assert count == 1

    @patch("elspeth.plugins.clients.http.validate_url_for_ssrf")
    def test_relative_redirect_preserves_scheme_and_host(self, mock_validate, http_client):
        """Relative redirect should preserve scheme and host from original URL."""
        redirect_response = _make_redirect_response("/api/v2/resource")
        final_response = _make_final_response()

        mock_validate.return_value = _make_ssrf_request("https://api.example.com/api/v2/resource")
        http_client._client.get.return_value = final_response

        http_client._follow_redirects_safe(
            response=redirect_response,
            max_redirects=5,
            timeout=10.0,
            original_headers={},
            original_url="https://api.example.com/api/v1/resource",
        )

        mock_validate.assert_called_once_with("https://api.example.com/api/v2/resource")


class TestAbsoluteRedirectResolution:
    """Absolute redirects carry their own hostname — should work regardless."""

    @patch("elspeth.plugins.clients.http.validate_url_for_ssrf")
    def test_absolute_redirect_to_different_host(self, mock_validate, http_client):
        """Location: https://other.com/page should use other.com, not original host."""
        redirect_response = _make_redirect_response("https://other.com/page")
        final_response = _make_final_response()

        mock_validate.return_value = _make_ssrf_request("https://other.com/page", ip="198.51.100.1")
        http_client._client.get.return_value = final_response

        http_client._follow_redirects_safe(
            response=redirect_response,
            max_redirects=5,
            timeout=10.0,
            original_headers={},
            original_url="https://example.com/start",
        )

        mock_validate.assert_called_once_with("https://other.com/page")


class TestChainedRedirects:
    """Redirect chains must track hostname through each hop."""

    @patch("elspeth.plugins.clients.http.validate_url_for_ssrf")
    def test_chained_relative_redirects_track_hostname(self, mock_validate, http_client):
        """Relative -> relative should keep resolving against the logical hostname."""
        redirect1 = _make_redirect_response("/step2")
        redirect2 = _make_redirect_response("/step3", url="https://93.184.216.34:443/step2")
        final_response = _make_final_response()

        mock_validate.side_effect = [
            _make_ssrf_request("https://example.com/step2"),
            _make_ssrf_request("https://example.com/step3"),
        ]
        http_client._client.get.side_effect = [redirect2, final_response]

        result, count = http_client._follow_redirects_safe(
            response=redirect1,
            max_redirects=5,
            timeout=10.0,
            original_headers={},
            original_url="https://example.com/step1",
        )

        assert mock_validate.call_count == 2
        mock_validate.assert_any_call("https://example.com/step2")
        mock_validate.assert_any_call("https://example.com/step3")
        assert result.status_code == 200
        assert count == 2

    @patch("elspeth.plugins.clients.http.validate_url_for_ssrf")
    def test_absolute_redirect_updates_hostname_for_subsequent_relative(self, mock_validate, http_client):
        """Absolute redirect to new.com, then relative /page, should resolve as https://new.com/page."""
        redirect1 = _make_redirect_response("https://new.com/")
        redirect2 = _make_redirect_response("/page", url="https://203.0.113.1:443/")
        final_response = _make_final_response()

        mock_validate.side_effect = [
            _make_ssrf_request("https://new.com/", ip="203.0.113.1"),
            _make_ssrf_request("https://new.com/page", ip="203.0.113.1"),
        ]
        http_client._client.get.side_effect = [redirect2, final_response]

        result, count = http_client._follow_redirects_safe(
            response=redirect1,
            max_redirects=5,
            timeout=10.0,
            original_headers={},
            original_url="https://example.com/start",
        )

        assert mock_validate.call_count == 2
        mock_validate.assert_any_call("https://new.com/")
        mock_validate.assert_any_call("https://new.com/page")
        assert result.status_code == 200
        assert count == 2


class TestHostHeaderAndSNI:
    """Host header and SNI must use hostname from validate_url_for_ssrf, not IP."""

    @patch("elspeth.plugins.clients.http.validate_url_for_ssrf")
    def test_host_header_uses_hostname_not_ip(self, mock_validate, http_client):
        """Host header on redirect hop should be the hostname, not the resolved IP."""
        redirect_response = _make_redirect_response("/new-path")
        final_response = _make_final_response()

        ssrf_req = _make_ssrf_request("https://example.com/new-path")
        mock_validate.return_value = ssrf_req
        http_client._client.get.return_value = final_response

        http_client._follow_redirects_safe(
            response=redirect_response,
            max_redirects=5,
            timeout=10.0,
            original_headers={"User-Agent": "test", "Host": "should-be-overwritten"},
            original_url="https://example.com/old-path",
        )

        # Check the headers passed to client.get()
        call_kwargs = http_client._client.get.call_args
        headers = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers")
        assert headers["Host"] == "example.com"

    @patch("elspeth.plugins.clients.http.validate_url_for_ssrf")
    def test_sni_hostname_set_for_https_redirect(self, mock_validate, http_client):
        """TLS SNI should use the hostname from the redirect target, not IP."""
        redirect_response = _make_redirect_response("/secure-path")
        final_response = _make_final_response()

        ssrf_req = _make_ssrf_request("https://secure.example.com/secure-path")
        mock_validate.return_value = ssrf_req
        http_client._client.get.return_value = final_response

        http_client._follow_redirects_safe(
            response=redirect_response,
            max_redirects=5,
            timeout=10.0,
            original_headers={},
            original_url="https://secure.example.com/old-path",
        )

        call_kwargs = http_client._client.get.call_args
        extensions = call_kwargs.kwargs.get("extensions") or call_kwargs[1].get("extensions")
        assert extensions["sni_hostname"] == "secure.example.com"


class TestNonRedirectPassthrough:
    """Non-redirect responses should pass through unchanged."""

    def test_non_redirect_response_returned_as_is(self, http_client):
        """A 200 response should be returned without modification."""
        response = _make_final_response()

        result, count = http_client._follow_redirects_safe(
            response=response,
            max_redirects=5,
            timeout=10.0,
            original_headers={},
            original_url="https://example.com/page",
        )

        assert result is response
        assert result.status_code == 200
        assert count == 0


class TestRedirectAuditRecording:
    """Each redirect hop must be individually recorded in the audit trail."""

    @patch("elspeth.plugins.clients.http.validate_url_for_ssrf")
    def test_single_redirect_records_one_hop(self, mock_validate, http_client):
        """A single redirect should produce exactly one HTTP_REDIRECT record_call."""
        redirect_response = _make_redirect_response("/new-path")
        final_response = _make_final_response()

        mock_validate.return_value = _make_ssrf_request("https://example.com/new-path")
        http_client._client.get.return_value = final_response

        http_client._follow_redirects_safe(
            response=redirect_response,
            max_redirects=5,
            timeout=10.0,
            original_headers={"User-Agent": "test"},
            original_url="https://example.com/old-path",
        )

        recorder = http_client._recorder
        recorder.record_call.assert_called_once()
        kw = recorder.record_call.call_args.kwargs
        assert kw["call_type"] == CallType.HTTP_REDIRECT
        assert kw["status"] == CallStatus.SUCCESS
        assert kw["state_id"] == "test-state-001"
        assert kw["request_data"]["url"] == "https://example.com/new-path"
        assert kw["request_data"]["hop_number"] == 1
        assert kw["response_data"]["status_code"] == 200

    @patch("elspeth.plugins.clients.http.validate_url_for_ssrf")
    def test_chained_redirects_record_multiple_hops(self, mock_validate, http_client):
        """Two redirects should produce two HTTP_REDIRECT record_call invocations."""
        redirect1 = _make_redirect_response("/step2")
        redirect2 = _make_redirect_response("/step3", url="https://93.184.216.34:443/step2")
        final_response = _make_final_response()

        mock_validate.side_effect = [
            _make_ssrf_request("https://example.com/step2"),
            _make_ssrf_request("https://example.com/step3"),
        ]
        http_client._client.get.side_effect = [redirect2, final_response]

        http_client._follow_redirects_safe(
            response=redirect1,
            max_redirects=5,
            timeout=10.0,
            original_headers={},
            original_url="https://example.com/step1",
        )

        recorder = http_client._recorder
        assert recorder.record_call.call_count == 2

        # First hop
        kw1 = recorder.record_call.call_args_list[0].kwargs
        assert kw1["call_type"] == CallType.HTTP_REDIRECT
        assert kw1["request_data"]["hop_number"] == 1
        assert kw1["request_data"]["url"] == "https://example.com/step2"

        # Second hop
        kw2 = recorder.record_call.call_args_list[1].kwargs
        assert kw2["call_type"] == CallType.HTTP_REDIRECT
        assert kw2["request_data"]["hop_number"] == 2
        assert kw2["request_data"]["url"] == "https://example.com/step3"

    @patch("elspeth.plugins.clients.http.validate_url_for_ssrf")
    def test_hop_records_include_redirect_from(self, mock_validate, http_client):
        """redirect_from captures the URL we're redirecting FROM (lineage within chain)."""
        redirect_response = _make_redirect_response("https://other.com/page")
        final_response = _make_final_response()

        mock_validate.return_value = _make_ssrf_request("https://other.com/page", ip="198.51.100.1")
        http_client._client.get.return_value = final_response

        http_client._follow_redirects_safe(
            response=redirect_response,
            max_redirects=5,
            timeout=10.0,
            original_headers={},
            original_url="https://example.com/start",
        )

        kw = http_client._recorder.record_call.call_args.kwargs
        assert kw["request_data"]["redirect_from"] == "https://example.com/start"
        assert kw["request_data"]["url"] == "https://other.com/page"

    @patch("elspeth.plugins.clients.http.validate_url_for_ssrf")
    def test_hop_records_include_resolved_ip(self, mock_validate, http_client):
        """Each hop record must include the resolved IP from SSRF validation."""
        redirect_response = _make_redirect_response("/new-path")
        final_response = _make_final_response()

        mock_validate.return_value = _make_ssrf_request("https://example.com/new-path", ip="93.184.216.34")
        http_client._client.get.return_value = final_response

        http_client._follow_redirects_safe(
            response=redirect_response,
            max_redirects=5,
            timeout=10.0,
            original_headers={},
            original_url="https://example.com/old-path",
        )

        kw = http_client._recorder.record_call.call_args.kwargs
        assert kw["request_data"]["resolved_ip"] == "93.184.216.34"

    @patch("elspeth.plugins.clients.http.validate_url_for_ssrf")
    def test_hop_records_have_latency(self, mock_validate, http_client):
        """Each hop record must include latency_ms."""
        redirect_response = _make_redirect_response("/new-path")
        final_response = _make_final_response()

        mock_validate.return_value = _make_ssrf_request("https://example.com/new-path")
        http_client._client.get.return_value = final_response

        http_client._follow_redirects_safe(
            response=redirect_response,
            max_redirects=5,
            timeout=10.0,
            original_headers={},
            original_url="https://example.com/old-path",
        )

        kw = http_client._recorder.record_call.call_args.kwargs
        assert "latency_ms" in kw
        assert isinstance(kw["latency_ms"], float)
        assert kw["latency_ms"] >= 0

    def test_no_hop_recorded_when_no_redirects(self, http_client):
        """A non-redirect response should produce zero HTTP_REDIRECT records."""
        response = _make_final_response()

        http_client._follow_redirects_safe(
            response=response,
            max_redirects=5,
            timeout=10.0,
            original_headers={},
            original_url="https://example.com/page",
        )

        http_client._recorder.record_call.assert_not_called()
