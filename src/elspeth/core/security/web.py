# src/elspeth/core/security/web.py
"""Web security infrastructure for SSRF prevention and URL validation."""

import urllib.parse


class SSRFBlockedError(Exception):
    """URL validation failed due to security policy (SSRF prevention)."""

    pass


ALLOWED_SCHEMES = {"http", "https"}


def validate_url_scheme(url: str) -> None:
    """Validate URL scheme is in allowlist (http/https only).

    Args:
        url: URL to validate

    Raises:
        SSRFBlockedError: If scheme is not in allowlist
    """
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise SSRFBlockedError(f"Forbidden scheme: {parsed.scheme}")
