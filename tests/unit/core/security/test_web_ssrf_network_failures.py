"""Regression coverage for SSRF DNS failure branches in web security checks."""

from __future__ import annotations

import time

import pytest

from elspeth.core.security.web import NetworkError, SSRFBlockedError, validate_url_for_ssrf


class TestSSRFDnsFailureBranches:
    """Fail-closed behavior for resolver failures in validate_url_for_ssrf()."""

    def test_dns_timeout_is_translated_to_network_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Resolver timeout must surface as explicit NetworkError."""

        def _slow_resolve(hostname: str) -> list[str]:
            time.sleep(5)  # Much longer than the 0.01s timeout
            return ["127.0.0.1"]

        monkeypatch.setattr("elspeth.core.security.web._resolve_hostname", _slow_resolve)

        with pytest.raises(NetworkError, match=r"DNS resolution timeout \(0\.01s\): example\.com"):
            validate_url_for_ssrf("https://example.com/path", timeout=0.01)

    def test_unexpected_resolver_exception_is_wrapped_as_network_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Unexpected resolver exceptions must be wrapped, not leaked raw."""

        def _exploding_resolve(hostname: str) -> list[str]:
            raise RuntimeError("resolver thread exploded")

        monkeypatch.setattr("elspeth.core.security.web._resolve_hostname", _exploding_resolve)

        with pytest.raises(NetworkError, match=r"DNS resolution failed: example\.com: resolver thread exploded"):
            validate_url_for_ssrf("https://example.com")

    def test_empty_dns_resolution_results_fail_closed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Resolver returning no IPs must fail closed with NetworkError."""
        monkeypatch.setattr("elspeth.core.security.web._resolve_hostname", lambda hostname: [])

        with pytest.raises(NetworkError, match=r"DNS resolution returned no addresses: example\.com"):
            validate_url_for_ssrf("https://example.com")


# ===========================================================================
# Bug 7.5: DNS timeout effectiveness (daemon thread cleanup)
# ===========================================================================


class TestDnsTimeoutEffectiveness:
    """Bug 7.5: DNS resolution must use daemon threads to avoid resource leaks."""

    def test_timeout_does_not_block_caller(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """After timeout, the caller must return promptly without blocking."""

        def _very_slow_resolve(hostname: str) -> list[str]:
            time.sleep(30)
            return ["127.0.0.1"]

        monkeypatch.setattr("elspeth.core.security.web._resolve_hostname", _very_slow_resolve)

        start = time.monotonic()
        with pytest.raises(NetworkError, match="DNS resolution timeout"):
            validate_url_for_ssrf("https://example.com", timeout=0.05)
        elapsed = time.monotonic() - start

        # Should return in well under 1 second, not 30
        assert elapsed < 1.0, f"Timeout took {elapsed:.1f}s — caller blocked on DNS thread"

    def test_ssrf_blocked_error_propagated_directly(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """SSRFBlockedError from resolver must propagate unwrapped."""

        def _ssrf_resolve(hostname: str) -> list[str]:
            raise SSRFBlockedError("blocked by test")

        monkeypatch.setattr("elspeth.core.security.web._resolve_hostname", _ssrf_resolve)

        with pytest.raises(SSRFBlockedError, match="blocked by test"):
            validate_url_for_ssrf("https://example.com")


# ===========================================================================
# Bug 7.6: Port parsing
# ===========================================================================


class TestPortParsing:
    """Bug 7.6: Port 0 and invalid ports must be rejected."""

    def test_port_zero_is_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Port 0 is falsy but must be explicitly blocked."""
        with pytest.raises(SSRFBlockedError, match="Port 0"):
            validate_url_for_ssrf("https://example.com:0/path")

    def test_explicit_port_is_used(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Explicit port (non-zero) should be used in the request."""
        monkeypatch.setattr(
            "elspeth.core.security.web._resolve_hostname",
            lambda hostname: ["93.184.216.34"],
        )
        result = validate_url_for_ssrf("https://example.com:8443/path")
        assert result.port == 8443

    def test_default_https_port(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """No explicit port on HTTPS should default to 443."""
        monkeypatch.setattr(
            "elspeth.core.security.web._resolve_hostname",
            lambda hostname: ["93.184.216.34"],
        )
        result = validate_url_for_ssrf("https://example.com/path")
        assert result.port == 443

    def test_default_http_port(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """No explicit port on HTTP should default to 80."""
        monkeypatch.setattr(
            "elspeth.core.security.web._resolve_hostname",
            lambda hostname: ["93.184.216.34"],
        )
        result = validate_url_for_ssrf("http://example.com/path")
        assert result.port == 80
