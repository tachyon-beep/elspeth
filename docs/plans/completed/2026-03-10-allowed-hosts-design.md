# Design: web_scrape `allowed_hosts` — configurable SSRF blocklist

**Date:** 2026-03-10
**Issue:** elspeth-9a6788d807
**Status:** Approved

## Problem

The `web_scrape` transform blocks all private IP ranges via SSRF protection. This is correct for production but makes the `chaosweb` example (and any internal-network scraping use case) non-functional. There is no way to selectively permit private addresses.

## Design Principles

1. **Security module provides mechanism, plugin provides policy.** `core/security/web.py` validates against a blocklist it's given. It doesn't know about `allowed_hosts` config semantics.
2. **Plugin constructs the effective blocklist at init, passes it stateless per-call.** No config threading through the system. Different plugin instances can have different policies.
3. **DNS resolution and IP pinning are always performed.** Only the blocklist check is affected — the anti-DNS-rebinding defense is never bypassed.

## Config Surface

Single field on `WebScrapeHTTPConfig`:

```yaml
http:
  abuse_contact: compliance@example.com
  scraping_reason: Regulatory monitoring
  allowed_hosts: public_only  # default — full SSRF blocklist
```

### Values

| Value | Effective Blocklist | Use Case |
|-------|-------------------|----------|
| `public_only` (default) | Full `BLOCKED_IP_RANGES` | Production web scraping |
| `allow_private` | Only `ALWAYS_BLOCKED_RANGES` (cloud metadata) | Fully controlled test environments |
| `["127.0.0.0/8"]` | Allow IPs in `127.0.0.0/8`, block all other private ranges + cloud metadata | ChaosWeb on localhost |
| `["127.0.0.1"]` | Allow only `127.0.0.1/32`, block everything else + cloud metadata | Single address |
| `["127.0.0.0/8", "10.0.0.0/8"]` | Allow IPs in both ranges, block all other private ranges + cloud metadata | Localhost + internal network |

**Cloud metadata is always blocked.** `169.254.0.0/16` (AWS/Azure/GCP instance metadata) and `fe80::/10` (IPv6 link-local, same attack surface) are in `ALWAYS_BLOCKED_RANGES` — a separate constant that is checked unconditionally, regardless of `allowed_hosts` mode. There is no valid reason for a web scraping transform to reach infrastructure metadata; a dedicated cloud management plugin would be the appropriate tool for that.

### Type

`str | list[str]` — Pydantic `field_validator` accepts either form. Keywords are `public_only` and `allow_private`. List entries are CIDR ranges (`"10.0.0.0/8"`) or single IPs (`"10.0.0.1"`, expanded to `/32` or `/128`).

### Validation Rules

- Keywords must be exact lowercase strings
- CIDR entries are parsed via `ipaddress.ip_network(entry, strict=False)` in the Pydantic `field_validator` — unparseable entries fail config validation before plugin init
- Single IPs are expanded: `"127.0.0.1"` → `ip_network("127.0.0.1/32")`
- Empty list `[]` is rejected (ambiguous — use `allow_private` if you mean no blocking)
- Entries overlapping `ALWAYS_BLOCKED_RANGES` are accepted in config but have no effect at runtime — the always-blocked check runs before the allowlist. This means `allowed_hosts: ["169.254.0.0/16"]` is not a config error, but `169.254.169.254` is still blocked

## Architecture

### Blocklist Construction (plugin `__init__`)

```python
# In WebScrapeTransform.__init__
allowed_hosts = cfg.http.allowed_hosts  # str | list[str], validated by Pydantic

if allowed_hosts == "public_only":
    self._allowed_ranges = ()  # no allowlist — full BLOCKED_IP_RANGES applies
elif allowed_hosts == "allow_private":
    self._allowed_ranges = (ipaddress.ip_network("0.0.0.0/0"), ipaddress.ip_network("::/0"))
else:
    # List of CIDR/IP entries to allow through the blocklist
    self._allowed_ranges = _parse_allowed_ranges(allowed_hosts)  # -> tuple[ip_network, ...]
```

**Note:** `BLOCKED_IP_RANGES` is a module-level `list` (not a tuple). It is never assigned to instance state directly — the allowlist approach (Option 2 below) means the blocklist constant is always checked in full, and `_allowed_ranges` provides the early-return bypass.

**Range semantics — Option 1 vs Option 2:**

An allowed entry could either remove blocked ranges (coarse) or bypass the blocklist per-IP (precise). Two options:

**Option 1 (coarse): Remove any blocked range containing the allowed entry.**
- Allow `127.0.0.1` → removes `127.0.0.0/8` → all loopback unblocked.
- Simple but overly permissive.

**Option 2 (precise): Only allow IPs that fall within an allowed entry.**
- Allow `127.0.0.1` → only `127.0.0.1` bypasses. `127.0.0.2` still blocked.
- More complex: can't just filter the blocklist. Need to check allowed entries in `_validate_ip_address`.

**Decision: Option 2 (precise).** The blocked ranges stay intact. The validation adds an early-return: if the IP matches any allowed entry, skip the blocklist check. This is more secure (minimal permission) and actually simpler to implement.

### Revised Architecture

#### Always-Blocked Ranges

A new constant `ALWAYS_BLOCKED_RANGES` is checked unconditionally — even when the IP matched an allowed range. These are infrastructure endpoints that a web scraping transform should never reach:

```python
# In core/security/web.py
ALWAYS_BLOCKED_RANGES = (
    # Cloud metadata endpoints — #1 SSRF target, IAM credential exfiltration
    ipaddress.ip_network("169.254.0.0/16"),   # IPv4 link-local (AWS/Azure/GCP metadata)
    ipaddress.ip_network("fe80::/10"),          # IPv6 link-local (same attack surface)
    # Broadcast / reserved — never valid HTTP targets
    ipaddress.ip_network("255.255.255.255/32"), # IPv4 broadcast
    ipaddress.ip_network("224.0.0.0/4"),        # IPv4 multicast
    ipaddress.ip_network("ff00::/8"),            # IPv6 multicast
)
```

#### Updated `_validate_ip_address`

```python
# In _validate_ip_address (security module)
def _validate_ip_address(
    ip_str: str,
    *,
    allowed_ranges: Sequence[IPv4Network | IPv6Network] = (),
) -> None:
    ip = ipaddress.ip_address(ip_str)

    # Always-blocked ranges are checked unconditionally — no allowlist bypass
    for never_allow in ALWAYS_BLOCKED_RANGES:
        if ip in never_allow:
            raise SSRFBlockedError(f"Always-blocked IP range: {ip_str} in {never_allow}")

    # Check allowlist — if IP is in an explicitly allowed range, skip blocklist
    for allowed in allowed_ranges:
        try:
            if ip in allowed:
                return
        except TypeError:
            # Cross-family check (e.g. IPv6 address in IPv4 network) — treat as no match
            continue

    # Standard blocklist check (BLOCKED_IP_RANGES is the module-level constant)
    for blocked in BLOCKED_IP_RANGES:
        if ip in blocked:
            raise SSRFBlockedError(f"Blocked IP range: {ip_str} in {blocked}")
```

> **Note:** The `blocked_ranges` parameter from an earlier design iteration has been removed.
> `BLOCKED_IP_RANGES` is always checked in full as a module-level constant. Making the blocklist
> parameterizable would create a footgun: a caller could accidentally pass an empty blocklist and
> disable all SSRF protection. The `allowed_ranges` parameter provides the selective bypass
> mechanism instead (Option 2 — precise per-IP bypass).

**Order matters:** Always-blocked first, then allowlist, then blocklist. This means `allow_private` mode (which sets `allowed_ranges` to `0.0.0.0/0` + `::/0`) still blocks cloud metadata, broadcast, and multicast.

**Overlap with `BLOCKED_IP_RANGES`:** `169.254.0.0/16` and `fe80::/10` appear in both `ALWAYS_BLOCKED_RANGES` and `BLOCKED_IP_RANGES`. This is intentional — `ALWAYS_BLOCKED_RANGES` is the "ceiling" that no allowlist can punch through, while `BLOCKED_IP_RANGES` is the configurable "floor" that the allowlist can selectively bypass. The double presence is defense-in-depth, not duplication. The multicast/broadcast ranges (`224.0.0.0/4`, `255.255.255.255/32`, `ff00::/8`) are new additions via `ALWAYS_BLOCKED_RANGES` only — they were not in the original blocklist because they are unreachable via HTTP, but blocking them explicitly eliminates any DNS-based attack surface.

And `validate_url_for_ssrf` gains an `allowed_ranges` parameter:

```python
def validate_url_for_ssrf(
    url: str,
    timeout: float = 5.0,
    allowed_ranges: Sequence[IPv4Network | IPv6Network] = (),
) -> SSRFSafeRequest:
    ...
    # Step 4: Validate ALL resolved IPs (with allowed_ranges passed through)
    for ip_str in ip_list:
        _validate_ip_address(ip_str, allowed_ranges=allowed_ranges)
    ...
```

### Call Chain

```
WebScrapeTransform.__init__
  ├── Parse allowed_hosts config
  └── Compute self._allowed_ranges: tuple[ip_network, ...]

WebScrapeTransform.process(row, ctx)
  └── validate_url_for_ssrf(url, allowed_ranges=self._allowed_ranges)
       └── _validate_ip_address(ip, allowed_ranges=self._allowed_ranges)

WebScrapeTransform._fetch_url(safe_request, ctx)
  └── client.get_ssrf_safe(safe_request, ..., allowed_ranges=self._allowed_ranges)
       └── _follow_redirects_safe(...)
            └── validate_url_for_ssrf(redirect_url, allowed_ranges=self._allowed_ranges)
                 └── _validate_ip_address(ip, allowed_ranges=self._allowed_ranges)
```

### Parameter Threading

- `validate_url_for_ssrf()` — new `allowed_ranges` parameter (default `()`)
- `_validate_ip_address()` — new `allowed_ranges` parameter (default `()`)
- `AuditedHTTPClient.get_ssrf_safe()` — new `allowed_ranges` parameter (default `()`)
- `AuditedHTTPClient._follow_redirects_safe()` — new `allowed_ranges` parameter (default `()`)

All default to `()` (empty tuple = current behavior). Only web_scrape passes non-empty values. Future plugins can use the same parameters.

## Files Changed

| File | Change |
|------|--------|
| `src/elspeth/core/security/web.py` | Add `ALWAYS_BLOCKED_RANGES` constant; add `allowed_ranges` parameter to `_validate_ip_address()` and `validate_url_for_ssrf()`; three-tier check order (always-blocked → allowlist → blocklist) |
| `src/elspeth/plugins/transforms/web_scrape.py` | Add `allowed_hosts` to `WebScrapeHTTPConfig`; new `_parse_allowed_ranges()` private helper; compute `self._allowed_ranges` in `__init__`; pass through in `process()` and `_fetch_url()` |
| `src/elspeth/plugins/infrastructure/clients/http.py` | Add `allowed_ranges` parameter to `get_ssrf_safe()` and `_follow_redirects_safe()` |
| `tests/unit/core/security/test_web_ssrf_network_failures.py` | **Extend existing file:** test `allowed_ranges` bypass in `_validate_ip_address` and `validate_url_for_ssrf`; test `ALWAYS_BLOCKED_RANGES` unconditional blocking; test IPv4-mapped IPv6 cross-family behavior (see note below) |
| `tests/unit/plugins/transforms/test_web_scrape_security.py` | Test `allowed_hosts` config parsing, blocklist construction, end-to-end with allowed private IPs; **redirect chain test** with `allowed_ranges` active (see note below) |
| `tests/unit/plugins/transforms/test_web_scrape.py` | Test config validation (keywords, CIDR, single IPs, empty list rejection, IPv6 entries) |
| `tests/property/plugins/web_scrape/test_ssrf_properties.py` | **Extend existing file:** add property tests for allowlist-blocklist interaction invariants |
| `examples/chaosweb/settings.yaml` | Add `allowed_hosts: ["127.0.0.0/8"]` |
| `config/cicd/enforce_tier_model/` | Update allowlist if needed for new `.get()` or similar patterns |

## IPv4-Mapped IPv6 Behavior

Python's `ipaddress` module treats IPv4 and IPv6 as separate address families. The `ip in network` containment check raises `TypeError` when the IP and network are different families — e.g., `IPv6Address("::ffff:127.0.0.1") in IPv4Network("127.0.0.0/8")` raises, not returns `False`.

This means: if an operator configures `allowed_hosts: ["127.0.0.0/8"]` and DNS returns the IPv4-mapped IPv6 address `::ffff:127.0.0.1`, the allowlist check will not match (TypeError is caught or the families don't intersect), and the IP falls through to the blocklist where `::ffff:0:0/96` blocks it. This is **safe** (fails closed) but should be **intentional, not accidental**.

**Implementation requirement:** The allowlist loop in `_validate_ip_address` must handle `TypeError` from cross-family containment checks — either by catching it (treating as "not in range") or by normalizing IPv4-mapped IPv6 addresses to their IPv4 equivalents before the check. The chosen approach and its rationale must be tested explicitly.

## Redirect Test Strategy

The redirect path (`get_ssrf_safe` → `_follow_redirects_safe` → `validate_url_for_ssrf`) has 4 handoff points where `allowed_ranges` must be threaded. A dropped parameter at any hop fails closed (not a security hole) but silently breaks the feature for redirect scenarios.

**Required test cases in `test_web_scrape_security.py`:**

1. Redirect chain where hop targets an allowed private IP — must succeed
2. Redirect chain where hop targets a non-allowed private IP — must raise `SSRFBlockedError`
3. Redirect chain where hop targets an always-blocked IP (cloud metadata) despite `allow_private` mode — must raise `SSRFBlockedError`

The existing redirect tests in `test_web_scrape.py` are `@pytest.mark.xfail` due to `respx` limitations with IP-pinned requests. The new redirect tests should either use a different mocking strategy (e.g., monkeypatching `validate_url_for_ssrf` at the redirect boundary) or be structured as integration tests against a local HTTP server.

## Audit Trail Impact

The `allowed_hosts` config is part of the plugin's `options`, which is already serialized into `config_json` on the `nodes` table. An auditor can see exactly which SSRF exemptions were active for any run. No additional audit recording needed.

## What This Does NOT Change

- `core/security/web.py` `BLOCKED_IP_RANGES` constant — untouched (new `ALWAYS_BLOCKED_RANGES` is additive)
- Default behavior — `public_only` is the default, existing configs unchanged
- DNS resolution / IP pinning — always performed regardless of allowed_hosts
- Scheme validation — always performed (no `file://` bypass)
- Redirect SSRF checks — still validated per-hop, just with the same allowed_ranges
- Resume behavior — `allowed_hosts` is not stored in checkpoints; the plugin re-inits from the settings YAML passed to `elspeth resume`. If the operator changes `allowed_hosts` between the original run and a resume, the new policy applies to all remaining rows. This is consistent with how all plugin config works in ELSPETH's resume model, but worth noting since a security policy change mid-run could cause previously-successful rows to fail SSRF checks on retry
