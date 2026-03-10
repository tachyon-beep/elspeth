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
| `public_only` (default) | `BLOCKED_IP_RANGES` as-is | Production web scraping |
| `unrestricted` | Empty — no IP blocking | Fully controlled test environments |
| `["127.0.0.0/8"]` | `BLOCKED_IP_RANGES` minus `127.0.0.0/8` | ChaosWeb on localhost |
| `["127.0.0.1"]` | `BLOCKED_IP_RANGES` minus `127.0.0.1/32` | Single address |
| `["127.0.0.0/8", "10.0.0.0/8"]` | `BLOCKED_IP_RANGES` minus both ranges | Localhost + internal network |

### Type

`str | list[str]` — Pydantic `field_validator` accepts either form. Keywords are `public_only` and `unrestricted`. List entries are CIDR ranges (`"10.0.0.0/8"`) or single IPs (`"10.0.0.1"`, expanded to `/32` or `/128`).

### Validation Rules

- Keywords must be exact lowercase strings
- CIDR entries are parsed via `ipaddress.ip_network(entry, strict=False)` — crash on unparseable
- Single IPs are expanded: `"127.0.0.1"` → `ip_network("127.0.0.1/32")`
- Empty list `[]` is rejected (ambiguous — use `unrestricted` if you mean no blocking)

## Architecture

### Blocklist Construction (plugin `__init__`)

```python
# In WebScrapeTransform.__init__
allowed_hosts = cfg.http.allowed_hosts  # str | list[str], validated by Pydantic

if allowed_hosts == "public_only":
    self._effective_blocklist = BLOCKED_IP_RANGES  # tuple, the default
elif allowed_hosts == "unrestricted":
    self._effective_blocklist = ()
else:
    # List of CIDR/IP entries to remove from blocklist
    permitted = _parse_allowed_ranges(allowed_hosts)  # -> set[ip_network]
    self._effective_blocklist = tuple(
        blocked for blocked in BLOCKED_IP_RANGES
        if not any(blocked.overlaps(p) or blocked.subnet_of(p) or p.subnet_of(blocked)
                   for p in permitted)
    )
```

**Range removal semantics:** An allowed entry removes any blocked range it overlaps with. `"127.0.0.1"` (a `/32`) removes the entire `127.0.0.0/8` block because `127.0.0.1/32` is a subnet of `127.0.0.0/8`. This is the intuitive behavior — "I want to reach 127.0.0.1" means "don't block loopback."

Wait — that's too aggressive. If you allow `127.0.0.1`, should `127.0.0.2` also be unblocked? Two options:

**Option 1 (coarse): Remove any blocked range containing the allowed entry.**
- Allow `127.0.0.1` → removes `127.0.0.0/8` → all loopback unblocked.
- Simple but overly permissive.

**Option 2 (precise): Only allow IPs that fall within an allowed entry.**
- Allow `127.0.0.1` → only `127.0.0.1` bypasses. `127.0.0.2` still blocked.
- More complex: can't just filter the blocklist. Need to check allowed entries in `_validate_ip_address`.

**Decision: Option 2 (precise).** The blocked ranges stay intact. The validation adds an early-return: if the IP matches any allowed entry, skip the blocklist check. This is more secure (minimal permission) and actually simpler to implement.

### Revised Architecture

```python
# In _validate_ip_address (security module)
def _validate_ip_address(
    ip_str: str,
    blocked_ranges: Sequence[IPv4Network | IPv6Network] = BLOCKED_IP_RANGES,
    allowed_ranges: Sequence[IPv4Network | IPv6Network] = (),
) -> None:
    ip = ipaddress.ip_address(ip_str)

    # Check allowlist first — if IP is in an explicitly allowed range, skip blocklist
    for allowed in allowed_ranges:
        if ip in allowed:
            return

    # Standard blocklist check
    for blocked in blocked_ranges:
        if ip in blocked:
            raise SSRFBlockedError(f"Blocked IP range: {ip_str} in {blocked}")
```

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
| `src/elspeth/core/security/web.py` | Add `allowed_ranges` parameter to `_validate_ip_address()` and `validate_url_for_ssrf()` |
| `src/elspeth/plugins/transforms/web_scrape.py` | Add `allowed_hosts` to `WebScrapeHTTPConfig`, compute `_allowed_ranges` in `__init__`, pass through in `process()` and `_fetch_url()` |
| `src/elspeth/plugins/infrastructure/clients/http.py` | Add `allowed_ranges` parameter to `get_ssrf_safe()` and `_follow_redirects_safe()` |
| `tests/unit/core/security/test_web_security.py` | Test allowed_ranges bypass in `_validate_ip_address` and `validate_url_for_ssrf` |
| `tests/unit/plugins/transforms/test_web_scrape_security.py` | Test allowed_hosts config parsing, blocklist construction, end-to-end with allowed private IPs |
| `tests/unit/plugins/transforms/test_web_scrape.py` | Test config validation (keywords, CIDR, single IPs, empty list rejection) |
| `examples/chaosweb/settings.yaml` | Add `allowed_hosts: ["127.0.0.0/8"]` |
| `config/cicd/enforce_tier_model/` | Update allowlist if needed for new `.get()` or similar patterns |

## Audit Trail Impact

The `allowed_hosts` config is part of the plugin's `options`, which is already serialized into `config_json` on the `nodes` table. An auditor can see exactly which SSRF exemptions were active for any run. No additional audit recording needed.

## What This Does NOT Change

- `core/security/web.py` `BLOCKED_IP_RANGES` constant — untouched
- Default behavior — `public_only` is the default, existing configs unchanged
- DNS resolution / IP pinning — always performed regardless of allowed_hosts
- Scheme validation — always performed (no `file://` bypass)
- Redirect SSRF checks — still validated per-hop, just with the same allowed_ranges
