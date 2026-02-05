# src/elspeth/core/security/web.py
"""Web security infrastructure for SSRF prevention and URL validation."""

import ipaddress
import socket
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError


class SSRFBlockedError(Exception):
    """URL validation failed due to security policy (SSRF prevention)."""

    pass


class NetworkError(Exception):
    """Network operation failed (DNS, connection, etc.)."""

    pass


ALLOWED_SCHEMES = {"http", "https"}

# Private, loopback, and cloud metadata IP ranges
BLOCKED_IP_RANGES = [
    ipaddress.ip_network("127.0.0.0/8"),  # Loopback
    ipaddress.ip_network("10.0.0.0/8"),  # Private Class A
    ipaddress.ip_network("172.16.0.0/12"),  # Private Class B
    ipaddress.ip_network("192.168.0.0/16"),  # Private Class C
    ipaddress.ip_network("169.254.0.0/16"),  # Link-local (AWS/Azure/GCP metadata)
    ipaddress.ip_network("::1/128"),  # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),  # IPv6 private
]


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


def validate_ip(hostname: str, timeout: float = 5.0) -> str:
    """Resolve hostname with timeout and validate IP is not blocked.

    Args:
        hostname: Hostname to resolve
        timeout: DNS resolution timeout in seconds

    Returns:
        Resolved IP address as string

    Raises:
        NetworkError: If DNS resolution fails or times out
        SSRFBlockedError: If resolved IP is in blocked ranges
    """

    def _resolve() -> str:
        try:
            return socket.gethostbyname(hostname)
        except socket.gaierror as e:
            raise NetworkError(f"DNS resolution failed: {hostname}: {e}") from e

    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="dns_resolve") as executor:
        future = executor.submit(_resolve)
        try:
            ip_str = future.result(timeout=timeout)
        except FuturesTimeoutError as e:
            raise NetworkError(f"DNS resolution timeout ({timeout}s): {hostname}") from e

    ip = ipaddress.ip_address(ip_str)
    for blocked in BLOCKED_IP_RANGES:
        if ip in blocked:
            raise SSRFBlockedError(f"Blocked IP range: {ip_str} in {blocked}")

    return ip_str
