# src/elspeth/core/security/web.py
"""Web security infrastructure for SSRF prevention and URL validation.

This module provides defense-in-depth against Server-Side Request Forgery (SSRF):

1. **Scheme validation**: Only HTTP/HTTPS allowed (blocks file://, ftp://, etc.)
2. **IP blocking**: Comprehensive blocklist covering private, loopback, metadata endpoints
3. **DNS rebinding prevention**: IP pinning via SSRFSafeRequest (resolve once, use that IP)

The key innovation is SSRFSafeRequest + validate_url_for_ssrf() which eliminates
the TOCTOU (Time-of-Check to Time-of-Use) vulnerability in traditional SSRF defenses:

    # VULNERABLE (old pattern - resolved twice, attacker can return different IPs):
    # validate then httpx.get(url) → second DNS lookup → 169.254.169.254

    # SECURE (resolved once, IP pinned for connection):
    safe_request = validate_url_for_ssrf(url)  # Resolves and validates
    httpx.get(safe_request.connection_url, headers={"Host": safe_request.host_header})
"""

from __future__ import annotations

import ipaddress
import queue
import socket
import threading
import urllib.parse
from dataclasses import dataclass


class SSRFBlockedError(Exception):
    """URL validation failed due to security policy (SSRF prevention)."""

    pass


class NetworkError(Exception):
    """Network operation failed (DNS, connection, etc.)."""

    pass


ALLOWED_SCHEMES = {"http", "https"}

# Comprehensive blocklist for SSRF prevention
# Each range blocks a specific attack vector - do not remove without security review
BLOCKED_IP_RANGES = [
    # IPv4 ranges
    ipaddress.ip_network("0.0.0.0/8"),  # Current network (RFC 1122) - can route to localhost
    ipaddress.ip_network("127.0.0.0/8"),  # Loopback
    ipaddress.ip_network("10.0.0.0/8"),  # Private Class A (RFC 1918)
    ipaddress.ip_network("172.16.0.0/12"),  # Private Class B (RFC 1918)
    ipaddress.ip_network("192.168.0.0/16"),  # Private Class C (RFC 1918)
    ipaddress.ip_network("169.254.0.0/16"),  # Link-local (AWS/Azure/GCP metadata endpoints)
    ipaddress.ip_network("100.64.0.0/10"),  # CGNAT (RFC 6598) - shared ISP space, often internal
    # IPv6 ranges
    ipaddress.ip_network("::1/128"),  # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),  # IPv6 unique local (RFC 4193) - private
    ipaddress.ip_network("fe80::/10"),  # IPv6 link-local (RFC 4291) - can reach metadata
    ipaddress.ip_network("::ffff:0:0/96"),  # IPv4-mapped IPv6 - CRITICAL: bypass vector!
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


def _resolve_hostname(hostname: str) -> list[str]:
    """Resolve hostname to all IP addresses (IPv4 + IPv6).

    Uses getaddrinfo() instead of gethostbyname() to support IPv6.

    Args:
        hostname: Hostname to resolve

    Returns:
        List of unique IP addresses (IPv4 and/or IPv6)

    Raises:
        NetworkError: If DNS resolution fails
    """
    try:
        # AF_UNSPEC = return both IPv4 and IPv6
        # SOCK_STREAM = TCP (filters out UDP-only results)
        results = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        # results[i] = (family, type, proto, canonname, sockaddr)
        # sockaddr = (ip, port) for IPv4 or (ip, port, flow, scope) for IPv6
        # sockaddr[0] is always the IP address string for both AF_INET and AF_INET6
        ips: set[str] = {str(r[4][0]) for r in results}
        return list(ips)
    except socket.gaierror as e:
        raise NetworkError(f"DNS resolution failed: {hostname}: {e}") from e


def _validate_ip_address(ip_str: str) -> None:
    """Validate that an IP address is not in any blocked range.

    Args:
        ip_str: IP address string (IPv4 or IPv6)

    Raises:
        SSRFBlockedError: If IP is in a blocked range or unparseable (fail-closed)
    """
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError as e:
        # Fail CLOSED: if we can't parse the IP (e.g. zone-scoped IPv6 like
        # "fe80::1%eth0"), block the request rather than allowing it through.
        raise SSRFBlockedError(f"Unparseable IP address: {ip_str!r}: {e}") from e
    for blocked in BLOCKED_IP_RANGES:
        if ip in blocked:
            raise SSRFBlockedError(f"Blocked IP range: {ip_str} in {blocked}")


@dataclass(frozen=True, slots=True)
class SSRFSafeRequest:
    """Request with pre-validated IP to prevent DNS rebinding attacks.

    This dataclass captures everything needed to make a request to a specific
    IP address while preserving the original hostname for Host header and TLS SNI.

    The key insight is that we resolve DNS once, validate the IP, then force the
    HTTP client to connect to that exact IP by rewriting the URL. The Host header
    ensures virtual hosting works, and SNI ensures TLS certificate verification.

    Attributes:
        original_url: The URL as provided by the user
        resolved_ip: The validated IP address we will connect to
        host_header: Original hostname for Host header (virtual hosting)
        port: Port number (explicit or default based on scheme)
        path: URL path including query string
        scheme: "http" or "https"

    Example:
        safe_request = validate_url_for_ssrf("https://example.com/path?q=1")
        # safe_request.connection_url = "https://93.184.216.34:443/path?q=1"
        # safe_request.host_header = "example.com"
        # safe_request.sni_hostname = "example.com"
    """

    original_url: str
    resolved_ip: str
    host_header: str
    port: int
    path: str
    scheme: str

    @property
    def connection_url(self) -> str:
        """URL with hostname replaced by resolved IP for direct connection.

        For IPv6 addresses, brackets are added per RFC 2732.
        """
        # IPv6 addresses need brackets in URLs
        ip_for_url = f"[{self.resolved_ip}]" if ":" in self.resolved_ip else self.resolved_ip
        return f"{self.scheme}://{ip_for_url}:{self.port}{self.path}"

    @property
    def sni_hostname(self) -> str:
        """Hostname for TLS SNI (Server Name Indication).

        Same as host_header - the original hostname for certificate verification.
        """
        return self.host_header


def validate_url_for_ssrf(url: str, timeout: float = 5.0) -> SSRFSafeRequest:
    """Validate URL and return request with pinned IP for SSRF-safe connection.

    This is the primary entry point for SSRF-safe HTTP requests. It:
    1. Validates the URL scheme (http/https only)
    2. Resolves DNS with timeout
    3. Validates ALL resolved IPs against blocklist
    4. Returns SSRFSafeRequest with pinned IP

    The returned SSRFSafeRequest should be used with get_ssrf_safe() or similar
    methods that connect directly to the resolved IP.

    Args:
        url: URL to validate and prepare for fetching
        timeout: DNS resolution timeout in seconds

    Returns:
        SSRFSafeRequest ready for secure fetching

    Raises:
        SSRFBlockedError: If scheme is forbidden or IP is blocked
        NetworkError: If DNS resolution fails or times out
    """
    # Step 1: Validate scheme
    validate_url_scheme(url)

    # Step 2: Parse URL components
    parsed = urllib.parse.urlparse(url)
    hostname = parsed.hostname
    if not hostname:
        raise SSRFBlockedError("URL has no hostname")

    # Determine port (explicit or default)
    # parsed.port can raise ValueError for out-of-range ports (e.g. 99999).
    # Port 0 is falsy but must be explicitly rejected (not a valid HTTP port).
    try:
        explicit_port = parsed.port
    except ValueError as e:
        raise SSRFBlockedError(f"Invalid port in URL: {e}") from e

    if explicit_port is not None:
        if explicit_port == 0:
            raise SSRFBlockedError("Port 0 is not allowed")
        port = explicit_port
    else:
        port = 443 if parsed.scheme.lower() == "https" else 80

    # Build path (including query string and fragment)
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    if parsed.fragment:
        path = f"{path}#{parsed.fragment}"

    # Step 3: Resolve DNS with timeout
    # Use a daemon thread instead of ThreadPoolExecutor. Daemon threads:
    # 1. Don't prevent process shutdown (unlike ThreadPoolExecutor workers)
    # 2. Are cleaned up automatically on process exit
    # 3. Don't accumulate on repeated timeouts (the OS resolver will
    #    eventually return and the daemon thread will exit naturally)
    result_queue: queue.Queue[tuple[str, list[str] | BaseException]] = queue.Queue()

    def _resolve_worker() -> None:
        try:
            result_queue.put(("ok", _resolve_hostname(hostname)))
        except BaseException as exc:
            result_queue.put(("error", exc))

    thread = threading.Thread(target=_resolve_worker, daemon=True, name="dns_resolve")
    thread.start()

    try:
        status, value = result_queue.get(timeout=timeout)
    except queue.Empty:
        raise NetworkError(f"DNS resolution timeout ({timeout}s): {hostname}") from None

    if status == "error":
        exc = value
        assert isinstance(exc, BaseException)
        if isinstance(exc, (SSRFBlockedError, NetworkError)):
            raise exc
        raise NetworkError(f"DNS resolution failed: {hostname}: {exc}") from exc

    ip_list: list[str] = value  # type: ignore[assignment]

    if not ip_list:
        raise NetworkError(f"DNS resolution returned no addresses: {hostname}")

    # Step 4: Validate ALL resolved IPs
    # Attacker could return a mix of safe and unsafe IPs - block if ANY is unsafe
    for ip_str in ip_list:
        _validate_ip_address(ip_str)

    # Select IP to use (prefer IPv4 for compatibility)
    ipv4_addrs = [ip for ip in ip_list if ":" not in ip]
    selected_ip = ipv4_addrs[0] if ipv4_addrs else ip_list[0]

    return SSRFSafeRequest(
        original_url=url,
        resolved_ip=selected_ip,
        host_header=hostname,
        port=port,
        path=path,
        scheme=parsed.scheme.lower(),
    )
