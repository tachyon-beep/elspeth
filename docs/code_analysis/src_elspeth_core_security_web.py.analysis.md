# Analysis: src/elspeth/core/security/web.py

**Lines:** 84
**Role:** Web security infrastructure for SSRF prevention. Provides URL scheme validation and IP address validation (DNS resolution with timeout + blocked IP range checking). Used by the web_scrape transform to prevent pipelines from accessing internal network resources or cloud metadata endpoints.
**Key dependencies:** Imports `ipaddress`, `socket`, `urllib.parse`, `concurrent.futures` (all standard library). Consumed by `plugins/transforms/web_scrape.py` and `plugins/transforms/test_web_scrape_properties.py`.
**Analysis depth:** FULL

## Summary

This is the SSRF prevention layer for ELSPETH's web scraping functionality. It has one critical finding (DNS rebinding / TOCTOU vulnerability) and two warnings (missing blocked ranges, IPv6 bypass). The individual functions are correctly implemented, but the architectural pattern of "validate then fetch" is inherently vulnerable to DNS rebinding attacks because the validation resolves the hostname independently from the HTTP client that subsequently fetches the URL.

## Critical Findings

### [51-84 + web_scrape.py:150-170] DNS rebinding TOCTOU vulnerability

**What:** The `validate_ip()` function resolves a hostname to an IP address using `socket.gethostbyname()` and checks the resolved IP against blocked ranges. However, the return value (the resolved IP) is not used by the caller (`web_scrape.py`). The web_scrape transform calls `validate_ip(parsed.host)` on line 157, discards the return value, and then passes the original URL (containing the hostname) to `_fetch_url()` on line 170. The HTTP client (`httpx`) inside `_fetch_url` performs its own DNS resolution when connecting. Between the two DNS resolutions, an attacker-controlled DNS server can change the A record from a safe public IP to a blocked internal IP (e.g., `169.254.169.254` for cloud metadata).

**Why it matters:** This is a classic DNS rebinding attack. In a cloud environment (AWS, Azure, GCP), the instance metadata service at `169.254.169.254` provides IAM credentials, instance identity, and configuration data. An attacker who controls a domain's DNS could configure it to return a public IP on first resolution (passing validation) and `169.254.169.254` on second resolution (when httpx connects). The pipeline would then fetch cloud credentials and potentially include them in transform output or audit trail.

**Evidence:**

In `web.py`:
```python
def validate_ip(hostname: str, timeout: float = 5.0) -> str:
    # ... resolves hostname via socket.gethostbyname()
    # ... checks IP against blocked ranges
    return ip_str  # Returns resolved IP but caller ignores it
```

In `web_scrape.py`:
```python
# Line 157: Resolves hostname, checks IP, discards result
validate_ip(parsed.host)

# Line 170: HTTP client resolves hostname AGAIN independently
response = self._fetch_url(url, ctx)

# Line 265 inside _fetch_url: original URL with hostname, not resolved IP
http_response = client.get(url, headers=headers)
```

**Remediation approach:** The resolved IP from `validate_ip()` should be used for the actual HTTP connection. Either: (a) pass the resolved IP to the HTTP client and use it in the Host header, or (b) use a custom DNS resolver in httpx that only uses the pre-validated IP, or (c) validate the IP at the socket level after connection but before sending the request.

## Warnings

### [26-34] Missing 0.0.0.0/8 and other special-use ranges in BLOCKED_IP_RANGES

**What:** The blocked ranges cover loopback (127.0.0.0/8), private RFC 1918 ranges, link-local (169.254.0.0/16), and IPv6 equivalents. However, several special-use ranges are missing:

- `0.0.0.0/8` -- "This host on this network" (RFC 1122). `0.0.0.0` in particular is often treated as localhost on Linux.
- `100.64.0.0/10` -- Carrier-grade NAT (RFC 6598). Used internally by cloud providers (e.g., AWS VPC).
- `198.18.0.0/15` -- Benchmarking (RFC 2544). Sometimes used for internal testing.
- `240.0.0.0/4` -- Reserved for future use (RFC 1112).
- `::ffff:0:0/96` -- IPv4-mapped IPv6 addresses. An attacker could use `::ffff:127.0.0.1` to bypass IPv4 loopback blocking if the system resolves to IPv6.
- `fe80::/10` -- IPv6 link-local (the IPv6 equivalent of 169.254.0.0/16, which IS blocked for IPv4 but the IPv6 link-local is NOT in the list, only the broader `fc00::/7` ULA range which does NOT cover `fe80::/10`).

**Why it matters:** `0.0.0.0` is particularly concerning because on many Linux systems it routes to localhost. An attacker could use `http://0.0.0.0:80/` to access local services. IPv4-mapped IPv6 addresses (`::ffff:127.0.0.1`) could bypass the IPv4 loopback check entirely if the DNS resolver returns an IPv6 address.

**Evidence:**
```python
BLOCKED_IP_RANGES = [
    ipaddress.ip_network("127.0.0.0/8"),      # Loopback
    ipaddress.ip_network("10.0.0.0/8"),        # Private Class A
    ipaddress.ip_network("172.16.0.0/12"),     # Private Class B
    ipaddress.ip_network("192.168.0.0/16"),    # Private Class C
    ipaddress.ip_network("169.254.0.0/16"),    # Link-local
    ipaddress.ip_network("::1/128"),           # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),          # IPv6 private (ULA)
    # Missing: 0.0.0.0/8, 100.64.0.0/10, ::ffff:0:0/96, fe80::/10
]
```

### [68] socket.gethostbyname only resolves IPv4

**What:** `socket.gethostbyname()` on line 68 only returns IPv4 addresses. It does not resolve AAAA records (IPv6). If the target hostname only has an AAAA record (IPv6-only), `gethostbyname` will raise `socket.gaierror`, which is caught and converted to `NetworkError`. This means IPv6-only hosts are completely blocked. However, if the HTTP client (`httpx`) supports IPv6, it could independently resolve and connect to an IPv6 address that was never validated.

**Why it matters:** The validation uses IPv4-only resolution while the HTTP client may use IPv6. An attacker could configure a domain with an IPv4 A record pointing to a safe IP (passes validation) and an IPv6 AAAA record pointing to `::1` or `::ffff:169.254.169.254` (used by the HTTP client if it prefers IPv6). This is a variant of the DNS rebinding issue but through protocol mismatch rather than temporal rebinding.

**Evidence:**
```python
def _resolve() -> str:
    try:
        return socket.gethostbyname(hostname)  # IPv4 only
    except socket.gaierror as e:
        raise NetworkError(...)
```

The `httpx` library uses `anyio` for DNS resolution which supports both IPv4 and IPv6 by default.

## Observations

### [72-77] ThreadPoolExecutor for DNS timeout is correct but heavyweight

**What:** A `ThreadPoolExecutor` with `max_workers=1` is created for each `validate_ip()` call to enforce DNS resolution timeout. The executor is properly cleaned up via the context manager. This is a correct approach since `socket.gethostbyname()` has no timeout parameter.

**Why it matters:** Low severity. Creating and destroying a thread pool per validation call has overhead. For high-throughput web scraping pipelines, this could become a bottleneck. A module-level thread pool (reused across calls) would be more efficient, but the current approach is correct and safe.

### [37-48] validate_url_scheme is correct

**What:** The scheme validation correctly parses the URL, lowercases the scheme, and checks against a frozenset-like allowlist. Only `http` and `https` are allowed. This correctly blocks `file://`, `ftp://`, `gopher://`, `data:`, and other dangerous schemes.

### [79-82] IP range checking is linear but adequate

**What:** The IP check iterates through all blocked ranges for each validation. With 7 ranges, this is O(7) per call which is negligible compared to DNS resolution time.

## Verdict

**Status:** CRITICAL
**Recommended action:** (1) Fix the DNS rebinding TOCTOU vulnerability by ensuring the HTTP client uses the pre-validated IP address rather than performing independent DNS resolution. This is the most important fix. (2) Add missing IP ranges, particularly `0.0.0.0/8`, `100.64.0.0/10`, `fe80::/10`, and `::ffff:0:0/96`. (3) Consider using `socket.getaddrinfo()` instead of `socket.gethostbyname()` to handle both IPv4 and IPv6 resolution.
**Confidence:** HIGH -- The DNS rebinding vulnerability is well-understood and the code path from validation to fetch is clearly traceable through two files. The missing IP ranges are verifiable by comparison against RFC 5735 and IANA special-purpose address registries.
