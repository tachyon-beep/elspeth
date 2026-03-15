# `allowed_hosts` SSRF Allowlist Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add configurable `allowed_hosts` to the `web_scrape` transform, enabling selective bypass of the SSRF IP blocklist for controlled environments (e.g. ChaosWeb on localhost) while keeping cloud metadata endpoints unconditionally blocked.

**Architecture:** Three-tier IP validation — always-blocked (cloud metadata, multicast) checked first, then allowlist early-return, then standard blocklist. The security module (`core/security/web.py`) gains two new constructs: an `ALWAYS_BLOCKED_RANGES` constant and an `allowed_ranges` parameter threaded through validation functions. The plugin (`web_scrape.py`) parses `allowed_hosts` config at init time and passes the computed ranges per-call. See `docs/plans/2026-03-10-allowed-hosts-design.md` for the full design rationale.

**Tech Stack:** Python `ipaddress` module, Pydantic field validators, `pytest` + `hypothesis` for testing.

**Prerequisites:**
- Working dev environment (`uv pip install -e ".[dev]"`)
- Familiarity with the design doc: `docs/plans/2026-03-10-allowed-hosts-design.md`

**Plan review (2026-03-12):** This plan was peer-reviewed by 4 specialized reviewers (Reality, Architecture, Quality, Systems). All findings have been incorporated. Key changes from the review:

1. **Added 3 redirect behavior tests** (Task 3, `TestRedirectAllowedRangesBehavior`) — the design doc requires behavioral outcome tests for redirect chains, not just parameter threading tests. These were missing from the original plan.
2. **Fixed mock target in Task 2 tests** — `get_ssrf_safe()` uses an ephemeral `httpx.Client` context manager, not `self._client`. All three test methods now patch `httpx.Client` globally.
3. **Added ChaosWeb test review step** (Task 5, Step 1b) — changing loopback behavior affects `SSRF_TARGETS` test expectations in `error_injector.py`.
4. **Removed structlog warnings** from `_parse_allowed_ranges()` and `__init__` — `web_scrape.py` has no structlog logger and the project direction is to rely on the audit trail, not ephemeral logs. The `allowed_hosts` config is already serialized into `config_json` on the `nodes` table, so SSRF exemptions are auditable without runtime logging. Host-bit widening and overlap information are derivable from the persisted config at any time.
5. **Changed `pytest.skip()` to `assume()`** in property test (Task 4) for correct Hypothesis behavior.
6. **Added `::ffff:0:0/96` design comment** to `ALWAYS_BLOCKED_RANGES` explaining why it's intentionally absent.
7. **Added notes about existing redirect test coverage gap** and **resume-time policy change behavior**.

**Peer review (2026-03-12, pass 2):** Manual review against codebase reality. Key changes:

8. **Removed structlog warning calls** from `_parse_allowed_ranges()` and `__init__` overlap detection (Task 3, Steps 4b/4c) — `web_scrape.py` has no `log` or `logger` binding and no `structlog` import. The original plan hallucinated "the existing structlog logger in `web_scrape.py`" which does not exist. Adding structlog would be inconsistent with the project direction of relying on the audit trail.
9. **Fixed unused `side_effect` entry** in `test_redirect_to_allowed_private_ip_succeeds` (Task 3, Step 3) — changed `side_effect=[initial_safe, redirect_safe]` to `return_value=initial_safe` because `process()` only calls `validate_url_for_ssrf` once at the `web_scrape` import site; the redirect hop uses the `http.py` import site (a different patch).
10. **Added missing imports** to `TestRedirectAllowedRangesBehavior` test block (Task 3, Step 3) — `test_web_scrape_security.py` needs `from unittest.mock import Mock, patch` and `import httpx` added to its imports for the redirect behavior tests. The existing file does not import these.
11. **Added import guidance** for Task 3, Step 4a — `web_scrape.py` already has two `from elspeth.core.security.web import` blocks (lines 27-29 and 30-34). Do not create a third block. The existing imports are sufficient since the overlap detection logging was removed.

Full review: `docs/plans/2026-03-11-allowed-hosts-implementation.review.json`

**Pre-implementation review (2026-03-12, pass 3):** Manual review before execution.

12. **Added isolated unit tests for `_parse_allowed_ranges`** (Task 3, new Step 7) — the helper was only tested indirectly through `TestAllowedHostsConfig`. Added direct tests for mixed IPv4/IPv6, single IPv6 expansion to /128, host-bit normalization, and immutable return type.
13. **Verified Hypothesis strategies exist** — `blocked_ipv4_from_range()` and `safe_public_ipv4()` are confirmed present in `test_ssrf_properties.py` (lines 41 and 89).

---

## Task 1: Add `ALWAYS_BLOCKED_RANGES` and `allowed_ranges` to security module

**Files:**
- Modify: `src/elspeth/core/security/web.py`
- Test: `tests/unit/core/security/test_web_ssrf_network_failures.py`

This task adds the foundation: the `ALWAYS_BLOCKED_RANGES` constant and the `allowed_ranges` parameter to `_validate_ip_address()` and `validate_url_for_ssrf()`.

### Step 1: Write failing tests for the new validation behavior

Add these test classes to `tests/unit/core/security/test_web_ssrf_network_failures.py`:

```python
# At the top, add these imports (merge with existing):
import ipaddress
from elspeth.core.security.web import (
    ALWAYS_BLOCKED_RANGES,
    BLOCKED_IP_RANGES,
    NetworkError,
    SSRFBlockedError,
    _validate_ip_address,
    validate_url_for_ssrf,
)


# ===========================================================================
# ALWAYS_BLOCKED_RANGES: unconditional blocking
# ===========================================================================


class TestAlwaysBlockedRanges:
    """ALWAYS_BLOCKED_RANGES cannot be bypassed by allowed_ranges."""

    def test_cloud_metadata_blocked_even_with_allow_private(self) -> None:
        """169.254.169.254 blocked even when allowed_ranges covers everything."""
        allow_private = (ipaddress.ip_network("0.0.0.0/0"), ipaddress.ip_network("::/0"))
        with pytest.raises(SSRFBlockedError, match="Always-blocked"):
            _validate_ip_address("169.254.169.254", allowed_ranges=allow_private)

    def test_ipv6_link_local_always_blocked(self) -> None:
        """fe80:: addresses are always blocked (IPv6 link-local)."""
        allow_private = (ipaddress.ip_network("0.0.0.0/0"), ipaddress.ip_network("::/0"))
        with pytest.raises(SSRFBlockedError, match="Always-blocked"):
            _validate_ip_address("fe80::1", allowed_ranges=allow_private)

    def test_ipv4_broadcast_always_blocked(self) -> None:
        """255.255.255.255 is always blocked."""
        allow_private = (ipaddress.ip_network("0.0.0.0/0"), ipaddress.ip_network("::/0"))
        with pytest.raises(SSRFBlockedError, match="Always-blocked"):
            _validate_ip_address("255.255.255.255", allowed_ranges=allow_private)

    def test_ipv4_multicast_always_blocked(self) -> None:
        """224.x.x.x is always blocked."""
        allow_private = (ipaddress.ip_network("0.0.0.0/0"), ipaddress.ip_network("::/0"))
        with pytest.raises(SSRFBlockedError, match="Always-blocked"):
            _validate_ip_address("224.0.0.1", allowed_ranges=allow_private)

    def test_ipv6_multicast_always_blocked(self) -> None:
        """ff02::1 is always blocked."""
        allow_private = (ipaddress.ip_network("0.0.0.0/0"), ipaddress.ip_network("::/0"))
        with pytest.raises(SSRFBlockedError, match="Always-blocked"):
            _validate_ip_address("ff02::1", allowed_ranges=allow_private)

    def test_constant_contains_expected_ranges(self) -> None:
        """Verify ALWAYS_BLOCKED_RANGES has all documented entries."""
        range_strs = {str(r) for r in ALWAYS_BLOCKED_RANGES}
        assert "169.254.0.0/16" in range_strs
        assert "fe80::/10" in range_strs
        assert "255.255.255.255/32" in range_strs
        assert "224.0.0.0/4" in range_strs
        assert "ff00::/8" in range_strs


# ===========================================================================
# allowed_ranges: selective blocklist bypass
# ===========================================================================


class TestAllowedRanges:
    """allowed_ranges parameter enables selective blocklist bypass."""

    def test_loopback_allowed_when_in_allowed_ranges(self) -> None:
        """127.0.0.1 passes when 127.0.0.0/8 is in allowed_ranges."""
        allowed = (ipaddress.ip_network("127.0.0.0/8"),)
        _validate_ip_address("127.0.0.1", allowed_ranges=allowed)  # Should not raise

    def test_loopback_blocked_without_allowed_ranges(self) -> None:
        """127.0.0.1 is still blocked when allowed_ranges is empty (default)."""
        with pytest.raises(SSRFBlockedError, match="Blocked IP range"):
            _validate_ip_address("127.0.0.1")

    def test_precise_allowlist_only_allows_matching_ip(self) -> None:
        """Allowing 127.0.0.1/32 does NOT allow 127.0.0.2."""
        allowed = (ipaddress.ip_network("127.0.0.1/32"),)
        _validate_ip_address("127.0.0.1", allowed_ranges=allowed)  # OK
        with pytest.raises(SSRFBlockedError):
            _validate_ip_address("127.0.0.2", allowed_ranges=allowed)

    def test_private_range_allowed_selectively(self) -> None:
        """10.0.0.0/8 allowed does not allow 192.168.1.1."""
        allowed = (ipaddress.ip_network("10.0.0.0/8"),)
        _validate_ip_address("10.1.2.3", allowed_ranges=allowed)  # OK
        with pytest.raises(SSRFBlockedError):
            _validate_ip_address("192.168.1.1", allowed_ranges=allowed)

    def test_public_ip_still_allowed_without_allowlist(self) -> None:
        """Public IPs pass even when allowed_ranges is empty."""
        _validate_ip_address("8.8.8.8")  # Should not raise

    def test_cross_family_no_match(self) -> None:
        """IPv4 allowlist does not match IPv6 addresses (cross-family)."""
        allowed = (ipaddress.ip_network("127.0.0.0/8"),)
        # IPv4-mapped IPv6 for 127.0.0.1 — should NOT match IPv4 allowlist
        with pytest.raises(SSRFBlockedError):
            _validate_ip_address("::ffff:127.0.0.1", allowed_ranges=allowed)

    def test_ipv6_allowlist_works(self) -> None:
        """IPv6 allowlist entry matches IPv6 addresses."""
        allowed = (ipaddress.ip_network("::1/128"),)
        _validate_ip_address("::1", allowed_ranges=allowed)  # OK


# ===========================================================================
# allowed_ranges through validate_url_for_ssrf
# ===========================================================================


class TestAllowedRangesFullPath:
    """allowed_ranges works end-to-end through validate_url_for_ssrf."""

    def test_loopback_allowed_via_full_validation(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """127.0.0.1 passes full validation when allowed."""
        monkeypatch.setattr("elspeth.core.security.web._resolve_hostname", lambda h: ["127.0.0.1"])
        allowed = (ipaddress.ip_network("127.0.0.0/8"),)
        result = validate_url_for_ssrf("http://localhost/page", allowed_ranges=allowed)
        assert result.resolved_ip == "127.0.0.1"

    def test_cloud_metadata_blocked_via_full_validation(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """169.254.169.254 blocked via full path even with allow_private."""
        monkeypatch.setattr("elspeth.core.security.web._resolve_hostname", lambda h: ["169.254.169.254"])
        allow_private = (ipaddress.ip_network("0.0.0.0/0"), ipaddress.ip_network("::/0"))
        with pytest.raises(SSRFBlockedError, match="Always-blocked"):
            validate_url_for_ssrf("http://metadata/", allowed_ranges=allow_private)
```

### Step 2: Run tests to verify they fail

Run: `.venv/bin/python -m pytest tests/unit/core/security/test_web_ssrf_network_failures.py -v -x`

Expected: Import errors for `ALWAYS_BLOCKED_RANGES` and signature errors for `allowed_ranges` parameter.

### Step 3: Implement the security module changes

In `src/elspeth/core/security/web.py`:

**3a.** Add `ALWAYS_BLOCKED_RANGES` constant after `BLOCKED_IP_RANGES`:

```python
# Unconditionally blocked — no allowlist can bypass these.
# Cloud metadata endpoints are the #1 SSRF target (IAM credential exfiltration).
# Broadcast/multicast are never valid HTTP targets.
#
# NOTE: ::ffff:0:0/96 (IPv4-mapped IPv6) is intentionally NOT here. It is in
# BLOCKED_IP_RANGES where it can be bypassed by allowed_ranges. This is correct:
# in "allow_private" mode, ::ffff:10.x.x.x should be allowed (the operator asked
# for allow_private access). Cloud metadata via ::ffff:169.254.x.x is still
# blocked because 169.254.0.0/16 IS in ALWAYS_BLOCKED_RANGES — the IPv4-mapped
# form hits the standard blocklist's ::ffff:0:0/96, but the underlying 169.254.x.x
# is caught by the always-blocked check before the allowlist runs.
ALWAYS_BLOCKED_RANGES = (
    ipaddress.ip_network("169.254.0.0/16"),    # IPv4 link-local (AWS/Azure/GCP metadata)
    ipaddress.ip_network("fe80::/10"),           # IPv6 link-local (same attack surface)
    ipaddress.ip_network("255.255.255.255/32"),  # IPv4 broadcast
    ipaddress.ip_network("224.0.0.0/4"),         # IPv4 multicast
    ipaddress.ip_network("ff00::/8"),            # IPv6 multicast
)
```

**3b.** Update `_validate_ip_address` signature and body:

```python
from collections.abc import Sequence
from ipaddress import IPv4Network, IPv6Network

def _validate_ip_address(
    ip_str: str,
    *,
    allowed_ranges: Sequence[IPv4Network | IPv6Network] = (),
) -> None:
    """Validate that an IP address is not in any blocked range.

    Three-tier check order:
    1. ALWAYS_BLOCKED_RANGES — unconditional, no allowlist bypass
    2. allowed_ranges — if IP matches, skip blocklist (early return)
    3. BLOCKED_IP_RANGES — standard blocklist

    Args:
        ip_str: IP address string (IPv4 or IPv6)
        allowed_ranges: IP networks that bypass the standard blocklist.
            Does NOT bypass ALWAYS_BLOCKED_RANGES.

    Raises:
        SSRFBlockedError: If IP is blocked or unparseable (fail-closed)
    """
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError as e:
        raise SSRFBlockedError(f"Unparseable IP address: {ip_str!r}: {e}") from e

    # 1. Always-blocked — unconditional, no bypass
    for never_allow in ALWAYS_BLOCKED_RANGES:
        if ip in never_allow:
            raise SSRFBlockedError(f"Always-blocked IP range: {ip_str} in {never_allow}")

    # 2. Allowlist — if IP matches an allowed range, skip blocklist
    for allowed in allowed_ranges:
        try:
            if ip in allowed:
                return
        except TypeError:
            # Cross-family check (e.g. IPv6 address in IPv4 network) — treat as no match
            continue

    # 3. Standard blocklist
    for blocked in BLOCKED_IP_RANGES:
        if ip in blocked:
            raise SSRFBlockedError(f"Blocked IP range: {ip_str} in {blocked}")
```

**Note:** No logging is added here. `_validate_ip_address` is a pure L1 validation function with no access to audit infrastructure. The allowlist bypass is already observable through the audit trail: `allowed_hosts` config is serialized into `config_json` on the `nodes` table, and the resolved IP is recorded by `AuditedHTTPClient.record_call()`. Adding a structlog call here would duplicate audit data as ephemeral logs.

**3c.** Update `validate_url_for_ssrf` signature to accept and pass through `allowed_ranges`:

```python
def validate_url_for_ssrf(
    url: str,
    timeout: float = 5.0,
    *,
    allowed_ranges: Sequence[IPv4Network | IPv6Network] = (),
) -> SSRFSafeRequest:
```

And in the "Step 4: Validate ALL resolved IPs" section, change:

```python
    # Step 4: Validate ALL resolved IPs
    for ip_str in ip_list:
        _validate_ip_address(ip_str, allowed_ranges=allowed_ranges)
```

**3d.** Add `Sequence` import at top of file:

```python
from collections.abc import Sequence
from ipaddress import IPv4Network, IPv6Network
```

**3e.** Add `ALWAYS_BLOCKED_RANGES` to `src/elspeth/core/security/__init__.py` exports:

In the import block, add `ALWAYS_BLOCKED_RANGES` alongside the existing web imports:

```python
from elspeth.core.security.web import (
    ALWAYS_BLOCKED_RANGES,
    NetworkError,
    SSRFBlockedError,
    SSRFSafeRequest,
    validate_url_for_ssrf,
    validate_url_scheme,
)
```

And add `"ALWAYS_BLOCKED_RANGES"` to the `__all__` list (alphabetical position — first entry).

### Step 4: Run tests to verify they pass

Run: `.venv/bin/python -m pytest tests/unit/core/security/test_web_ssrf_network_failures.py -v`

Expected: All tests pass, including existing ones (default `allowed_ranges=()` preserves behavior).

Also run existing SSRF tests to verify no regression:

Run: `.venv/bin/python -m pytest tests/unit/core/security/ tests/property/plugins/web_scrape/test_ssrf_properties.py -v`

### Step 5: Commit

```bash
git add src/elspeth/core/security/web.py src/elspeth/core/security/__init__.py tests/unit/core/security/test_web_ssrf_network_failures.py
git commit -m "feat: add ALWAYS_BLOCKED_RANGES and allowed_ranges to SSRF validation

- Three-tier check: always-blocked → allowlist → blocklist
- Cloud metadata (169.254/fe80::) unconditionally blocked
- Cross-family TypeError handled safely (fails closed)
- ALWAYS_BLOCKED_RANGES exported from core/security package
- Design: docs/plans/2026-03-10-allowed-hosts-design.md

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

**Definition of Done:**
- [ ] `ALWAYS_BLOCKED_RANGES` constant exported from `core/security/web.py` (as a **tuple**, not list)
- [ ] `ALWAYS_BLOCKED_RANGES` added to `core/security/__init__.py` imports and `__all__`
- [ ] `_validate_ip_address` accepts `allowed_ranges` kwarg
- [ ] `validate_url_for_ssrf` accepts and threads `allowed_ranges`
- [ ] Always-blocked ranges cannot be bypassed even with allow_private allowlist
- [ ] Cross-family `TypeError` caught and treated as no-match
- [ ] All existing SSRF tests still pass (no regression)

---

## Task 2: Thread `allowed_ranges` through `AuditedHTTPClient`

**Files:**
- Modify: `src/elspeth/plugins/infrastructure/clients/http.py`

This task adds the `allowed_ranges` parameter to `get_ssrf_safe()` and `_follow_redirects_safe()` so redirect hops respect the same allowlist as the initial request.

### Step 0: Create test directory

The directory `tests/unit/plugins/infrastructure/clients/` does not exist yet. Create it:

```bash
mkdir -p tests/unit/plugins/infrastructure/clients
touch tests/unit/plugins/infrastructure/clients/__init__.py
```

### Step 1: Write failing tests for redirect allowlist threading

Add a new test file `tests/unit/plugins/infrastructure/clients/test_http_allowed_ranges.py`.

**Important context:** The purpose of this test file is to verify that `AuditedHTTPClient.get_ssrf_safe()` and `_follow_redirects_safe()` correctly **thread** the `allowed_ranges` parameter through the redirect chain. There are 4 handoff points where the parameter could be silently dropped:

1. `WebScrapeTransform.process()` → `validate_url_for_ssrf()` (tested in Task 3)
2. `WebScrapeTransform._fetch_url()` → `get_ssrf_safe()` (tested in Task 3)
3. `get_ssrf_safe()` → `_follow_redirects_safe()` (**tested here**)
4. `_follow_redirects_safe()` → `validate_url_for_ssrf()` (**tested here**)

If `allowed_ranges` is dropped at handoff 3 or 4, the default `()` means the full blocklist applies — which silently breaks the allowlist feature for redirect scenarios (fails closed, not a security hole, but the feature doesn't work). These tests verify the threading is correct by monkeypatching `validate_url_for_ssrf` at the call site inside `_follow_redirects_safe` and asserting that `allowed_ranges` arrives there.

```python
"""Tests for allowed_ranges parameter threading through AuditedHTTPClient redirect chain.

These tests verify that get_ssrf_safe() and _follow_redirects_safe() correctly
pass allowed_ranges through to validate_url_for_ssrf() at each redirect hop.

The critical risk: allowed_ranges has 4 handoff points in the redirect chain.
A dropped parameter at any hop defaults to () (full blocklist), which silently
breaks the allowlist feature for redirect scenarios. These tests catch that.

Approach: We monkeypatch validate_url_for_ssrf at the module where it's imported
(elspeth.plugins.infrastructure.clients.http) so we can inspect whether
allowed_ranges is passed through during redirect hops. We use a real initial
response with a 301 redirect to trigger _follow_redirects_safe.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Sequence
from ipaddress import IPv4Network, IPv6Network
from unittest.mock import Mock, call, patch

import httpx
import pytest

from elspeth.core.security.web import SSRFBlockedError, SSRFSafeRequest


@pytest.fixture
def mock_recorder():
    """Minimal LandscapeRecorder mock for AuditedHTTPClient."""
    recorder = Mock()
    recorder.record_call = Mock()
    return recorder


@pytest.fixture
def mock_telemetry_emit():
    """No-op telemetry callback."""
    return Mock()


class TestRedirectAllowedRangesThreading:
    """Verify allowed_ranges is threaded from get_ssrf_safe through _follow_redirects_safe
    to the validate_url_for_ssrf call at each redirect hop.

    Architecture:
      get_ssrf_safe(request, allowed_ranges=X)
        -> _follow_redirects_safe(..., allowed_ranges=X)
          -> validate_url_for_ssrf(redirect_url, allowed_ranges=X)  <-- must receive X

    We patch validate_url_for_ssrf at the import site inside http.py so we can
    capture the kwargs it receives during redirect processing.
    """

    def test_allowed_ranges_passed_to_redirect_validation(
        self, mock_recorder, mock_telemetry_emit
    ) -> None:
        """allowed_ranges from get_ssrf_safe reaches validate_url_for_ssrf in redirect hop."""
        from elspeth.plugins.infrastructure.clients.http import AuditedHTTPClient

        allowed = (ipaddress.ip_network("127.0.0.0/8"),)

        # Build a realistic initial SSRFSafeRequest (as if validate_url_for_ssrf already ran)
        initial_request = SSRFSafeRequest(
            original_url="http://example.com/start",
            resolved_ip="93.184.216.34",
            host_header="example.com",
            port=80,
            path="/start",
            scheme="http",
        )

        # Build a redirect SSRFSafeRequest that validate_url_for_ssrf would return
        redirect_safe_request = SSRFSafeRequest(
            original_url="http://localhost/redirected",
            resolved_ip="127.0.0.1",
            host_header="localhost",
            port=80,
            path="/redirected",
            scheme="http",
        )

        client = AuditedHTTPClient(
            recorder=mock_recorder,
            state_id="test-state",
            run_id="test-run",
            telemetry_emit=mock_telemetry_emit,
        )

        try:
            # Mock the initial HTTP request to return a 301 redirect
            redirect_response = httpx.Response(
                301,
                headers={"location": "http://localhost/redirected"},
                request=httpx.Request("GET", "http://93.184.216.34:80/start"),
            )
            # Mock the follow-up request to return 200
            final_response = httpx.Response(
                200,
                text="OK",
                request=httpx.Request("GET", "http://127.0.0.1:80/redirected"),
            )

            # Patch validate_url_for_ssrf at the import site in http.py
            # This is called inside _follow_redirects_safe for each redirect hop
            #
            # IMPORTANT: get_ssrf_safe() creates an EPHEMERAL httpx.Client via
            # "with httpx.Client(...) as ssrf_client:" — it does NOT use self._client.
            # We must patch httpx.Client globally to intercept the initial request.
            # The redirect hop also uses an ephemeral client inside _follow_redirects_safe.
            with patch(
                "elspeth.plugins.infrastructure.clients.http.validate_url_for_ssrf",
                return_value=redirect_safe_request,
            ) as mock_validate, patch("httpx.Client") as MockClient:
                # First httpx.Client() call is the initial request — returns redirect
                initial_client = Mock()
                initial_client.__enter__ = Mock(return_value=initial_client)
                initial_client.__exit__ = Mock(return_value=False)
                initial_client.get.return_value = redirect_response

                # Second httpx.Client() call is the redirect hop — returns 200
                hop_client = Mock()
                hop_client.__enter__ = Mock(return_value=hop_client)
                hop_client.__exit__ = Mock(return_value=False)
                hop_client.get.return_value = final_response

                MockClient.side_effect = [initial_client, hop_client]

                client.get_ssrf_safe(
                    initial_request,
                    follow_redirects=True,
                    allowed_ranges=allowed,
                )

                # Assert validate_url_for_ssrf was called during the redirect hop
                # and received the allowed_ranges parameter
                mock_validate.assert_called_once()
                call_kwargs = mock_validate.call_args
                assert call_kwargs.kwargs.get("allowed_ranges") == allowed or (
                    len(call_kwargs.args) > 1 and call_kwargs.args[1] == allowed
                ), (
                    f"validate_url_for_ssrf was called during redirect but allowed_ranges "
                    f"was not passed through. Call args: {call_kwargs}"
                )
        finally:
            client.close()

    def test_empty_allowed_ranges_default_preserved_in_redirect(
        self, mock_recorder, mock_telemetry_emit
    ) -> None:
        """When no allowed_ranges is passed to get_ssrf_safe, redirect hops get default ()."""
        from elspeth.plugins.infrastructure.clients.http import AuditedHTTPClient

        initial_request = SSRFSafeRequest(
            original_url="http://example.com/start",
            resolved_ip="93.184.216.34",
            host_header="example.com",
            port=80,
            path="/start",
            scheme="http",
        )

        redirect_safe_request = SSRFSafeRequest(
            original_url="http://other.example.com/page",
            resolved_ip="93.184.216.35",
            host_header="other.example.com",
            port=80,
            path="/page",
            scheme="http",
        )

        client = AuditedHTTPClient(
            recorder=mock_recorder,
            state_id="test-state",
            run_id="test-run",
            telemetry_emit=mock_telemetry_emit,
        )

        try:
            redirect_response = httpx.Response(
                301,
                headers={"location": "http://other.example.com/page"},
                request=httpx.Request("GET", "http://93.184.216.34:80/start"),
            )
            final_response = httpx.Response(
                200,
                text="OK",
                request=httpx.Request("GET", "http://93.184.216.35:80/page"),
            )

            # Same mock pattern as above — patch httpx.Client globally, not self._client
            with patch(
                "elspeth.plugins.infrastructure.clients.http.validate_url_for_ssrf",
                return_value=redirect_safe_request,
            ) as mock_validate, patch("httpx.Client") as MockClient:
                initial_client = Mock()
                initial_client.__enter__ = Mock(return_value=initial_client)
                initial_client.__exit__ = Mock(return_value=False)
                initial_client.get.return_value = redirect_response

                hop_client = Mock()
                hop_client.__enter__ = Mock(return_value=hop_client)
                hop_client.__exit__ = Mock(return_value=False)
                hop_client.get.return_value = final_response

                MockClient.side_effect = [initial_client, hop_client]

                # Call WITHOUT allowed_ranges — should default to ()
                client.get_ssrf_safe(
                    initial_request,
                    follow_redirects=True,
                )

                mock_validate.assert_called_once()
                call_kwargs = mock_validate.call_args
                actual_allowed = call_kwargs.kwargs.get("allowed_ranges", ())
                assert actual_allowed == (), (
                    f"Default allowed_ranges should be () but got {actual_allowed}"
                )
        finally:
            client.close()

    def test_allowed_ranges_not_threaded_when_no_redirect(
        self, mock_recorder, mock_telemetry_emit
    ) -> None:
        """When response is not a redirect, validate_url_for_ssrf is not called again."""
        from elspeth.plugins.infrastructure.clients.http import AuditedHTTPClient

        allowed = (ipaddress.ip_network("10.0.0.0/8"),)

        initial_request = SSRFSafeRequest(
            original_url="http://example.com/page",
            resolved_ip="93.184.216.34",
            host_header="example.com",
            port=80,
            path="/page",
            scheme="http",
        )

        client = AuditedHTTPClient(
            recorder=mock_recorder,
            state_id="test-state",
            run_id="test-run",
            telemetry_emit=mock_telemetry_emit,
        )

        try:
            ok_response = httpx.Response(
                200,
                text="<html>Content</html>",
                request=httpx.Request("GET", "http://93.184.216.34:80/page"),
            )

            # Patch httpx.Client globally — get_ssrf_safe uses an ephemeral client
            with patch(
                "elspeth.plugins.infrastructure.clients.http.validate_url_for_ssrf",
            ) as mock_validate, patch("httpx.Client") as MockClient:
                initial_client = Mock()
                initial_client.__enter__ = Mock(return_value=initial_client)
                initial_client.__exit__ = Mock(return_value=False)
                initial_client.get.return_value = ok_response
                MockClient.return_value = initial_client

                client.get_ssrf_safe(
                    initial_request,
                    follow_redirects=True,
                    allowed_ranges=allowed,
                )

                # No redirect, so validate_url_for_ssrf should NOT be called
                # (it was already called before get_ssrf_safe by the caller)
                mock_validate.assert_not_called()
        finally:
            client.close()
```

### Step 2: Run tests to verify they fail

Run: `.venv/bin/python -m pytest tests/unit/plugins/infrastructure/clients/test_http_allowed_ranges.py -v -x`

Expected: Failures because `get_ssrf_safe` and `_follow_redirects_safe` don't accept `allowed_ranges` yet (TypeError on unexpected keyword argument).

### Step 3: Add `allowed_ranges` parameter to `get_ssrf_safe()` and `_follow_redirects_safe()`

In `src/elspeth/plugins/infrastructure/clients/http.py`:

**3a.** Add imports at top:

```python
from collections.abc import Sequence
from ipaddress import IPv4Network, IPv6Network
```

**3b.** Update `get_ssrf_safe` signature:

```python
def get_ssrf_safe(
    self,
    request: SSRFSafeRequest,
    *,
    headers: dict[str, str] | None = None,
    follow_redirects: bool = False,
    max_redirects: int = 10,
    allowed_ranges: Sequence[IPv4Network | IPv6Network] = (),
) -> httpx.Response:
```

**3c.** Pass `allowed_ranges` to `_follow_redirects_safe` call (around line 711):

```python
                response, redirect_count = self._follow_redirects_safe(
                    response,
                    max_redirects,
                    effective_timeout,
                    merged_headers,
                    original_url=request.original_url,
                    allowed_ranges=allowed_ranges,
                )
```

**3d.** Update `_follow_redirects_safe` signature:

```python
def _follow_redirects_safe(
    self,
    response: httpx.Response,
    max_redirects: int,
    timeout: float,
    original_headers: dict[str, str],
    original_url: str,
    *,
    allowed_ranges: Sequence[IPv4Network | IPv6Network] = (),
) -> tuple[httpx.Response, int]:
```

**3e.** Pass `allowed_ranges` to `validate_url_for_ssrf` in the redirect loop (around line 919):

```python
            redirect_request = validate_url_for_ssrf(redirect_url, allowed_ranges=allowed_ranges)
```

### Step 4: Run all HTTP client tests

Run: `.venv/bin/python -m pytest tests/unit/plugins/infrastructure/clients/ tests/unit/plugins/clients/test_http_redirects.py -v`

Expected: All tests pass (default `allowed_ranges=()` preserves existing behavior).

**Note:** The existing `test_http_redirects.py` has 14 test methods that call `_follow_redirects_safe` directly. These all use the old positional signature and will continue to pass with the default `allowed_ranges=()`, but they provide **zero coverage** of the new parameter path. This is expected — they test redirect behavior in general, not the allowlist feature. The new `test_http_allowed_ranges.py` file covers the allowlist threading specifically.

### Step 5: Commit

```bash
git add src/elspeth/plugins/infrastructure/clients/http.py tests/unit/plugins/infrastructure/clients/test_http_allowed_ranges.py
git commit -m "feat: thread allowed_ranges through AuditedHTTPClient redirect chain

- get_ssrf_safe() accepts allowed_ranges kwarg
- _follow_redirects_safe() passes allowed_ranges to validate_url_for_ssrf
- Default () preserves existing behavior

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

**Definition of Done:**
- [ ] `get_ssrf_safe()` has `allowed_ranges` parameter
- [ ] `_follow_redirects_safe()` has `allowed_ranges` parameter
- [ ] Redirect hops use `allowed_ranges` when calling `validate_url_for_ssrf`
- [ ] Test verifies `allowed_ranges` is passed through to `validate_url_for_ssrf` during redirect
- [ ] Test verifies default `()` is preserved when `allowed_ranges` is not passed
- [ ] Test verifies `validate_url_for_ssrf` is not called again when no redirect occurs
- [ ] All existing HTTP client tests pass

---

## Task 3: Add `allowed_hosts` config to `WebScrapeTransform`

**Files:**
- Modify: `src/elspeth/plugins/transforms/web_scrape.py`
- Test: `tests/unit/plugins/transforms/test_web_scrape.py` (config validation)
- Test: `tests/unit/plugins/transforms/test_web_scrape_security.py` (end-to-end)

### Step 1: Write failing tests for config validation

Add to `tests/unit/plugins/transforms/test_web_scrape.py`:

```python
# ===========================================================================
# allowed_hosts config validation
# ===========================================================================


class TestAllowedHostsConfig:
    """Config validation for allowed_hosts field."""

    def test_default_is_public_only(self) -> None:
        """Default allowed_hosts is public_only (no allowlist)."""
        t = WebScrapeTransform({
            "schema": {"mode": "observed"},
            "url_field": "url",
            "content_field": "content",
            "fingerprint_field": "fingerprint",
            "http": {
                "abuse_contact": "test@example.com",
                "scraping_reason": "Test",
            },
        })
        assert t._allowed_ranges == ()

    def test_public_only_keyword(self) -> None:
        """public_only keyword produces empty allowed_ranges."""
        t = WebScrapeTransform({
            "schema": {"mode": "observed"},
            "url_field": "url",
            "content_field": "content",
            "fingerprint_field": "fingerprint",
            "http": {
                "abuse_contact": "test@example.com",
                "scraping_reason": "Test",
                "allowed_hosts": "public_only",
            },
        })
        assert t._allowed_ranges == ()

    def test_allow_private_keyword(self) -> None:
        """allow_private keyword produces 0.0.0.0/0 + ::/0."""
        import ipaddress
        t = WebScrapeTransform({
            "schema": {"mode": "observed"},
            "url_field": "url",
            "content_field": "content",
            "fingerprint_field": "fingerprint",
            "http": {
                "abuse_contact": "test@example.com",
                "scraping_reason": "Test",
                "allowed_hosts": "allow_private",
            },
        })
        range_strs = {str(r) for r in t._allowed_ranges}
        assert "0.0.0.0/0" in range_strs
        assert "::/0" in range_strs

    def test_cidr_list(self) -> None:
        """List of CIDR ranges parsed correctly."""
        import ipaddress
        t = WebScrapeTransform({
            "schema": {"mode": "observed"},
            "url_field": "url",
            "content_field": "content",
            "fingerprint_field": "fingerprint",
            "http": {
                "abuse_contact": "test@example.com",
                "scraping_reason": "Test",
                "allowed_hosts": ["127.0.0.0/8", "10.0.0.0/8"],
            },
        })
        range_strs = {str(r) for r in t._allowed_ranges}
        assert "127.0.0.0/8" in range_strs
        assert "10.0.0.0/8" in range_strs

    def test_single_ip_expanded_to_32(self) -> None:
        """Single IP address expanded to /32."""
        import ipaddress
        t = WebScrapeTransform({
            "schema": {"mode": "observed"},
            "url_field": "url",
            "content_field": "content",
            "fingerprint_field": "fingerprint",
            "http": {
                "abuse_contact": "test@example.com",
                "scraping_reason": "Test",
                "allowed_hosts": ["127.0.0.1"],
            },
        })
        range_strs = {str(r) for r in t._allowed_ranges}
        assert "127.0.0.1/32" in range_strs

    def test_ipv6_cidr_accepted(self) -> None:
        """IPv6 CIDR entries are accepted."""
        t = WebScrapeTransform({
            "schema": {"mode": "observed"},
            "url_field": "url",
            "content_field": "content",
            "fingerprint_field": "fingerprint",
            "http": {
                "abuse_contact": "test@example.com",
                "scraping_reason": "Test",
                "allowed_hosts": ["::1/128"],
            },
        })
        assert len(t._allowed_ranges) == 1

    def test_empty_list_rejected(self) -> None:
        """Empty list is rejected (ambiguous — use allow_private if intended)."""
        with pytest.raises((PluginConfigError, ValueError)):
            WebScrapeTransform({
                "schema": {"mode": "observed"},
                "url_field": "url",
                "content_field": "content",
                "fingerprint_field": "fingerprint",
                "http": {
                    "abuse_contact": "test@example.com",
                    "scraping_reason": "Test",
                    "allowed_hosts": [],
                },
            })

    def test_invalid_cidr_rejected(self) -> None:
        """Unparseable CIDR entry crashes at config time."""
        with pytest.raises((PluginConfigError, ValueError)):
            WebScrapeTransform({
                "schema": {"mode": "observed"},
                "url_field": "url",
                "content_field": "content",
                "fingerprint_field": "fingerprint",
                "http": {
                    "abuse_contact": "test@example.com",
                    "scraping_reason": "Test",
                    "allowed_hosts": ["not-a-cidr"],
                },
            })

    def test_invalid_keyword_rejected(self) -> None:
        """Unknown string keyword is rejected."""
        with pytest.raises((PluginConfigError, ValueError)):
            WebScrapeTransform({
                "schema": {"mode": "observed"},
                "url_field": "url",
                "content_field": "content",
                "fingerprint_field": "fingerprint",
                "http": {
                    "abuse_contact": "test@example.com",
                    "scraping_reason": "Test",
                    "allowed_hosts": "allow_all",
                },
            })

    def test_keyword_case_sensitive(self) -> None:
        """Keywords are case-sensitive — 'Public_Only' is rejected."""
        with pytest.raises((PluginConfigError, ValueError)):
            WebScrapeTransform({
                "schema": {"mode": "observed"},
                "url_field": "url",
                "content_field": "content",
                "fingerprint_field": "fingerprint",
                "http": {
                    "abuse_contact": "test@example.com",
                    "scraping_reason": "Test",
                    "allowed_hosts": "Public_Only",
                },
            })

    def test_host_bits_set_normalized_by_strict_false(self) -> None:
        """CIDR with host bits set is silently normalized via strict=False.

        ipaddress.ip_network("127.0.0.1/8", strict=False) produces 127.0.0.0/8.
        This is intentional — strict=False is used because operators commonly
        write "127.0.0.1/8" meaning "the /8 containing 127.0.0.1".
        """
        import ipaddress
        t = WebScrapeTransform({
            "schema": {"mode": "observed"},
            "url_field": "url",
            "content_field": "content",
            "fingerprint_field": "fingerprint",
            "http": {
                "abuse_contact": "test@example.com",
                "scraping_reason": "Test",
                "allowed_hosts": ["127.0.0.1/8"],
            },
        })
        range_strs = {str(r) for r in t._allowed_ranges}
        # strict=False normalizes 127.0.0.1/8 to 127.0.0.0/8
        assert "127.0.0.0/8" in range_strs

    def test_always_blocked_overlap_accepted_in_config(self) -> None:
        """Entries overlapping ALWAYS_BLOCKED_RANGES are accepted in config.

        They have no effect at runtime (ALWAYS_BLOCKED_RANGES is checked first),
        but are not config errors. An operator might not know which ranges are
        always-blocked, and rejecting their config would be confusing.
        """
        t = WebScrapeTransform({
            "schema": {"mode": "observed"},
            "url_field": "url",
            "content_field": "content",
            "fingerprint_field": "fingerprint",
            "http": {
                "abuse_contact": "test@example.com",
                "scraping_reason": "Test",
                "allowed_hosts": ["169.254.0.0/16"],
            },
        })
        assert len(t._allowed_ranges) == 1
```

### Step 2: Run tests to verify they fail

Run: `.venv/bin/python -m pytest tests/unit/plugins/transforms/test_web_scrape.py::TestAllowedHostsConfig -v -x`

Expected: Failures because `allowed_hosts` field doesn't exist yet and `_allowed_ranges` attribute doesn't exist.

### Step 3: Write failing end-to-end security tests

Add to `tests/unit/plugins/transforms/test_web_scrape_security.py`:

```python
# ===========================================================================
# allowed_hosts end-to-end tests
# ===========================================================================


class TestAllowedHostsEndToEnd:
    """End-to-end tests for allowed_hosts config through the transform."""

    @pytest.fixture
    def allowed_loopback_transform(self, mock_ctx):
        """Transform with allowed_hosts: ["127.0.0.0/8"]."""
        t = WebScrapeTransform({
            "schema": {"mode": "observed"},
            "url_field": "url",
            "content_field": "page_content",
            "fingerprint_field": "page_fingerprint",
            "http": {
                "abuse_contact": "test@example.com",
                "scraping_reason": "Testing allowed_hosts",
                "allowed_hosts": ["127.0.0.0/8"],
            },
        })
        t.on_start(mock_ctx)
        return t

    @pytest.fixture
    def allow_private_transform(self, mock_ctx):
        """Transform with allowed_hosts: allow_private."""
        t = WebScrapeTransform({
            "schema": {"mode": "observed"},
            "url_field": "url",
            "content_field": "page_content",
            "fingerprint_field": "page_fingerprint",
            "http": {
                "abuse_contact": "test@example.com",
                "scraping_reason": "Testing allow_private",
                "allowed_hosts": "allow_private",
            },
        })
        t.on_start(mock_ctx)
        return t

    @respx.mock
    def test_loopback_allowed_with_config(self, allowed_loopback_transform, mock_ctx):
        """Loopback succeeds when explicitly allowed."""
        respx.get("http://127.0.0.1:80/page").mock(
            return_value=httpx.Response(200, text="<html>Local content</html>")
        )
        with patch("socket.getaddrinfo", _mock_getaddrinfo("127.0.0.1")):
            result = allowed_loopback_transform.process(
                make_pipeline_row({"url": "http://localhost/page"}), mock_ctx
            )
        assert result.status == "success"

    def test_non_allowed_private_still_blocked(self, allowed_loopback_transform, mock_ctx):
        """192.168.x.x still blocked when only 127.0.0.0/8 is allowed."""
        with patch("socket.getaddrinfo", _mock_getaddrinfo("192.168.1.1")):
            result = allowed_loopback_transform.process(
                make_pipeline_row({"url": "http://internal.example.com/page"}), mock_ctx
            )
        assert result.status == "error"
        assert result.reason["error_type"] == "SSRFBlockedError"

    def test_cloud_metadata_blocked_with_allow_private(self, allow_private_transform, mock_ctx):
        """Cloud metadata always blocked even with allow_private."""
        with patch("socket.getaddrinfo", _mock_getaddrinfo("169.254.169.254")):
            result = allow_private_transform.process(
                make_pipeline_row({"url": "http://metadata.internal/latest"}), mock_ctx
            )
        assert result.status == "error"
        assert result.reason["error_type"] == "SSRFBlockedError"

    @respx.mock
    def test_public_ip_still_works_with_default(self, transform, mock_ctx):
        """Default (public_only) still allows public IPs — regression check."""
        respx.get("https://93.184.216.34:443/page").mock(
            return_value=httpx.Response(200, text="<html>Content</html>")
        )
        with patch("socket.getaddrinfo", _mock_getaddrinfo("93.184.216.34")):
            result = transform.process(
                make_pipeline_row({"url": "https://example.com/page"}), mock_ctx
            )
        assert result.status == "success"


# ===========================================================================
# Redirect chain behavior tests (design doc requirement, lines 215-217)
# ===========================================================================
#
# IMPORTANT: These tests require additional imports that test_web_scrape_security.py
# does NOT currently have. Add these to the import block at the top of the file:
#
#   from unittest.mock import Mock, patch
#   import httpx
#
# The existing file imports respx, pytest, and ELSPETH internals, but NOT
# unittest.mock or httpx directly. Without these, the redirect tests will
# fail with NameError on Mock/patch/httpx.
#
# These test the BEHAVIORAL outcome of redirects with allowed_ranges active,
# not just parameter threading (which is tested in Task 2). A subtle bug in
# _follow_redirects_safe could thread the parameter correctly but produce
# wrong behavior — these tests catch that.
#
# Approach: monkeypatch validate_url_for_ssrf at the http.py import site
# to control redirect validation outcomes. This avoids the respx limitation
# with IP-pinned requests (existing redirect tests are @pytest.mark.xfail
# for that reason).


class TestRedirectAllowedRangesBehavior:
    """Behavioral redirect tests with allowed_ranges active.

    Required by the design doc (2026-03-10-allowed-hosts-design.md, lines 215-217):
    1. Redirect to allowed private IP succeeds
    2. Redirect to non-allowed private IP raises SSRFBlockedError
    3. Redirect to always-blocked IP (cloud metadata) despite allow_private raises SSRFBlockedError
    """

    @pytest.fixture
    def allowed_loopback_transform(self, mock_ctx):
        """Transform with allowed_hosts: ["127.0.0.0/8"]."""
        t = WebScrapeTransform({
            "schema": {"mode": "observed"},
            "url_field": "url",
            "content_field": "page_content",
            "fingerprint_field": "page_fingerprint",
            "http": {
                "abuse_contact": "test@example.com",
                "scraping_reason": "Testing redirect allowed_hosts",
                "allowed_hosts": ["127.0.0.0/8"],
            },
        })
        t.on_start(mock_ctx)
        return t

    @pytest.fixture
    def allow_private_transform(self, mock_ctx):
        """Transform with allowed_hosts: allow_private."""
        t = WebScrapeTransform({
            "schema": {"mode": "observed"},
            "url_field": "url",
            "content_field": "page_content",
            "fingerprint_field": "page_fingerprint",
            "http": {
                "abuse_contact": "test@example.com",
                "scraping_reason": "Testing allow_private redirects",
                "allowed_hosts": "allow_private",
            },
        })
        t.on_start(mock_ctx)
        return t

    def test_redirect_to_allowed_private_ip_succeeds(
        self, allowed_loopback_transform, mock_ctx
    ):
        """Redirect chain where hop targets an allowed private IP — must succeed."""
        from elspeth.core.security.web import SSRFSafeRequest

        # Initial request resolves to public IP, returns redirect to localhost
        initial_safe = SSRFSafeRequest(
            original_url="http://example.com/start",
            resolved_ip="93.184.216.34",
            host_header="example.com",
            port=80, path="/start", scheme="http",
        )
        redirect_safe = SSRFSafeRequest(
            original_url="http://localhost/redirected",
            resolved_ip="127.0.0.1",
            host_header="localhost",
            port=80, path="/redirected", scheme="http",
        )

        # validate_url_for_ssrf is patched at TWO import sites:
        # 1. web_scrape.py — called once by process() for the initial URL
        # 2. http.py — called by _follow_redirects_safe() for each redirect hop
        # These are different patches because Python's import system binds names
        # per-module, so patching one doesn't affect the other.
        with patch(
            "elspeth.plugins.transforms.web_scrape.validate_url_for_ssrf",
            return_value=initial_safe,
        ), patch(
            "elspeth.plugins.infrastructure.clients.http.validate_url_for_ssrf",
            return_value=redirect_safe,
        ), patch("httpx.Client") as MockClient:
            # Initial request returns 301
            initial_client = Mock()
            initial_client.__enter__ = Mock(return_value=initial_client)
            initial_client.__exit__ = Mock(return_value=False)
            initial_client.get.return_value = httpx.Response(
                301,
                headers={"location": "http://localhost/redirected"},
                request=httpx.Request("GET", "http://93.184.216.34:80/start"),
            )
            # Redirect hop returns 200 with content
            hop_client = Mock()
            hop_client.__enter__ = Mock(return_value=hop_client)
            hop_client.__exit__ = Mock(return_value=False)
            hop_client.get.return_value = httpx.Response(
                200,
                text="<html>Local content</html>",
                request=httpx.Request("GET", "http://127.0.0.1:80/redirected"),
            )
            MockClient.side_effect = [initial_client, hop_client]

            result = allowed_loopback_transform.process(
                make_pipeline_row({"url": "http://example.com/start"}), mock_ctx
            )

        assert result.status == "success"

    def test_redirect_to_non_allowed_private_ip_blocked(
        self, allowed_loopback_transform, mock_ctx
    ):
        """Redirect chain where hop targets a non-allowed private IP — must block."""
        from elspeth.core.security.web import SSRFSafeRequest, SSRFBlockedError

        initial_safe = SSRFSafeRequest(
            original_url="http://example.com/start",
            resolved_ip="93.184.216.34",
            host_header="example.com",
            port=80, path="/start", scheme="http",
        )

        # Redirect validation raises SSRFBlockedError — 192.168.x.x not in allowed_ranges
        with patch(
            "elspeth.plugins.transforms.web_scrape.validate_url_for_ssrf",
            return_value=initial_safe,
        ), patch(
            "elspeth.plugins.infrastructure.clients.http.validate_url_for_ssrf",
            side_effect=SSRFBlockedError("Blocked IP range: 192.168.1.1"),
        ), patch("httpx.Client") as MockClient:
            initial_client = Mock()
            initial_client.__enter__ = Mock(return_value=initial_client)
            initial_client.__exit__ = Mock(return_value=False)
            initial_client.get.return_value = httpx.Response(
                301,
                headers={"location": "http://192.168.1.1/internal"},
                request=httpx.Request("GET", "http://93.184.216.34:80/start"),
            )
            MockClient.return_value = initial_client

            result = allowed_loopback_transform.process(
                make_pipeline_row({"url": "http://example.com/start"}), mock_ctx
            )

        assert result.status == "error"
        assert "SSRFBlockedError" in result.reason.get("error_type", "")

    def test_redirect_to_cloud_metadata_blocked_even_allow_private(
        self, allow_private_transform, mock_ctx
    ):
        """Redirect to always-blocked IP (cloud metadata) despite allow_private — must block."""
        from elspeth.core.security.web import SSRFSafeRequest, SSRFBlockedError

        initial_safe = SSRFSafeRequest(
            original_url="http://example.com/start",
            resolved_ip="93.184.216.34",
            host_header="example.com",
            port=80, path="/start", scheme="http",
        )

        # Redirect validation raises SSRFBlockedError — 169.254.169.254 is always-blocked
        with patch(
            "elspeth.plugins.transforms.web_scrape.validate_url_for_ssrf",
            return_value=initial_safe,
        ), patch(
            "elspeth.plugins.infrastructure.clients.http.validate_url_for_ssrf",
            side_effect=SSRFBlockedError("Always-blocked IP range: 169.254.169.254"),
        ), patch("httpx.Client") as MockClient:
            initial_client = Mock()
            initial_client.__enter__ = Mock(return_value=initial_client)
            initial_client.__exit__ = Mock(return_value=False)
            initial_client.get.return_value = httpx.Response(
                301,
                headers={"location": "http://169.254.169.254/latest/meta-data/"},
                request=httpx.Request("GET", "http://93.184.216.34:80/start"),
            )
            MockClient.return_value = initial_client

            result = allow_private_transform.process(
                make_pipeline_row({"url": "http://example.com/start"}), mock_ctx
            )

        assert result.status == "error"
        assert "SSRFBlockedError" in result.reason.get("error_type", "")
```

### Step 4: Implement the plugin changes

In `src/elspeth/plugins/transforms/web_scrape.py`:

**4a.** Add `allowed_hosts` field to `WebScrapeHTTPConfig`:

First, add the new imports at the top of `web_scrape.py`:

```python
# Add these new stdlib imports near the top (alongside existing imports):
import ipaddress
from ipaddress import IPv4Network, IPv6Network
```

**IMPORTANT:** `web_scrape.py` already has two `from elspeth.core.security.web import` blocks (lines 27-29 and 30-34). Do NOT create a third block. The existing block at lines 30-34 already imports `SSRFBlockedError`, `SSRFSafeRequest`, and `validate_url_for_ssrf` — no changes needed there. (`ALWAYS_BLOCKED_RANGES` is NOT imported here because the overlap detection logging was removed — the audit trail provides observability instead.)

Then add the field to the config model:

```python
class WebScrapeHTTPConfig(BaseModel):
    # ... existing fields ...

    allowed_hosts: str | list[str] = Field(
        default="public_only",
        description="SSRF allowlist: 'public_only' (default), 'allow_private', or list of CIDR ranges",
    )

    @field_validator("allowed_hosts")
    @classmethod
    def _validate_allowed_hosts(cls, v: str | list[str]) -> str | list[str]:
        if isinstance(v, str):
            if v not in ("public_only", "allow_private"):
                raise ValueError(
                    f"allowed_hosts must be 'public_only', 'allow_private', or a list of CIDR ranges, got {v!r}"
                )
            return v
        if not v:
            raise ValueError("allowed_hosts list must not be empty (use 'allow_private' to allow all)")
        for entry in v:
            try:
                ipaddress.ip_network(entry, strict=False)
            except ValueError as e:
                raise ValueError(f"Invalid CIDR in allowed_hosts: {entry!r}: {e}") from e
        return v
```

**4b.** Add `_parse_allowed_ranges` helper function (module-level, before `WebScrapeTransform`):

```python
def _parse_allowed_ranges(entries: list[str]) -> tuple[IPv4Network | IPv6Network, ...]:
    """Parse allowed_hosts list entries into ip_network objects.

    Single IPs (no /) are expanded to /32 (IPv4) or /128 (IPv6).
    Uses strict=False so "10.0.0.1/8" is accepted as "10.0.0.0/8".

    No runtime logging — web_scrape.py has no logger and the project uses the
    audit trail (config_json on the nodes table) for observability, not ephemeral
    logs. Host-bit widening is tested explicitly (test_host_bits_set_normalized_by_strict_false).
    """
    networks: list[IPv4Network | IPv6Network] = []
    for entry in entries:
        network = ipaddress.ip_network(entry, strict=False)
        networks.append(network)
    return tuple(networks)
```

**4c.** In `WebScrapeTransform.__init__`, after the HTTP config parsing block, add allowed_ranges computation:

```python
        # Compute allowed_ranges from allowed_hosts config
        allowed_hosts = cfg.http.allowed_hosts
        if allowed_hosts == "public_only":
            self._allowed_ranges: tuple[IPv4Network | IPv6Network, ...] = ()
        elif allowed_hosts == "allow_private":
            self._allowed_ranges = (
                ipaddress.ip_network("0.0.0.0/0"),
                ipaddress.ip_network("::/0"),
            )
        else:
            self._allowed_ranges = _parse_allowed_ranges(allowed_hosts)
```

**Note:** No runtime logging for overlap detection or host-bit widening. `web_scrape.py` has no structlog logger, and the project relies on the audit trail for observability — `allowed_hosts` config is serialized into `config_json` on the `nodes` table, so an auditor can see exactly which SSRF exemptions were active for any run. Overlap with `ALWAYS_BLOCKED_RANGES` is tested explicitly (`test_always_blocked_overlap_accepted_in_config`) and is a safe no-op at runtime (always-blocked check runs first).

**Resume behavior note:** If an operator changes `allowed_hosts` between the original run and a resume, the new policy applies to all remaining rows (the plugin re-inits from the new settings YAML). This can cause previously-successful rows to fail SSRF checks on retry, or vice versa. The original run's `config_json` on the `nodes` table preserves the original policy, so the discrepancy is auditable — but not obvious. This is consistent with how all plugin config works in ELSPETH's resume model. No code change needed here, but implementers should be aware of this edge case.

**4d.** In `process()`, pass `allowed_ranges` to `validate_url_for_ssrf`:

```python
        try:
            safe_request = validate_url_for_ssrf(url, allowed_ranges=self._allowed_ranges)
```

**4e.** In `_fetch_url()`, pass `allowed_ranges` to `client.get_ssrf_safe`:

```python
            response = client.get_ssrf_safe(
                safe_request,
                headers=headers,
                follow_redirects=True,
                allowed_ranges=self._allowed_ranges,
            )
```

### Step 5: Run all tests

Run: `.venv/bin/python -m pytest tests/unit/plugins/transforms/test_web_scrape.py tests/unit/plugins/transforms/test_web_scrape_security.py -v`

Expected: All tests pass.

### Step 6: Commit

```bash
git add src/elspeth/plugins/transforms/web_scrape.py tests/unit/plugins/transforms/test_web_scrape.py tests/unit/plugins/transforms/test_web_scrape_security.py
git commit -m "feat: add allowed_hosts config to web_scrape transform

- Supports public_only (default), allow_private, or CIDR list
- Validates at config time, computes ranges at init
- Threads allowed_ranges through validate_url_for_ssrf and get_ssrf_safe
- Empty list rejected (ambiguous), invalid CIDR crashes at config

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

### Step 7: Add unit tests for `_parse_allowed_ranges` helper

Add to `tests/unit/plugins/transforms/test_web_scrape.py` alongside `TestAllowedHostsConfig`:

```python
class TestParseAllowedRanges:
    """Direct unit tests for _parse_allowed_ranges helper.

    These complement TestAllowedHostsConfig (which tests through the full transform)
    with isolated edge cases that are easier to debug when they fail.
    """

    def test_mixed_ipv4_and_ipv6(self) -> None:
        """Mixed address families in a single list."""
        from elspeth.plugins.transforms.web_scrape import _parse_allowed_ranges
        result = _parse_allowed_ranges(["10.0.0.0/8", "::1/128"])
        assert len(result) == 2
        range_strs = {str(r) for r in result}
        assert "10.0.0.0/8" in range_strs
        assert "::1/128" in range_strs

    def test_single_ipv6_expanded_to_128(self) -> None:
        """Single IPv6 address without prefix is expanded to /128."""
        from elspeth.plugins.transforms.web_scrape import _parse_allowed_ranges
        result = _parse_allowed_ranges(["::1"])
        assert str(result[0]) == "::1/128"

    def test_host_bits_normalized(self) -> None:
        """Host bits are cleared by strict=False."""
        from elspeth.plugins.transforms.web_scrape import _parse_allowed_ranges
        result = _parse_allowed_ranges(["10.0.0.1/8"])
        assert str(result[0]) == "10.0.0.0/8"

    def test_returns_tuple(self) -> None:
        """Return type is tuple (immutable)."""
        from elspeth.plugins.transforms.web_scrape import _parse_allowed_ranges
        result = _parse_allowed_ranges(["127.0.0.0/8"])
        assert isinstance(result, tuple)
```

**Definition of Done:**
- [ ] `allowed_hosts` field on `WebScrapeHTTPConfig` with validator
- [ ] `_parse_allowed_ranges()` helper correctly parses CIDR and single IPs (no runtime logging — audit trail provides observability)
- [ ] `_parse_allowed_ranges()` has isolated unit tests for mixed families, IPv6 expansion, host-bit normalization, return type
- [ ] `WebScrapeTransform.__init__` computes `_allowed_ranges` from config
- [ ] `process()` passes `_allowed_ranges` to `validate_url_for_ssrf`
- [ ] `_fetch_url()` passes `_allowed_ranges` to `get_ssrf_safe`
- [ ] Config validation tests pass (keywords, CIDR, single IP, empty list, invalid)
- [ ] End-to-end security tests pass (allowed loopback, blocked non-allowed, cloud metadata)
- [ ] Redirect behavior tests pass (redirect to allowed IP succeeds, redirect to non-allowed blocked, redirect to cloud metadata blocked even with allow_private)
- [ ] All existing web_scrape tests pass (no regression)

---

## Task 4: Add property tests for allowlist-blocklist interaction invariants

**Files:**
- Modify: `tests/property/plugins/web_scrape/test_ssrf_properties.py`

### Step 1: Add property test classes

Append to `tests/property/plugins/web_scrape/test_ssrf_properties.py`.

**First, add `assume` to the existing hypothesis imports at the top of the file** (it already imports `given`, `settings`, `st` — add `assume` to that import line):

```python
from hypothesis import assume, given, settings
```

Then append these test classes at the bottom:

```python
# =============================================================================
# Property Tests: Allowlist-Blocklist Interaction Invariants
# =============================================================================


class TestAllowlistBlocklistInvariants:
    """Properties governing the interaction between allowed_ranges and blocklists."""

    @given(data=blocked_ipv4_from_range())
    @settings(max_examples=200)
    def test_allowed_ip_bypasses_blocklist(self, data: tuple[str, ipaddress.IPv4Network]) -> None:
        """Property: An IP in allowed_ranges is NOT blocked by BLOCKED_IP_RANGES."""
        ip_str, network = data
        # Filter out IPs in ALWAYS_BLOCKED_RANGES (they can never be allowed).
        # Use assume() not pytest.skip() — assume() tells Hypothesis to discard
        # this example and try another, preserving shrinking and example database.
        # pytest.skip() would suppress the entire test on first match.
        from elspeth.core.security.web import ALWAYS_BLOCKED_RANGES
        ip = ipaddress.ip_address(ip_str)
        assume(not any(ip in abr for abr in ALWAYS_BLOCKED_RANGES))
        allowed = (network,)
        _validate_ip_address(ip_str, allowed_ranges=allowed)  # Should not raise

    @given(data=blocked_ipv4_from_range())
    @settings(max_examples=200)
    def test_without_allowlist_still_blocked(self, data: tuple[str, ipaddress.IPv4Network]) -> None:
        """Property: Same IPs are blocked when allowed_ranges is empty."""
        ip_str, _ = data
        with pytest.raises(SSRFBlockedError):
            _validate_ip_address(ip_str)

    @given(safe_ip=safe_public_ipv4())
    @settings(max_examples=100)
    def test_public_ip_unaffected_by_allowlist(self, safe_ip: str) -> None:
        """Property: Public IPs pass regardless of allowed_ranges content."""
        # With no allowlist
        _validate_ip_address(safe_ip)
        # With an allowlist for private ranges
        allowed = (ipaddress.ip_network("10.0.0.0/8"),)
        _validate_ip_address(safe_ip, allowed_ranges=allowed)


class TestAlwaysBlockedInvariants:
    """Properties: ALWAYS_BLOCKED_RANGES cannot be overridden."""

    @given(
        ip_int=st.integers(
            min_value=int(ipaddress.ip_address("169.254.0.0")),
            max_value=int(ipaddress.ip_address("169.254.255.255")),
        )
    )
    @settings(max_examples=200)
    def test_link_local_never_allowed(self, ip_int: int) -> None:
        """Property: Any 169.254.x.x IP is always blocked, even with allowlist."""
        ip_str = str(ipaddress.IPv4Address(ip_int))
        allow_private = (ipaddress.ip_network("0.0.0.0/0"), ipaddress.ip_network("::/0"))
        with pytest.raises(SSRFBlockedError, match="Always-blocked"):
            _validate_ip_address(ip_str, allowed_ranges=allow_private)

    @given(
        ip_int=st.integers(
            min_value=int(ipaddress.ip_address("224.0.0.0")),
            max_value=int(ipaddress.ip_address("239.255.255.255")),
        )
    )
    @settings(max_examples=100)
    def test_multicast_never_allowed(self, ip_int: int) -> None:
        """Property: Any 224.x.x.x-239.x.x.x IP is always blocked."""
        ip_str = str(ipaddress.IPv4Address(ip_int))
        allow_private = (ipaddress.ip_network("0.0.0.0/0"),)
        with pytest.raises(SSRFBlockedError, match="Always-blocked"):
            _validate_ip_address(ip_str, allowed_ranges=allow_private)
```

### Step 2: Run property tests

Run: `.venv/bin/python -m pytest tests/property/plugins/web_scrape/test_ssrf_properties.py -v`

Expected: All tests pass (implementation from Tasks 1-3 already in place).

### Step 3: Commit

```bash
git add tests/property/plugins/web_scrape/test_ssrf_properties.py
git commit -m "test: add property tests for allowlist-blocklist interaction invariants

- Allowed IP bypasses standard blocklist
- Same IP blocked without allowlist (default behavior)
- Public IPs unaffected by allowlist presence
- ALWAYS_BLOCKED_RANGES never overridden (link-local, multicast)

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

**Definition of Done:**
- [ ] Property tests for allowlist bypass of standard blocklist
- [ ] Property tests for ALWAYS_BLOCKED_RANGES immutability
- [ ] Property tests for public IP independence from allowlist
- [ ] All property tests pass with 200+ examples each

---

## Task 5: Update ChaosWeb example and verify tier model enforcement

**Files:**
- Modify: `examples/chaosweb/settings.yaml`
- Review: `src/elspeth/testing/chaosweb/error_injector.py` (check `SSRF_TARGETS`)
- Review: `tests/property/testing/chaosweb/test_error_injector_properties.py` (update assertions if needed)
- Check: `config/cicd/enforce_tier_model/` (update if needed)

### Step 1: Add `allowed_hosts` to ChaosWeb settings

In `examples/chaosweb/settings.yaml`, add `allowed_hosts` to the HTTP config block:

```yaml
    http:
      abuse_contact: test@example.com
      scraping_reason: ChaosWeb resilience testing example
      timeout: 10
      allowed_hosts:
        - "127.0.0.0/8"
```

### Step 1b: Review and update ChaosWeb SSRF test expectations

Adding `allowed_hosts: ["127.0.0.0/8"]` to the ChaosWeb example changes the SSRF behavior for loopback targets. The `SSRF_TARGETS` list in `src/elspeth/testing/chaosweb/error_injector.py` includes `http://127.0.0.1:8080/` as a target that ChaosWeb redirects to. Any test that expects loopback redirects to raise `SSRFBlockedError` will now silently pass for the wrong reason (the loopback is allowed, not blocked).

**Action:** Read `src/elspeth/testing/chaosweb/error_injector.py` (around line 71, the `SSRF_TARGETS` list) and `tests/property/testing/chaosweb/test_error_injector_properties.py`. Check if any tests assert that loopback SSRF redirects are blocked. If so, update those assertions to account for the new behavior: when the transform has `allowed_hosts: ["127.0.0.0/8"]`, loopback redirects should succeed, not raise. Tests that run ChaosWeb without the example settings file (i.e., with `public_only` default) are unaffected.

**Note:** If the ChaosWeb property tests only test the error_injector's redirect *construction* (not the transform's SSRF validation), they may not need changes. But verify — don't assume.

### Step 2: Run tier model enforcement

Run: `.venv/bin/python scripts/cicd/enforce_tier_model.py check --root src/elspeth --allowlist config/cicd/enforce_tier_model`

Expected: No new violations. The changes use `ipaddress.ip_network()` and `ipaddress.ip_address()` which are stdlib, not defensive patterns. If any new findings appear, add an allowlist entry to the appropriate module file in `config/cicd/enforce_tier_model/`.

### Step 3: Run full test suite

Run: `.venv/bin/python -m pytest tests/unit/ tests/property/ -x --timeout=60`

Expected: All tests pass.

### Step 4: Run type checking

Run: `.venv/bin/python -m mypy src/elspeth/core/security/web.py src/elspeth/plugins/transforms/web_scrape.py src/elspeth/plugins/infrastructure/clients/http.py`

Expected: No type errors.

### Step 5: Commit

```bash
git add examples/chaosweb/settings.yaml  # Also add any modified ChaosWeb test files from Step 1b
git commit -m "chore: add allowed_hosts to ChaosWeb example settings

- Allows 127.0.0.0/8 for localhost ChaosWeb server
- ChaosWeb SSRF test expectations reviewed in Step 1b
- Closes elspeth-9a6788d807

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

**Definition of Done:**
- [ ] ChaosWeb example has `allowed_hosts: ["127.0.0.0/8"]`
- [ ] ChaosWeb `error_injector.py` SSRF_TARGETS test expectations reviewed and updated if needed (Step 1b)
- [ ] Tier model enforcement passes
- [ ] Full unit + property test suite passes
- [ ] mypy type checking passes
- [ ] Linked to tracking issue

---

## Summary of all files touched

| File | Task | Action |
|------|------|--------|
| `src/elspeth/core/security/web.py` | 1 | Add `ALWAYS_BLOCKED_RANGES`, `allowed_ranges` param |
| `src/elspeth/core/security/__init__.py` | 1 | Export `ALWAYS_BLOCKED_RANGES` |
| `src/elspeth/plugins/infrastructure/clients/http.py` | 2 | Thread `allowed_ranges` through redirect chain |
| `src/elspeth/plugins/transforms/web_scrape.py` | 3 | Add `allowed_hosts` config, parse, pass through |
| `tests/unit/core/security/test_web_ssrf_network_failures.py` | 1 | Tests for always-blocked and allowed_ranges |
| `tests/unit/plugins/infrastructure/clients/test_http_allowed_ranges.py` | 2 | Tests for redirect allowlist threading (new file) |
| `tests/unit/plugins/transforms/test_web_scrape.py` | 3 | Config validation tests |
| `tests/unit/plugins/transforms/test_web_scrape_security.py` | 3 | End-to-end security tests + redirect behavior tests |
| `tests/property/plugins/web_scrape/test_ssrf_properties.py` | 4 | Property tests for interaction invariants |
| `examples/chaosweb/settings.yaml` | 5 | Enable loopback for ChaosWeb |
| `src/elspeth/testing/chaosweb/error_injector.py` | 5 | Review SSRF_TARGETS (update if needed) |
| `tests/property/testing/chaosweb/test_error_injector_properties.py` | 5 | Review assertions (update if needed) |
