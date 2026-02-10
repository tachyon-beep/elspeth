# src/elspeth/testing/chaosweb/error_injector.py
"""Error injection logic and burst state machine for ChaosWeb.

The WebErrorInjector decides per-request whether to inject an error based on
configured percentages. It supports HTTP-level errors, connection-level
failures, content malformations, and redirect injection (including SSRF
redirects to private IPs). A burst state machine elevates error rates
periodically to simulate anti-scraping escalation.

Adapted from ChaosLLM's error_injector.py with web-specific error types.
"""

import random as random_module
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from elspeth.testing.chaosweb.config import WebErrorInjectionConfig


class WebErrorCategory(Enum):
    """Categories of errors the web injector can produce."""

    HTTP = "http"  # Returns an HTTP error status code
    CONNECTION = "connection"  # Connection-level failures (timeout, reset, slow, incomplete)
    MALFORMED = "malformed"  # Returns 200 but with corrupted content
    REDIRECT = "redirect"  # Returns 301/302 redirect (loops or SSRF injection)


# HTTP error types with their status codes.
WEB_HTTP_ERRORS: dict[str, int] = {
    "rate_limit": 429,
    "forbidden": 403,
    "not_found": 404,
    "gone": 410,
    "payment_required": 402,
    "unavailable_for_legal": 451,
    "service_unavailable": 503,
    "bad_gateway": 502,
    "gateway_timeout": 504,
    "internal_error": 500,
}

# Connection-level error types.
WEB_CONNECTION_ERRORS: set[str] = {
    "timeout",
    "connection_reset",
    "connection_stall",
    "slow_response",
    "incomplete_response",
}

# Content malformation types.
WEB_MALFORMED_TYPES: set[str] = {
    "wrong_content_type",
    "encoding_mismatch",
    "truncated_html",
    "invalid_encoding",
    "charset_confusion",
    "malformed_meta",
}

# Redirect injection types.
WEB_REDIRECT_TYPES: set[str] = {
    "redirect_loop",
    "ssrf_redirect",
}

# SSRF redirect targets — comprehensive set covering all blocked IP ranges.
# Each target represents a real attack vector that validate_url_for_ssrf must block.
SSRF_TARGETS: list[str] = [
    # Cloud metadata endpoints
    "http://169.254.169.254/latest/meta-data/",  # AWS metadata
    "http://metadata.google.internal/",  # GCP metadata
    "http://169.254.169.254/metadata/instance",  # Azure metadata
    # Private networks (RFC 1918)
    "http://192.168.1.1/",  # Class C private
    "http://10.0.0.1/",  # Class A private
    "http://172.16.0.1/",  # Class B private
    # Loopback
    "http://127.0.0.1:8080/",  # IPv4 loopback
    # CGNAT (RFC 6598)
    "http://100.64.0.1/",  # CGNAT shared space
    # Current network
    "http://0.0.0.0/",  # Current network (RFC 1122)
    # IPv6 variants
    "http://[::1]/",  # IPv6 loopback
    "http://[::ffff:169.254.169.254]/",  # IPv4-mapped IPv6 (bypass vector)
    # Encoding tricks
    "http://2852039166/",  # Decimal IP for 169.254.169.254
]


@dataclass(frozen=True, slots=True)
class WebErrorDecision:
    """Result of a web error injection decision.

    Extends ChaosLLM's ErrorDecision with web-specific fields for redirect
    injection, encoding mismatches, and incomplete responses.
    """

    error_type: str | None
    status_code: int | None = None
    retry_after_sec: int | None = None
    delay_sec: float | None = None
    start_delay_sec: float | None = None
    category: WebErrorCategory | None = None
    malformed_type: str | None = None
    # Web-specific fields
    redirect_target: str | None = None  # URL for SSRF redirect
    redirect_hops: int | None = None  # Hop count for redirect loops
    incomplete_bytes: int | None = None  # Bytes to send before disconnect
    encoding_actual: str | None = None  # Actual encoding for mismatch scenarios

    @classmethod
    def success(cls) -> "WebErrorDecision":
        """Create a decision for a successful (no error) response."""
        return cls(error_type=None)

    @classmethod
    def http_error(
        cls,
        error_type: str,
        status_code: int,
        retry_after_sec: int | None = None,
    ) -> "WebErrorDecision":
        """Create a decision for an HTTP-level error."""
        return cls(
            error_type=error_type,
            status_code=status_code,
            retry_after_sec=retry_after_sec,
            category=WebErrorCategory.HTTP,
        )

    @classmethod
    def connection_error(
        cls,
        error_type: str,
        delay_sec: float | None = None,
        start_delay_sec: float | None = None,
        status_code: int | None = None,
        incomplete_bytes: int | None = None,
    ) -> "WebErrorDecision":
        """Create a decision for a connection-level failure."""
        return cls(
            error_type=error_type,
            category=WebErrorCategory.CONNECTION,
            delay_sec=delay_sec,
            start_delay_sec=start_delay_sec,
            status_code=status_code,
            incomplete_bytes=incomplete_bytes,
        )

    @classmethod
    def malformed_content(
        cls,
        malformed_type: str,
        encoding_actual: str | None = None,
    ) -> "WebErrorDecision":
        """Create a decision for a malformed content response (200 with bad content)."""
        return cls(
            error_type="malformed",
            status_code=200,
            category=WebErrorCategory.MALFORMED,
            malformed_type=malformed_type,
            encoding_actual=encoding_actual,
        )

    @classmethod
    def redirect(
        cls,
        redirect_type: str,
        *,
        redirect_target: str | None = None,
        redirect_hops: int | None = None,
    ) -> "WebErrorDecision":
        """Create a decision for a redirect injection."""
        return cls(
            error_type=redirect_type,
            status_code=301,
            category=WebErrorCategory.REDIRECT,
            redirect_target=redirect_target,
            redirect_hops=redirect_hops,
        )

    @property
    def should_inject(self) -> bool:
        """Return True if an error should be injected."""
        return self.error_type is not None

    @property
    def is_connection_level(self) -> bool:
        """Return True if error is a connection-level error."""
        return self.category == WebErrorCategory.CONNECTION

    @property
    def is_malformed(self) -> bool:
        """Return True if error is a malformed content response."""
        return self.category == WebErrorCategory.MALFORMED

    @property
    def is_redirect(self) -> bool:
        """Return True if error is a redirect injection."""
        return self.category == WebErrorCategory.REDIRECT


class WebErrorInjector:
    """Decides per-request whether to inject a web error.

    Thread-safe implementation with burst state machine that elevates
    error rates periodically to simulate anti-scraping escalation.

    Usage:
        config = WebErrorInjectionConfig(rate_limit_pct=5.0)
        injector = WebErrorInjector(config)
        decision = injector.decide()
        if decision.should_inject:
            # Handle the error injection
            ...
    """

    def __init__(
        self,
        config: WebErrorInjectionConfig,
        *,
        time_func: Callable[[], float] | None = None,
        rng: random_module.Random | None = None,
    ) -> None:
        """Initialize the web error injector.

        Args:
            config: Web error injection configuration
            time_func: Time function for testing (default: time.monotonic)
            rng: Random instance for testing (default: creates new Random instance).
                 Inject a seeded random.Random() for deterministic testing.
        """
        self._config = config
        self._time_func = time_func if time_func is not None else time.monotonic
        self._rng = rng if rng is not None else random_module.Random()

        # Burst state machine
        self._lock = threading.Lock()
        self._start_time: float | None = None

    def _get_current_time(self) -> float:
        """Get current time, initializing start time if needed."""
        with self._lock:
            current = self._time_func()
            if self._start_time is None:
                self._start_time = current
            return current - self._start_time

    def _is_in_burst(self, elapsed: float) -> bool:
        """Determine if we're currently in a burst period."""
        if not self._config.burst.enabled:
            return False

        interval = self._config.burst.interval_sec
        duration = self._config.burst.duration_sec
        position_in_interval = elapsed % interval
        return position_in_interval < duration

    def _get_burst_rate_limit_pct(self, elapsed: float) -> float:
        """Get rate limit percentage, using burst rate if in burst mode."""
        if self._is_in_burst(elapsed):
            return self._config.burst.rate_limit_pct
        return self._config.rate_limit_pct

    def _get_burst_forbidden_pct(self, elapsed: float) -> float:
        """Get forbidden percentage, using burst rate if in burst mode."""
        if self._is_in_burst(elapsed):
            return self._config.burst.forbidden_pct
        return self._config.forbidden_pct

    def _should_trigger(self, percentage: float) -> bool:
        """Determine if an error should trigger based on percentage."""
        if percentage <= 0:
            return False
        return self._rng.random() * 100 < percentage

    def _pick_retry_after(self) -> int:
        """Pick a random Retry-After value from the configured range."""
        min_sec, max_sec = self._config.retry_after_sec
        return self._rng.randint(min_sec, max_sec)

    def _pick_timeout_delay(self) -> float:
        """Pick a random timeout delay from the configured range."""
        min_sec, max_sec = self._config.timeout_sec
        return self._rng.uniform(min_sec, max_sec)

    def _pick_connection_stall_start(self) -> float:
        """Pick a start delay before stalling the connection."""
        min_sec, max_sec = self._config.connection_stall_start_sec
        return self._rng.uniform(min_sec, max_sec)

    def _pick_connection_stall_delay(self) -> float:
        """Pick a stall duration before disconnect."""
        min_sec, max_sec = self._config.connection_stall_sec
        return self._rng.uniform(min_sec, max_sec)

    def _pick_slow_response_delay(self) -> float:
        """Pick a random slow response delay from the configured range."""
        min_sec, max_sec = self._config.slow_response_sec
        return self._rng.uniform(min_sec, max_sec)

    def _pick_incomplete_bytes(self) -> int:
        """Pick how many bytes to send before disconnecting."""
        min_bytes, max_bytes = self._config.incomplete_response_bytes
        return self._rng.randint(min_bytes, max_bytes)

    def _pick_ssrf_target(self) -> str:
        """Pick a random SSRF redirect target from the target list."""
        return self._rng.choice(SSRF_TARGETS)

    def _pick_redirect_hops(self) -> int:
        """Pick a redirect loop hop count (3 to max_redirect_loop_hops)."""
        return self._rng.randint(3, self._config.max_redirect_loop_hops)

    def decide(self) -> WebErrorDecision:
        """Decide whether to inject an error for this request.

        Priority order:
        1. Connection-level errors (highest)
        2. Redirect injection
        3. HTTP errors
        4. Content malformations (lowest)

        Returns:
            WebErrorDecision indicating what error (if any) to inject
        """
        elapsed = self._get_current_time()
        if self._config.selection_mode == "weighted":
            return self._decide_weighted(elapsed)
        return self._decide_priority(elapsed)

    def _decide_priority(self, elapsed: float) -> WebErrorDecision:
        """Priority-based decision (first matching error wins)."""

        # === Connection-level errors (highest priority) ===

        if self._should_trigger(self._config.timeout_pct):
            delay = self._pick_timeout_delay()
            return WebErrorDecision.connection_error("timeout", delay_sec=delay)

        if self._should_trigger(self._config.connection_reset_pct):
            return WebErrorDecision.connection_error("connection_reset")

        if self._should_trigger(self._config.connection_stall_pct):
            return WebErrorDecision.connection_error(
                "connection_stall",
                delay_sec=self._pick_connection_stall_delay(),
                start_delay_sec=self._pick_connection_stall_start(),
            )

        if self._should_trigger(self._config.slow_response_pct):
            return WebErrorDecision.connection_error(
                "slow_response",
                delay_sec=self._pick_slow_response_delay(),
            )

        if self._should_trigger(self._config.incomplete_response_pct):
            return WebErrorDecision.connection_error(
                "incomplete_response",
                incomplete_bytes=self._pick_incomplete_bytes(),
            )

        # === Redirect injection ===

        if self._should_trigger(self._config.ssrf_redirect_pct):
            return WebErrorDecision.redirect(
                "ssrf_redirect",
                redirect_target=self._pick_ssrf_target(),
            )

        if self._should_trigger(self._config.redirect_loop_pct):
            return WebErrorDecision.redirect(
                "redirect_loop",
                redirect_hops=self._pick_redirect_hops(),
            )

        # === HTTP-level errors ===

        # Rate limit (429) — burst-adjusted
        if self._should_trigger(self._get_burst_rate_limit_pct(elapsed)):
            return WebErrorDecision.http_error(
                "rate_limit",
                429,
                retry_after_sec=self._pick_retry_after(),
            )

        # Forbidden (403) — burst-adjusted (bot detection escalation)
        if self._should_trigger(self._get_burst_forbidden_pct(elapsed)):
            return WebErrorDecision.http_error("forbidden", 403)

        if self._should_trigger(self._config.not_found_pct):
            return WebErrorDecision.http_error("not_found", 404)

        if self._should_trigger(self._config.gone_pct):
            return WebErrorDecision.http_error("gone", 410)

        if self._should_trigger(self._config.payment_required_pct):
            return WebErrorDecision.http_error("payment_required", 402)

        if self._should_trigger(self._config.unavailable_for_legal_pct):
            return WebErrorDecision.http_error("unavailable_for_legal", 451)

        if self._should_trigger(self._config.service_unavailable_pct):
            return WebErrorDecision.http_error("service_unavailable", 503)

        if self._should_trigger(self._config.bad_gateway_pct):
            return WebErrorDecision.http_error("bad_gateway", 502)

        if self._should_trigger(self._config.gateway_timeout_pct):
            return WebErrorDecision.http_error("gateway_timeout", 504)

        if self._should_trigger(self._config.internal_error_pct):
            return WebErrorDecision.http_error("internal_error", 500)

        # === Content malformations (lowest priority) ===

        if self._should_trigger(self._config.wrong_content_type_pct):
            return WebErrorDecision.malformed_content("wrong_content_type")

        if self._should_trigger(self._config.encoding_mismatch_pct):
            return WebErrorDecision.malformed_content("encoding_mismatch", encoding_actual="iso-8859-1")

        if self._should_trigger(self._config.truncated_html_pct):
            return WebErrorDecision.malformed_content("truncated_html")

        if self._should_trigger(self._config.invalid_encoding_pct):
            return WebErrorDecision.malformed_content("invalid_encoding")

        if self._should_trigger(self._config.charset_confusion_pct):
            return WebErrorDecision.malformed_content("charset_confusion")

        if self._should_trigger(self._config.malformed_meta_pct):
            return WebErrorDecision.malformed_content("malformed_meta")

        # No error — success!
        return WebErrorDecision.success()

    def _decide_weighted(self, elapsed: float) -> WebErrorDecision:
        """Weighted mix decision (errors chosen by configured weights)."""
        choices: list[tuple[float, Callable[[], WebErrorDecision]]] = []

        def _add(weight: float, builder: Callable[[], WebErrorDecision]) -> None:
            if weight > 0:
                choices.append((weight, builder))

        # Connection-level
        _add(
            self._config.timeout_pct,
            lambda: WebErrorDecision.connection_error("timeout", delay_sec=self._pick_timeout_delay()),
        )
        _add(
            self._config.connection_reset_pct,
            lambda: WebErrorDecision.connection_error("connection_reset"),
        )
        _add(
            self._config.connection_stall_pct,
            lambda: WebErrorDecision.connection_error(
                "connection_stall",
                delay_sec=self._pick_connection_stall_delay(),
                start_delay_sec=self._pick_connection_stall_start(),
            ),
        )
        _add(
            self._config.slow_response_pct,
            lambda: WebErrorDecision.connection_error("slow_response", delay_sec=self._pick_slow_response_delay()),
        )
        _add(
            self._config.incomplete_response_pct,
            lambda: WebErrorDecision.connection_error(
                "incomplete_response",
                incomplete_bytes=self._pick_incomplete_bytes(),
            ),
        )

        # Redirect injection
        _add(
            self._config.ssrf_redirect_pct,
            lambda: WebErrorDecision.redirect("ssrf_redirect", redirect_target=self._pick_ssrf_target()),
        )
        _add(
            self._config.redirect_loop_pct,
            lambda: WebErrorDecision.redirect("redirect_loop", redirect_hops=self._pick_redirect_hops()),
        )

        # HTTP-level (burst-adjusted for rate limit and forbidden)
        _add(
            self._get_burst_rate_limit_pct(elapsed),
            lambda: WebErrorDecision.http_error("rate_limit", 429, retry_after_sec=self._pick_retry_after()),
        )
        _add(
            self._get_burst_forbidden_pct(elapsed),
            lambda: WebErrorDecision.http_error("forbidden", 403),
        )
        _add(self._config.not_found_pct, lambda: WebErrorDecision.http_error("not_found", 404))
        _add(self._config.gone_pct, lambda: WebErrorDecision.http_error("gone", 410))
        _add(self._config.payment_required_pct, lambda: WebErrorDecision.http_error("payment_required", 402))
        _add(
            self._config.unavailable_for_legal_pct,
            lambda: WebErrorDecision.http_error("unavailable_for_legal", 451),
        )
        _add(self._config.service_unavailable_pct, lambda: WebErrorDecision.http_error("service_unavailable", 503))
        _add(self._config.bad_gateway_pct, lambda: WebErrorDecision.http_error("bad_gateway", 502))
        _add(self._config.gateway_timeout_pct, lambda: WebErrorDecision.http_error("gateway_timeout", 504))
        _add(self._config.internal_error_pct, lambda: WebErrorDecision.http_error("internal_error", 500))

        # Content malformations
        _add(self._config.wrong_content_type_pct, lambda: WebErrorDecision.malformed_content("wrong_content_type"))
        _add(
            self._config.encoding_mismatch_pct,
            lambda: WebErrorDecision.malformed_content("encoding_mismatch", encoding_actual="iso-8859-1"),
        )
        _add(self._config.truncated_html_pct, lambda: WebErrorDecision.malformed_content("truncated_html"))
        _add(self._config.invalid_encoding_pct, lambda: WebErrorDecision.malformed_content("invalid_encoding"))
        _add(self._config.charset_confusion_pct, lambda: WebErrorDecision.malformed_content("charset_confusion"))
        _add(self._config.malformed_meta_pct, lambda: WebErrorDecision.malformed_content("malformed_meta"))

        total_weight = sum(weight for weight, _ in choices)
        if total_weight <= 0:
            return WebErrorDecision.success()

        success_weight = max(0.0, 100.0 - total_weight)
        roll = self._rng.random() * (total_weight + success_weight)
        if roll >= total_weight:
            return WebErrorDecision.success()

        threshold = 0.0
        for weight, builder in choices:
            threshold += weight
            if roll < threshold:
                return builder()

        return WebErrorDecision.success()

    def reset(self) -> None:
        """Reset the injector state (clears burst timing)."""
        with self._lock:
            self._start_time = None

    def is_in_burst(self) -> bool:
        """Check if currently in burst mode (for observability)."""
        elapsed = self._get_current_time()
        return self._is_in_burst(elapsed)
