# tests/core/security/test_web.py
"""Tests for web security infrastructure (SSRF prevention).

Tests for:
- URL scheme validation (block file://, ftp://, etc.)
- IP validation (block private IPs, cloud metadata endpoints)
- DNS resolution with timeout
"""

import pytest

from elspeth.core.security.web import SSRFBlockedError, validate_url_scheme


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
