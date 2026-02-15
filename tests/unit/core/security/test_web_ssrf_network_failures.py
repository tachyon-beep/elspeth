"""Regression coverage for SSRF DNS failure branches in web security checks."""

from __future__ import annotations

from concurrent.futures import TimeoutError as FuturesTimeoutError

import pytest

from elspeth.core.security.web import NetworkError, SSRFBlockedError, validate_url_for_ssrf


class _FutureRaises:
    """Simple future test double that raises from result()."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def result(self, timeout: float | None = None) -> list[str]:
        raise self._exc


class _ExecutorReturnsFuture:
    """ThreadPoolExecutor test double for deterministic DNS branch testing.

    Supports both context manager protocol (legacy) and explicit lifecycle
    (shutdown() method) used after the Bug 7.5 fix.
    """

    def __init__(self, future: _FutureRaises, *args: object, **kwargs: object) -> None:
        self._future = future

    def __enter__(self) -> _ExecutorReturnsFuture:
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> bool:
        return False

    def submit(self, fn: object) -> _FutureRaises:
        return self._future

    def shutdown(self, wait: bool = True, cancel_futures: bool = False) -> None:
        pass


class TestSSRFDnsFailureBranches:
    """Fail-closed behavior for resolver failures in validate_url_for_ssrf()."""

    def test_dns_timeout_is_translated_to_network_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Resolver timeout must surface as explicit NetworkError."""
        monkeypatch.setattr(
            "elspeth.core.security.web.ThreadPoolExecutor",
            lambda *args, **kwargs: _ExecutorReturnsFuture(_FutureRaises(FuturesTimeoutError())),
        )

        with pytest.raises(NetworkError, match=r"DNS resolution timeout \(0\.01s\): example\.com"):
            validate_url_for_ssrf("https://example.com/path", timeout=0.01)

    def test_unexpected_resolver_exception_is_wrapped_as_network_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Unexpected resolver exceptions must be wrapped, not leaked raw."""
        monkeypatch.setattr(
            "elspeth.core.security.web.ThreadPoolExecutor",
            lambda *args, **kwargs: _ExecutorReturnsFuture(_FutureRaises(RuntimeError("resolver thread exploded"))),
        )

        with pytest.raises(NetworkError, match=r"DNS resolution failed: example\.com: resolver thread exploded"):
            validate_url_for_ssrf("https://example.com")

    def test_empty_dns_resolution_results_fail_closed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Resolver returning no IPs must fail closed with NetworkError."""
        monkeypatch.setattr("elspeth.core.security.web._resolve_hostname", lambda hostname: [])

        with pytest.raises(NetworkError, match=r"DNS resolution returned no addresses: example\.com"):
            validate_url_for_ssrf("https://example.com")


# ===========================================================================
# Bug 7.5: DNS timeout effectiveness (executor lifecycle)
# ===========================================================================


class TestDnsTimeoutEffectiveness:
    """Bug 7.5: ThreadPoolExecutor must not block on shutdown after timeout."""

    def test_executor_shutdown_called_with_wait_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """After timeout, executor.shutdown(wait=False) must be called, not wait=True."""
        shutdown_calls: list[dict[str, object]] = []

        class _TrackingExecutor:
            def __init__(self, *args: object, **kwargs: object) -> None:
                pass

            def submit(self, fn: object) -> _FutureRaises:
                return _FutureRaises(FuturesTimeoutError())

            def shutdown(self, wait: bool = True, cancel_futures: bool = False) -> None:
                shutdown_calls.append({"wait": wait, "cancel_futures": cancel_futures})

        monkeypatch.setattr(
            "elspeth.core.security.web.ThreadPoolExecutor",
            _TrackingExecutor,
        )

        with pytest.raises(NetworkError):
            validate_url_for_ssrf("https://example.com", timeout=0.01)

        assert len(shutdown_calls) == 1
        assert shutdown_calls[0]["wait"] is False
        assert shutdown_calls[0]["cancel_futures"] is True


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
