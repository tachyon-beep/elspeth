# tests/core/security/test_web.py
"""Tests for web security infrastructure (SSRF prevention).

Tests for:
- URL scheme validation (block file://, ftp://, etc.)
- IP validation (block private IPs, cloud metadata endpoints)
- DNS resolution with timeout
"""

import re
import socket
from unittest.mock import patch

import pytest

from elspeth.core.security.web import NetworkError, SSRFBlockedError, validate_ip, validate_url_scheme


def test_validate_url_scheme_allows_https() -> None:
    """HTTPS URLs should pass validation."""
    # Should not raise
    validate_url_scheme("https://example.com/page")


def test_validate_url_scheme_allows_http() -> None:
    """HTTP URLs should pass validation."""
    # Should not raise
    validate_url_scheme("http://example.com/page")


def test_validate_url_scheme_blocks_file() -> None:
    """File URLs should be blocked."""
    with pytest.raises(SSRFBlockedError, match="Forbidden scheme: file"):
        validate_url_scheme("file:///etc/passwd")


def test_validate_url_scheme_blocks_ftp() -> None:
    """FTP URLs should be blocked."""
    with pytest.raises(SSRFBlockedError, match="Forbidden scheme: ftp"):
        validate_url_scheme("ftp://example.com/file")


def test_validate_ip_allows_public_ip() -> None:
    """Public IPs should pass validation."""
    with patch("socket.gethostbyname", return_value="8.8.8.8"):
        ip = validate_ip("example.com")
        assert ip == "8.8.8.8"


def test_validate_ip_blocks_loopback() -> None:
    """Loopback IPs should be blocked."""
    with (
        patch("socket.gethostbyname", return_value="127.0.0.1"),
        pytest.raises(SSRFBlockedError, match=re.escape("Blocked IP range: 127.0.0.1")),
    ):
        validate_ip("localhost")


def test_validate_ip_blocks_private_class_a() -> None:
    """Private Class A IPs should be blocked."""
    with (
        patch("socket.gethostbyname", return_value="10.0.0.1"),
        pytest.raises(SSRFBlockedError, match=re.escape("Blocked IP range: 10.0.0.1")),
    ):
        validate_ip("internal.example.com")


def test_validate_ip_blocks_cloud_metadata() -> None:
    """Cloud metadata IPs should be blocked."""
    with (
        patch("socket.gethostbyname", return_value="169.254.169.254"),
        pytest.raises(SSRFBlockedError, match=re.escape("Blocked IP range: 169.254.169.254")),
    ):
        validate_ip("metadata.google.internal")


def test_validate_ip_dns_timeout() -> None:
    """DNS resolution timeout should raise NetworkError."""

    def slow_dns(hostname: str) -> str:
        import time

        time.sleep(10)
        return "8.8.8.8"

    with (
        patch("socket.gethostbyname", side_effect=slow_dns),
        pytest.raises(NetworkError, match="DNS resolution timeout"),
    ):
        validate_ip("slow.example.com", timeout=0.1)


def test_validate_ip_dns_failure() -> None:
    """DNS resolution failure should raise NetworkError."""
    with (
        patch("socket.gethostbyname", side_effect=socket.gaierror("DNS failed")),
        pytest.raises(NetworkError, match="DNS resolution failed"),
    ):
        validate_ip("nonexistent.example.com")
