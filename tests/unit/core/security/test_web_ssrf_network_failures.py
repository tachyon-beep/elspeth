"""Regression coverage for SSRF DNS failure branches in web security checks."""

from __future__ import annotations

from concurrent.futures import TimeoutError as FuturesTimeoutError

import pytest

from elspeth.core.security.web import NetworkError, validate_url_for_ssrf


class _FutureRaises:
    """Simple future test double that raises from result()."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def result(self, timeout: float | None = None) -> list[str]:
        raise self._exc


class _ExecutorReturnsFuture:
    """ThreadPoolExecutor test double for deterministic DNS branch testing."""

    def __init__(self, future: _FutureRaises, *args: object, **kwargs: object) -> None:
        self._future = future

    def __enter__(self) -> _ExecutorReturnsFuture:
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> bool:
        return False

    def submit(self, fn: object) -> _FutureRaises:
        return self._future


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
