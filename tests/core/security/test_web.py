# tests/core/security/test_web.py
"""Tests for web security infrastructure (SSRF prevention).

Tests for:
- URL scheme validation (block file://, ftp://, etc.)
- IP validation via validate_url_for_ssrf() (block private IPs, cloud metadata)
- DNS resolution with timeout and IPv6 support
- SSRFSafeRequest IP pinning for DNS rebinding prevention
- Comprehensive IP blocklist coverage
"""

import re
import socket
import time
from typing import Any
from unittest.mock import patch

import pytest

from elspeth.core.security.web import (
    NetworkError,
    SSRFBlockedError,
    SSRFSafeRequest,
    _validate_ip_address,
    validate_url_for_ssrf,
    validate_url_scheme,
)


# Helper to create a mock getaddrinfo result for a given IP
def _mock_getaddrinfo(ip: str) -> Any:
    """Create a mock getaddrinfo that returns the given IP."""
    is_ipv6 = ":" in ip

    def _getaddrinfo(
        host: str,
        port: Any,
        family: int = 0,
        type: int = 0,
        proto: int = 0,
        flags: int = 0,
    ) -> list[tuple[Any, ...]]:
        if is_ipv6:
            return [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", (ip, 0, 0, 0))]
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0))]

    return _getaddrinfo


# ============================================================================
# URL Scheme Validation
# ============================================================================


def test_validate_url_scheme_allows_https() -> None:
    """HTTPS URLs should pass validation."""
    validate_url_scheme("https://example.com/page")


def test_validate_url_scheme_allows_http() -> None:
    """HTTP URLs should pass validation."""
    validate_url_scheme("http://example.com/page")


def test_validate_url_scheme_blocks_file() -> None:
    """File URLs should be blocked."""
    with pytest.raises(SSRFBlockedError, match="Forbidden scheme: file"):
        validate_url_scheme("file:///etc/passwd")


def test_validate_url_scheme_blocks_ftp() -> None:
    """FTP URLs should be blocked."""
    with pytest.raises(SSRFBlockedError, match="Forbidden scheme: ftp"):
        validate_url_scheme("ftp://example.com/file")


# ============================================================================
# validate_url_for_ssrf() - Public IP (should pass)
# ============================================================================


def test_validate_url_for_ssrf_allows_public_ip() -> None:
    """Public IPs should pass validation and return SSRFSafeRequest."""
    with patch("socket.getaddrinfo", _mock_getaddrinfo("93.184.216.34")):
        result = validate_url_for_ssrf("https://example.com/page")

    assert isinstance(result, SSRFSafeRequest)
    assert result.resolved_ip == "93.184.216.34"
    assert result.host_header == "example.com"
    assert result.scheme == "https"
    assert result.port == 443
    assert result.path == "/page"


def test_validate_url_for_ssrf_http_default_port() -> None:
    """HTTP URLs should default to port 80."""
    with patch("socket.getaddrinfo", _mock_getaddrinfo("93.184.216.34")):
        result = validate_url_for_ssrf("http://example.com/page")

    assert result.port == 80
    assert result.scheme == "http"


def test_validate_url_for_ssrf_preserves_query_string() -> None:
    """Query strings should be preserved in the path."""
    with patch("socket.getaddrinfo", _mock_getaddrinfo("93.184.216.34")):
        result = validate_url_for_ssrf("https://example.com/search?q=test&page=1")

    assert result.path == "/search?q=test&page=1"


# ============================================================================
# validate_url_for_ssrf() - Blocked IP ranges
# ============================================================================


def test_blocks_loopback() -> None:
    """Loopback IPs should be blocked."""
    with (
        patch("socket.getaddrinfo", _mock_getaddrinfo("127.0.0.1")),
        pytest.raises(SSRFBlockedError, match=re.escape("127.0.0.1")),
    ):
        validate_url_for_ssrf("http://localhost/admin")


def test_blocks_private_class_a() -> None:
    """Private Class A IPs should be blocked."""
    with (
        patch("socket.getaddrinfo", _mock_getaddrinfo("10.0.0.1")),
        pytest.raises(SSRFBlockedError, match=re.escape("10.0.0.1")),
    ):
        validate_url_for_ssrf("http://internal.example.com/api")


def test_blocks_private_class_b() -> None:
    """Private Class B IPs should be blocked."""
    with (
        patch("socket.getaddrinfo", _mock_getaddrinfo("172.16.5.1")),
        pytest.raises(SSRFBlockedError, match=re.escape("172.16.5.1")),
    ):
        validate_url_for_ssrf("http://internal.example.com/api")


def test_blocks_private_class_c() -> None:
    """Private Class C IPs should be blocked."""
    with (
        patch("socket.getaddrinfo", _mock_getaddrinfo("192.168.1.1")),
        pytest.raises(SSRFBlockedError, match=re.escape("192.168.1.1")),
    ):
        validate_url_for_ssrf("http://internal.example.com/api")


def test_blocks_cloud_metadata() -> None:
    """Cloud metadata IPs (169.254.x.x) should be blocked."""
    with (
        patch("socket.getaddrinfo", _mock_getaddrinfo("169.254.169.254")),
        pytest.raises(SSRFBlockedError, match=re.escape("169.254.169.254")),
    ):
        validate_url_for_ssrf("http://metadata.google.internal/computeMetadata/v1/")


def test_blocks_current_network() -> None:
    """0.0.0.0/8 (current network) should be blocked."""
    with (
        patch("socket.getaddrinfo", _mock_getaddrinfo("0.0.0.1")),
        pytest.raises(SSRFBlockedError, match=re.escape("0.0.0.1")),
    ):
        validate_url_for_ssrf("http://zero.example.com/")


def test_blocks_cgnat() -> None:
    """100.64.0.0/10 (CGNAT) should be blocked."""
    with (
        patch("socket.getaddrinfo", _mock_getaddrinfo("100.64.0.1")),
        pytest.raises(SSRFBlockedError, match=re.escape("100.64.0.1")),
    ):
        validate_url_for_ssrf("http://cgnat.example.com/")


def test_blocks_ipv6_loopback() -> None:
    """IPv6 loopback (::1) should be blocked."""
    with (
        patch("socket.getaddrinfo", _mock_getaddrinfo("::1")),
        pytest.raises(SSRFBlockedError, match=re.escape("::1")),
    ):
        validate_url_for_ssrf("http://localhost6.example.com/")


def test_blocks_ipv6_link_local() -> None:
    """IPv6 link-local (fe80::/10) should be blocked."""
    with (
        patch("socket.getaddrinfo", _mock_getaddrinfo("fe80::1")),
        pytest.raises(SSRFBlockedError, match=re.escape("fe80::1")),
    ):
        validate_url_for_ssrf("http://linklocal.example.com/")


def test_blocks_ipv6_unique_local() -> None:
    """IPv6 unique local (fc00::/7) should be blocked."""
    with (
        patch("socket.getaddrinfo", _mock_getaddrinfo("fd00::1")),
        pytest.raises(SSRFBlockedError, match=re.escape("fd00::1")),
    ):
        validate_url_for_ssrf("http://ula.example.com/")


def test_blocks_ipv4_mapped_ipv6() -> None:
    """IPv4-mapped IPv6 (::ffff:127.0.0.1) should be blocked.

    This is a critical bypass vector - an attacker could use the IPv4-mapped
    IPv6 format to bypass IPv4-only blocklists.
    """
    with (
        patch("socket.getaddrinfo", _mock_getaddrinfo("::ffff:127.0.0.1")),
        pytest.raises(SSRFBlockedError),
    ):
        validate_url_for_ssrf("http://bypass.example.com/")


# ============================================================================
# DNS resolution errors
# ============================================================================


def test_dns_timeout() -> None:
    """DNS resolution timeout should raise NetworkError."""

    def slow_dns(*args: Any, **kwargs: Any) -> list[tuple[Any, ...]]:
        time.sleep(10)
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 0))]

    with (
        patch("socket.getaddrinfo", side_effect=slow_dns),
        pytest.raises(NetworkError, match="DNS resolution timeout"),
    ):
        validate_url_for_ssrf("http://slow.example.com/", timeout=0.1)


def test_dns_failure() -> None:
    """DNS resolution failure should raise NetworkError."""
    with (
        patch("socket.getaddrinfo", side_effect=socket.gaierror("DNS failed")),
        pytest.raises(NetworkError, match="DNS resolution failed"),
    ):
        validate_url_for_ssrf("http://nonexistent.example.com/")


def test_no_hostname() -> None:
    """URL with no hostname should be blocked."""
    with pytest.raises(SSRFBlockedError, match="URL has no hostname"):
        validate_url_for_ssrf("http:///path")


# ============================================================================
# SSRFSafeRequest properties
# ============================================================================


def test_connection_url_ipv4() -> None:
    """connection_url should use resolved IP with port."""
    req = SSRFSafeRequest(
        original_url="https://example.com/path",
        resolved_ip="93.184.216.34",
        host_header="example.com",
        port=443,
        path="/path",
        scheme="https",
    )
    assert req.connection_url == "https://93.184.216.34:443/path"


def test_connection_url_ipv6() -> None:
    """connection_url should bracket IPv6 addresses per RFC 2732."""
    req = SSRFSafeRequest(
        original_url="http://example.com/path",
        resolved_ip="2606:2800:220:1:248:1893:25c8:1946",
        host_header="example.com",
        port=80,
        path="/path",
        scheme="http",
    )
    assert req.connection_url == "http://[2606:2800:220:1:248:1893:25c8:1946]:80/path"


def test_sni_hostname() -> None:
    """sni_hostname should return the original hostname for TLS."""
    req = SSRFSafeRequest(
        original_url="https://example.com/",
        resolved_ip="93.184.216.34",
        host_header="example.com",
        port=443,
        path="/",
        scheme="https",
    )
    assert req.sni_hostname == "example.com"


# ============================================================================
# _validate_ip_address (internal helper, tested directly for coverage)
# ============================================================================


def test_validate_ip_address_allows_public() -> None:
    """Public IP should not raise."""
    _validate_ip_address("8.8.8.8")


def test_validate_ip_address_blocks_private() -> None:
    """Private IP should raise."""
    with pytest.raises(SSRFBlockedError):
        _validate_ip_address("10.0.0.1")


# ============================================================================
# IPv6 resolution support
# ============================================================================


def test_resolve_returns_ipv6() -> None:
    """getaddrinfo with IPv6 result should be handled correctly."""
    ipv6_addr = "2606:2800:220:1:248:1893:25c8:1946"
    with patch("socket.getaddrinfo", _mock_getaddrinfo(ipv6_addr)):
        result = validate_url_for_ssrf("http://example.com/")

    assert result.resolved_ip == ipv6_addr


def test_prefers_ipv4_when_both_available() -> None:
    """When both IPv4 and IPv6 are available, prefer IPv4."""

    def _both(*args: Any, **kwargs: Any) -> list[tuple[Any, ...]]:
        return [
            (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2606:2800:220:1:248:1893:25c8:1946", 0, 0, 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0)),
        ]

    with patch("socket.getaddrinfo", _both):
        result = validate_url_for_ssrf("http://example.com/")

    assert result.resolved_ip == "93.184.216.34"
