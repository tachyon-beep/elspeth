# tests/property/testing/chaosweb/test_error_injector_properties.py
"""Property-based tests for ChaosWeb WebErrorInjector.

The WebErrorInjector is the core decision engine for ChaosWeb's fault injection
targeting web scraping pipelines. This module tests the critical invariants:

- WebErrorDecision factory method invariants (frozen, correct categories)
- Error rate statistical accuracy over N trials
- Burst timing periodicity (deterministic with injectable time_func)
- Retry-After values within configured range
- Delay calculations are non-negative
- Redirect hops and SSRF target validity
- Priority vs weighted selection mode behavior
- Config validation boundaries (0-100 percentages)
"""

from __future__ import annotations

import random

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from elspeth.testing.chaosweb.config import (
    WebBurstConfig,
    WebErrorInjectionConfig,
)
from elspeth.testing.chaosweb.error_injector import (
    SSRF_TARGETS,
    WEB_CONNECTION_ERRORS,
    WEB_HTTP_ERRORS,
    WEB_MALFORMED_TYPES,
    WEB_REDIRECT_TYPES,
    WebErrorCategory,
    WebErrorDecision,
    WebErrorInjector,
)

# =============================================================================
# WebErrorDecision Factory Properties
# =============================================================================


class TestWebErrorDecisionFactories:
    """Property tests for WebErrorDecision factory methods."""

    def test_success_has_no_error(self) -> None:
        """Property: success() produces a non-injecting decision."""
        d = WebErrorDecision.success()
        assert not d.should_inject
        assert d.error_type is None
        assert d.category is None
        assert d.status_code is None
        assert d.redirect_target is None
        assert d.redirect_hops is None
        assert d.malformed_type is None
        assert d.incomplete_bytes is None
        assert d.encoding_actual is None

    @given(
        error_type=st.sampled_from(list(WEB_HTTP_ERRORS.keys())),
        status_code=st.sampled_from(list(WEB_HTTP_ERRORS.values())),
    )
    def test_http_error_has_correct_category(self, error_type: str, status_code: int) -> None:
        """Property: http_error() always has HTTP category with correct status code."""
        d = WebErrorDecision.http_error(error_type, status_code)
        assert d.should_inject
        assert d.category == WebErrorCategory.HTTP
        assert d.status_code == status_code
        assert d.error_type == error_type
        assert not d.is_connection_level
        assert not d.is_malformed
        assert not d.is_redirect

    @given(
        error_type=st.sampled_from(list(WEB_HTTP_ERRORS.keys())),
        retry_after=st.integers(min_value=1, max_value=300),
    )
    def test_http_error_retry_after_preserved(self, error_type: str, retry_after: int) -> None:
        """Property: http_error() preserves retry_after_sec when provided."""
        status_code = WEB_HTTP_ERRORS[error_type]
        d = WebErrorDecision.http_error(error_type, status_code, retry_after_sec=retry_after)
        assert d.retry_after_sec == retry_after
        assert d.category == WebErrorCategory.HTTP

    @given(error_type=st.sampled_from(sorted(WEB_CONNECTION_ERRORS)))
    def test_connection_error_has_correct_category(self, error_type: str) -> None:
        """Property: connection_error() always has CONNECTION category."""
        d = WebErrorDecision.connection_error(error_type)
        assert d.should_inject
        assert d.category == WebErrorCategory.CONNECTION
        assert d.is_connection_level
        assert not d.is_malformed
        assert not d.is_redirect

    @given(
        error_type=st.sampled_from(sorted(WEB_CONNECTION_ERRORS)),
        delay=st.floats(min_value=0.0, max_value=120.0, allow_nan=False, allow_infinity=False),
    )
    def test_connection_error_delay_preserved(self, error_type: str, delay: float) -> None:
        """Property: connection_error() preserves delay_sec when provided."""
        d = WebErrorDecision.connection_error(error_type, delay_sec=delay)
        assert d.delay_sec == delay

    @given(
        error_type=st.sampled_from(sorted(WEB_CONNECTION_ERRORS)),
        incomplete_bytes=st.integers(min_value=1, max_value=10000),
    )
    def test_connection_error_incomplete_bytes_preserved(self, error_type: str, incomplete_bytes: int) -> None:
        """Property: connection_error() preserves incomplete_bytes when provided."""
        d = WebErrorDecision.connection_error(error_type, incomplete_bytes=incomplete_bytes)
        assert d.incomplete_bytes == incomplete_bytes

    @given(malformed_type=st.sampled_from(sorted(WEB_MALFORMED_TYPES)))
    def test_malformed_content_has_correct_category(self, malformed_type: str) -> None:
        """Property: malformed_content() has MALFORMED category and status 200."""
        d = WebErrorDecision.malformed_content(malformed_type)
        assert d.should_inject
        assert d.category == WebErrorCategory.MALFORMED
        assert d.status_code == 200
        assert d.is_malformed
        assert not d.is_connection_level
        assert not d.is_redirect
        assert d.malformed_type == malformed_type

    @given(malformed_type=st.sampled_from(sorted(WEB_MALFORMED_TYPES)))
    def test_malformed_content_encoding_actual(self, malformed_type: str) -> None:
        """Property: malformed_content() preserves encoding_actual when provided."""
        d = WebErrorDecision.malformed_content(malformed_type, encoding_actual="iso-8859-1")
        assert d.encoding_actual == "iso-8859-1"
        assert d.category == WebErrorCategory.MALFORMED

    @given(redirect_type=st.sampled_from(sorted(WEB_REDIRECT_TYPES)))
    def test_redirect_has_correct_category(self, redirect_type: str) -> None:
        """Property: redirect() always has REDIRECT category with status 301."""
        # Each redirect type requires its specific field
        if redirect_type == "ssrf_redirect":
            d = WebErrorDecision.redirect(redirect_type, redirect_target="http://169.254.169.254/")
        else:
            d = WebErrorDecision.redirect(redirect_type, redirect_hops=3)
        assert d.should_inject
        assert d.category == WebErrorCategory.REDIRECT
        assert d.status_code == 301
        assert d.is_redirect
        assert not d.is_connection_level
        assert not d.is_malformed

    @given(hops=st.integers(min_value=1, max_value=50))
    def test_redirect_hops_preserved(self, hops: int) -> None:
        """Property: redirect() preserves redirect_hops when provided."""
        d = WebErrorDecision.redirect("redirect_loop", redirect_hops=hops)
        assert d.redirect_hops == hops
        assert d.category == WebErrorCategory.REDIRECT

    @given(target=st.sampled_from(SSRF_TARGETS))
    def test_redirect_target_preserved(self, target: str) -> None:
        """Property: redirect() preserves redirect_target when provided."""
        d = WebErrorDecision.redirect("ssrf_redirect", redirect_target=target)
        assert d.redirect_target == target
        assert d.category == WebErrorCategory.REDIRECT


# =============================================================================
# Error Rate Statistical Accuracy
# =============================================================================


class TestErrorRateAccuracy:
    """Property tests for error rate statistical accuracy.

    With a seeded RNG and enough trials, the observed error rate
    should converge to the configured percentage within a margin.
    """

    @given(
        rate=st.floats(min_value=5.0, max_value=95.0, allow_nan=False, allow_infinity=False),
        seed=st.integers(min_value=0, max_value=2**32 - 1),
    )
    @settings(max_examples=50)
    def test_rate_limit_frequency_converges(self, rate: float, seed: int) -> None:
        """Property: Over 2000 trials, rate_limit rate is within +/-5% of configured."""
        config = WebErrorInjectionConfig(rate_limit_pct=rate)
        rng = random.Random(seed)
        injector = WebErrorInjector(config, rng=rng)

        n_trials = 2000
        errors = sum(1 for _ in range(n_trials) if injector.decide().should_inject)
        observed_rate = (errors / n_trials) * 100

        assert abs(observed_rate - rate) < 5.0, (
            f"Configured rate={rate:.1f}%, observed={observed_rate:.1f}% over {n_trials} trials (seed={seed}). Margin exceeded."
        )

    @given(seed=st.integers(min_value=0, max_value=2**32 - 1))
    @settings(max_examples=30)
    def test_zero_rate_produces_no_errors(self, seed: int) -> None:
        """Property: 0% error rate produces zero errors."""
        config = WebErrorInjectionConfig()  # All rates default to 0.0
        rng = random.Random(seed)
        injector = WebErrorInjector(config, rng=rng)

        for _ in range(500):
            d = injector.decide()
            assert not d.should_inject, "0% rate should never inject errors"

    @given(seed=st.integers(min_value=0, max_value=2**32 - 1))
    @settings(max_examples=30)
    def test_100_pct_rate_limit_always_errors(self, seed: int) -> None:
        """Property: 100% rate_limit produces errors on every request."""
        config = WebErrorInjectionConfig(rate_limit_pct=100.0)
        rng = random.Random(seed)
        injector = WebErrorInjector(config, rng=rng)

        for _ in range(200):
            d = injector.decide()
            assert d.should_inject, "100% rate should always inject"

    @given(seed=st.integers(min_value=0, max_value=2**32 - 1))
    @settings(max_examples=30)
    def test_100_pct_timeout_always_errors(self, seed: int) -> None:
        """Property: 100% timeout produces connection errors on every request."""
        config = WebErrorInjectionConfig(timeout_pct=100.0)
        rng = random.Random(seed)
        injector = WebErrorInjector(config, rng=rng)

        for _ in range(200):
            d = injector.decide()
            assert d.should_inject, "100% timeout should always inject"
            assert d.category == WebErrorCategory.CONNECTION
            assert d.error_type == "timeout"

    @given(seed=st.integers(min_value=0, max_value=2**32 - 1))
    @settings(max_examples=30)
    def test_100_pct_ssrf_redirect_always_errors(self, seed: int) -> None:
        """Property: 100% ssrf_redirect produces redirects on every request."""
        config = WebErrorInjectionConfig(ssrf_redirect_pct=100.0)
        rng = random.Random(seed)
        injector = WebErrorInjector(config, rng=rng)

        for _ in range(200):
            d = injector.decide()
            assert d.should_inject, "100% ssrf_redirect should always inject"
            assert d.category == WebErrorCategory.REDIRECT
            assert d.error_type == "ssrf_redirect"

    @given(seed=st.integers(min_value=0, max_value=2**32 - 1))
    @settings(max_examples=30)
    def test_100_pct_malformed_always_errors(self, seed: int) -> None:
        """Property: 100% wrong_content_type produces malformed on every request."""
        config = WebErrorInjectionConfig(wrong_content_type_pct=100.0)
        rng = random.Random(seed)
        injector = WebErrorInjector(config, rng=rng)

        for _ in range(200):
            d = injector.decide()
            assert d.should_inject, "100% malformed should always inject"
            assert d.category == WebErrorCategory.MALFORMED

    @given(
        rate=st.floats(min_value=10.0, max_value=90.0, allow_nan=False, allow_infinity=False),
        seed=st.integers(min_value=0, max_value=2**32 - 1),
    )
    @settings(max_examples=200)
    def test_single_error_type_rate_converges(self, rate: float, seed: int) -> None:
        """Property: Any single error type at rate N% fires ~N% of the time."""
        config = WebErrorInjectionConfig(forbidden_pct=rate)
        rng = random.Random(seed)
        injector = WebErrorInjector(config, rng=rng)

        n_trials = 1000
        errors = sum(1 for _ in range(n_trials) if injector.decide().should_inject)
        observed_rate = (errors / n_trials) * 100

        assert abs(observed_rate - rate) < 7.0, (
            f"Configured forbidden_pct={rate:.1f}%, observed={observed_rate:.1f}% over {n_trials} trials (seed={seed}). Margin exceeded."
        )


# =============================================================================
# WebErrorInjector Invariants
# =============================================================================


class TestInjectorInvariants:
    """Property tests for WebErrorInjector invariants."""

    @given(seed=st.integers(min_value=0, max_value=2**32 - 1))
    @settings(max_examples=50)
    def test_decide_never_returns_none(self, seed: int) -> None:
        """Property: decide() never returns None."""
        config = WebErrorInjectionConfig(
            rate_limit_pct=20.0,
            timeout_pct=10.0,
            wrong_content_type_pct=5.0,
            ssrf_redirect_pct=3.0,
        )
        rng = random.Random(seed)
        injector = WebErrorInjector(config, rng=rng)

        for _ in range(200):
            d = injector.decide()
            assert d is not None, "decide() must never return None"

    @given(seed=st.integers(min_value=0, max_value=2**32 - 1))
    @settings(max_examples=50)
    def test_every_decision_has_valid_category_or_is_success(self, seed: int) -> None:
        """Property: Every decision has a valid WebErrorCategory or is success."""
        config = WebErrorInjectionConfig(
            rate_limit_pct=15.0,
            timeout_pct=10.0,
            connection_reset_pct=5.0,
            wrong_content_type_pct=5.0,
            ssrf_redirect_pct=5.0,
            redirect_loop_pct=3.0,
            encoding_mismatch_pct=2.0,
        )
        rng = random.Random(seed)
        injector = WebErrorInjector(config, rng=rng)

        valid_categories = set(WebErrorCategory)
        for _ in range(300):
            d = injector.decide()
            if d.should_inject:
                assert d.category in valid_categories, f"Invalid category: {d.category}"
            else:
                assert d.category is None, "Success decision must have category=None"

    @given(seed=st.integers(min_value=0, max_value=2**32 - 1))
    @settings(max_examples=50)
    def test_retry_after_within_configured_range(self, seed: int) -> None:
        """Property: retry_after_sec is within configured range when present."""
        min_sec, max_sec = 5, 45
        config = WebErrorInjectionConfig(
            rate_limit_pct=100.0,
            retry_after_sec=(min_sec, max_sec),
        )
        rng = random.Random(seed)
        injector = WebErrorInjector(config, rng=rng)

        for _ in range(200):
            d = injector.decide()
            if d.retry_after_sec is not None:
                assert min_sec <= d.retry_after_sec <= max_sec, f"Retry-After {d.retry_after_sec} outside [{min_sec}, {max_sec}]"

    @given(
        min_sec=st.integers(min_value=1, max_value=10),
        max_sec=st.integers(min_value=10, max_value=120),
        seed=st.integers(min_value=0, max_value=2**32 - 1),
    )
    @settings(max_examples=100)
    def test_retry_after_bounds_parametric(self, min_sec: int, max_sec: int, seed: int) -> None:
        """Property: Retry-After values are always within [min, max] for any range."""
        config = WebErrorInjectionConfig(
            rate_limit_pct=100.0,
            retry_after_sec=(min_sec, max_sec),
        )
        rng = random.Random(seed)
        injector = WebErrorInjector(config, rng=rng)

        for _ in range(50):
            d = injector.decide()
            if d.retry_after_sec is not None:
                assert min_sec <= d.retry_after_sec <= max_sec

    @given(seed=st.integers(min_value=0, max_value=2**32 - 1))
    @settings(max_examples=50)
    def test_delay_sec_non_negative(self, seed: int) -> None:
        """Property: delay_sec is non-negative when present."""
        config = WebErrorInjectionConfig(
            timeout_pct=30.0,
            connection_stall_pct=30.0,
            slow_response_pct=30.0,
        )
        rng = random.Random(seed)
        injector = WebErrorInjector(config, rng=rng)

        for _ in range(300):
            d = injector.decide()
            if d.delay_sec is not None:
                assert d.delay_sec >= 0, f"Negative delay: {d.delay_sec}"

    @given(seed=st.integers(min_value=0, max_value=2**32 - 1))
    @settings(max_examples=50)
    def test_start_delay_sec_non_negative(self, seed: int) -> None:
        """Property: start_delay_sec is non-negative when present."""
        config = WebErrorInjectionConfig(connection_stall_pct=100.0)
        rng = random.Random(seed)
        injector = WebErrorInjector(config, rng=rng)

        for _ in range(200):
            d = injector.decide()
            if d.start_delay_sec is not None:
                assert d.start_delay_sec >= 0, f"Negative start_delay: {d.start_delay_sec}"

    @given(seed=st.integers(min_value=0, max_value=2**32 - 1))
    @settings(max_examples=50)
    def test_redirect_hops_at_least_one(self, seed: int) -> None:
        """Property: redirect hops is >= 1 when present."""
        config = WebErrorInjectionConfig(redirect_loop_pct=100.0)
        rng = random.Random(seed)
        injector = WebErrorInjector(config, rng=rng)

        for _ in range(200):
            d = injector.decide()
            if d.redirect_hops is not None:
                assert d.redirect_hops >= 1, f"Redirect hops < 1: {d.redirect_hops}"

    @given(seed=st.integers(min_value=0, max_value=2**32 - 1))
    @settings(max_examples=50)
    def test_ssrf_targets_from_target_list(self, seed: int) -> None:
        """Property: SSRF redirect targets are always from the SSRF_TARGETS list."""
        config = WebErrorInjectionConfig(ssrf_redirect_pct=100.0)
        rng = random.Random(seed)
        injector = WebErrorInjector(config, rng=rng)

        for _ in range(200):
            d = injector.decide()
            if d.redirect_target is not None:
                assert d.redirect_target in SSRF_TARGETS, f"SSRF target {d.redirect_target!r} not in SSRF_TARGETS list"

    @given(seed=st.integers(min_value=0, max_value=2**32 - 1))
    @settings(max_examples=50)
    def test_incomplete_bytes_positive(self, seed: int) -> None:
        """Property: incomplete_bytes is positive when present."""
        config = WebErrorInjectionConfig(incomplete_response_pct=100.0)
        rng = random.Random(seed)
        injector = WebErrorInjector(config, rng=rng)

        for _ in range(200):
            d = injector.decide()
            if d.incomplete_bytes is not None:
                assert d.incomplete_bytes > 0, f"incomplete_bytes <= 0: {d.incomplete_bytes}"


# =============================================================================
# Burst Timing Properties
# =============================================================================


class TestBurstTiming:
    """Property tests for burst state machine timing."""

    @given(
        interval=st.integers(min_value=10, max_value=120),
        duration=st.integers(min_value=1, max_value=9),
    )
    @settings(max_examples=50)
    def test_burst_timing_is_periodic(self, interval: int, duration: int) -> None:
        """Property: Bursts occur at regular intervals.

        At time 0, interval, 2*interval, etc. a burst starts.
        Each burst lasts for `duration` seconds.
        """
        effective_duration = min(duration, interval - 1)
        burst_config = WebBurstConfig(
            enabled=True,
            interval_sec=interval,
            duration_sec=effective_duration,
            rate_limit_pct=90.0,
        )
        config = WebErrorInjectionConfig(rate_limit_pct=5.0, burst=burst_config)

        clock_time = 0.0
        injector = WebErrorInjector(config, time_func=lambda: clock_time)

        # Check burst timing via the composed engine's state machine.
        clock_time = 0.1
        _ = injector._engine._get_elapsed()  # Initialize

        # t=0 -> in burst (start of first interval)
        assert injector._engine._check_burst(0.1)

        # t=effective_duration + 0.1 -> out of burst
        assert not injector._engine._check_burst(effective_duration + 0.1)

        # t=interval -> in burst (start of second interval)
        assert injector._engine._check_burst(float(interval))

        # t=interval + effective_duration + 0.1 -> out of burst
        assert not injector._engine._check_burst(float(interval) + effective_duration + 0.1)

    def test_burst_disabled_never_in_burst(self) -> None:
        """Property: Disabled burst means never in burst."""
        config = WebErrorInjectionConfig(
            burst=WebBurstConfig(enabled=False),
        )
        injector = WebErrorInjector(config)

        for t in [0.0, 5.0, 30.0, 100.0, 1000.0]:
            assert not injector._engine._check_burst(t)

    @given(seed=st.integers(min_value=0, max_value=2**32 - 1))
    @settings(max_examples=30)
    def test_burst_elevates_error_rate(self, seed: int) -> None:
        """Property: During burst, error rate increases to burst level."""
        burst_config = WebBurstConfig(
            enabled=True,
            interval_sec=100,
            duration_sec=50,
            rate_limit_pct=90.0,
        )
        config = WebErrorInjectionConfig(rate_limit_pct=5.0, burst=burst_config)

        # Time is during burst (t=10 within [0, 50] burst window)
        clock_time = 10.0
        rng = random.Random(seed)
        injector = WebErrorInjector(config, time_func=lambda: clock_time, rng=rng)

        n_trials = 500
        errors = sum(1 for _ in range(n_trials) if injector.decide().should_inject)
        observed = (errors / n_trials) * 100

        # During burst, rate should be ~90% (burst rate), not ~5% (base rate)
        assert observed > 50.0, f"During burst, expected high error rate (~90%), got {observed:.1f}%"

    @given(seed=st.integers(min_value=0, max_value=2**32 - 1))
    @settings(max_examples=30)
    def test_burst_forbidden_elevates(self, seed: int) -> None:
        """Property: During burst, forbidden rate increases to burst level."""
        burst_config = WebBurstConfig(
            enabled=True,
            interval_sec=100,
            duration_sec=50,
            rate_limit_pct=0.0,
            forbidden_pct=90.0,
        )
        config = WebErrorInjectionConfig(forbidden_pct=5.0, burst=burst_config)

        clock_time = 10.0
        rng = random.Random(seed)
        injector = WebErrorInjector(config, time_func=lambda: clock_time, rng=rng)

        n_trials = 500
        errors = sum(1 for _ in range(n_trials) if injector.decide().should_inject)
        observed = (errors / n_trials) * 100

        assert observed > 50.0, f"During burst, expected high forbidden rate (~90%), got {observed:.1f}%"

    @given(seed=st.integers(min_value=0, max_value=2**32 - 1))
    @settings(max_examples=30)
    def test_outside_burst_uses_base_rate(self, seed: int) -> None:
        """Property: Outside burst window, base rate is used.

        _get_current_time() records _start_time on the first call, then
        returns (current - _start_time). We use an advancing clock so that
        the first call sets _start_time=0 and all subsequent calls return
        elapsed=50, which is outside the [0, 10] burst window.
        """
        burst_config = WebBurstConfig(
            enabled=True,
            interval_sec=100,
            duration_sec=10,
            rate_limit_pct=90.0,
        )
        config = WebErrorInjectionConfig(rate_limit_pct=5.0, burst=burst_config)

        # Clock starts at 0 (sets _start_time=0), then jumps to 50 for all
        # subsequent calls so elapsed is always 50 (outside [0, 10] burst).
        call_count = 0

        def advancing_clock() -> float:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return 0.0  # _start_time initialization
            return 50.0  # elapsed = 50.0 - 0.0 = 50.0 (outside burst)

        rng = random.Random(seed)
        injector = WebErrorInjector(config, time_func=advancing_clock, rng=rng)

        n_trials = 500
        errors = sum(1 for _ in range(n_trials) if injector.decide().should_inject)
        observed = (errors / n_trials) * 100

        # Outside burst, rate should be ~5% (base rate), not ~90% (burst rate)
        assert observed < 20.0, f"Outside burst, expected low error rate (~5%), got {observed:.1f}%"


# =============================================================================
# Selection Mode Properties
# =============================================================================


class TestSelectionModes:
    """Property tests for priority vs weighted selection."""

    @given(seed=st.integers(min_value=0, max_value=2**32 - 1))
    @settings(max_examples=30)
    def test_priority_mode_connection_first(self, seed: int) -> None:
        """Property: In priority mode, connection errors take precedence over HTTP.

        When both timeout and rate_limit are at 100%,
        timeout should always win (connection errors are checked first).
        """
        config = WebErrorInjectionConfig(
            timeout_pct=100.0,
            rate_limit_pct=100.0,
            selection_mode="priority",
        )
        rng = random.Random(seed)
        injector = WebErrorInjector(config, rng=rng)

        for _ in range(100):
            d = injector.decide()
            assert d.error_type == "timeout", f"Priority mode: timeout should win over rate_limit, got {d.error_type}"

    @given(seed=st.integers(min_value=0, max_value=2**32 - 1))
    @settings(max_examples=30)
    def test_priority_mode_redirect_before_http(self, seed: int) -> None:
        """Property: In priority mode, redirects take precedence over HTTP errors.

        When both ssrf_redirect and rate_limit are at 100%,
        ssrf_redirect should always win (redirect checked before HTTP).
        """
        config = WebErrorInjectionConfig(
            ssrf_redirect_pct=100.0,
            rate_limit_pct=100.0,
            selection_mode="priority",
        )
        rng = random.Random(seed)
        injector = WebErrorInjector(config, rng=rng)

        for _ in range(100):
            d = injector.decide()
            assert d.error_type == "ssrf_redirect", f"Priority mode: ssrf_redirect should win over rate_limit, got {d.error_type}"

    @given(seed=st.integers(min_value=0, max_value=2**32 - 1))
    @settings(max_examples=30)
    def test_priority_mode_connection_before_redirect(self, seed: int) -> None:
        """Property: In priority mode, connection errors take precedence over redirects."""
        config = WebErrorInjectionConfig(
            timeout_pct=100.0,
            ssrf_redirect_pct=100.0,
            selection_mode="priority",
        )
        rng = random.Random(seed)
        injector = WebErrorInjector(config, rng=rng)

        for _ in range(100):
            d = injector.decide()
            assert d.error_type == "timeout", f"Priority mode: timeout should win over ssrf_redirect, got {d.error_type}"

    @given(seed=st.integers(min_value=0, max_value=2**32 - 1))
    @settings(max_examples=30)
    def test_priority_mode_http_before_malformed(self, seed: int) -> None:
        """Property: In priority mode, HTTP errors take precedence over malformations."""
        config = WebErrorInjectionConfig(
            rate_limit_pct=100.0,
            wrong_content_type_pct=100.0,
            selection_mode="priority",
        )
        rng = random.Random(seed)
        injector = WebErrorInjector(config, rng=rng)

        for _ in range(100):
            d = injector.decide()
            assert d.error_type == "rate_limit", f"Priority mode: rate_limit should win over wrong_content_type, got {d.error_type}"

    @given(seed=st.integers(min_value=0, max_value=2**32 - 1))
    @settings(max_examples=30)
    def test_weighted_mode_distributes(self, seed: int) -> None:
        """Property: Weighted mode distributes among multiple error types.

        With equal weights, both timeout and rate_limit should appear.
        """
        config = WebErrorInjectionConfig(
            timeout_pct=50.0,
            rate_limit_pct=50.0,
            selection_mode="weighted",
        )
        rng = random.Random(seed)
        injector = WebErrorInjector(config, rng=rng)

        seen_types: set[str | None] = set()
        for _ in range(500):
            d = injector.decide()
            if d.should_inject:
                seen_types.add(d.error_type)

        assert "timeout" in seen_types, "Weighted mode should produce timeout"
        assert "rate_limit" in seen_types, "Weighted mode should produce rate_limit"

    @given(seed=st.integers(min_value=0, max_value=2**32 - 1))
    @settings(max_examples=30)
    def test_weighted_mode_multiple_categories(self, seed: int) -> None:
        """Property: Weighted mode distributes across all error categories."""
        config = WebErrorInjectionConfig(
            timeout_pct=25.0,
            rate_limit_pct=25.0,
            wrong_content_type_pct=25.0,
            ssrf_redirect_pct=25.0,
            selection_mode="weighted",
        )
        rng = random.Random(seed)
        injector = WebErrorInjector(config, rng=rng)

        seen_categories: set[WebErrorCategory] = set()
        for _ in range(1000):
            d = injector.decide()
            if d.should_inject and d.category is not None:
                seen_categories.add(d.category)

        assert WebErrorCategory.CONNECTION in seen_categories
        assert WebErrorCategory.HTTP in seen_categories
        assert WebErrorCategory.MALFORMED in seen_categories
        assert WebErrorCategory.REDIRECT in seen_categories


# =============================================================================
# Config Validation Properties
# =============================================================================


class TestConfigValidation:
    """Property tests for WebErrorInjectionConfig validation."""

    @given(pct=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False))
    @settings(max_examples=100)
    def test_valid_percentage_accepted(self, pct: float) -> None:
        """Property: Any float 0-100 is accepted as a valid percentage."""
        config = WebErrorInjectionConfig(rate_limit_pct=pct)
        assert config.rate_limit_pct == pct

    @given(pct=st.floats(min_value=-100.0, max_value=-0.01, allow_nan=False, allow_infinity=False))
    @settings(max_examples=50)
    def test_negative_percentage_rejected(self, pct: float) -> None:
        """Property: Negative percentages are rejected."""
        with pytest.raises(Exception):  # noqa: B017 - Pydantic ValidationError
            WebErrorInjectionConfig(rate_limit_pct=pct)

    @given(pct=st.floats(min_value=100.01, max_value=1000.0, allow_nan=False, allow_infinity=False))
    @settings(max_examples=50)
    def test_percentage_over_100_rejected(self, pct: float) -> None:
        """Property: Percentages > 100 are rejected."""
        with pytest.raises(Exception):  # noqa: B017 - Pydantic ValidationError
            WebErrorInjectionConfig(rate_limit_pct=pct)

    @given(pct=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False))
    @settings(max_examples=50)
    def test_all_percentage_fields_accept_valid(self, pct: float) -> None:
        """Property: All percentage fields accept valid 0-100 float values."""
        config = WebErrorInjectionConfig(
            rate_limit_pct=pct,
            forbidden_pct=pct,
            not_found_pct=pct,
            gone_pct=pct,
            payment_required_pct=pct,
            unavailable_for_legal_pct=pct,
            service_unavailable_pct=pct,
            bad_gateway_pct=pct,
            gateway_timeout_pct=pct,
            internal_error_pct=pct,
            timeout_pct=pct,
            connection_reset_pct=pct,
            connection_stall_pct=pct,
            slow_response_pct=pct,
            incomplete_response_pct=pct,
            wrong_content_type_pct=pct,
            encoding_mismatch_pct=pct,
            truncated_html_pct=pct,
            invalid_encoding_pct=pct,
            charset_confusion_pct=pct,
            malformed_meta_pct=pct,
            redirect_loop_pct=pct,
            ssrf_redirect_pct=pct,
        )
        assert config.rate_limit_pct == pct

    def test_nan_percentage_rejected(self) -> None:
        """Property: NaN is rejected as a percentage value."""
        with pytest.raises(Exception):  # noqa: B017
            WebErrorInjectionConfig(rate_limit_pct=float("nan"))

    def test_infinity_percentage_rejected(self) -> None:
        """Property: Infinity is rejected as a percentage value."""
        with pytest.raises(Exception):  # noqa: B017
            WebErrorInjectionConfig(rate_limit_pct=float("inf"))

    def test_negative_infinity_percentage_rejected(self) -> None:
        """Property: Negative infinity is rejected as a percentage value."""
        with pytest.raises(Exception):  # noqa: B017
            WebErrorInjectionConfig(rate_limit_pct=float("-inf"))


# =============================================================================
# Determinism with Seeded RNG
# =============================================================================


class TestDeterminism:
    """Property tests for deterministic behavior with seeded RNG."""

    @given(seed=st.integers(min_value=0, max_value=2**32 - 1))
    @settings(max_examples=30)
    def test_same_seed_same_sequence(self, seed: int) -> None:
        """Property: Same seed produces identical decision sequence."""
        config = WebErrorInjectionConfig(
            rate_limit_pct=20.0,
            timeout_pct=10.0,
            wrong_content_type_pct=5.0,
            ssrf_redirect_pct=3.0,
        )

        clock_time = 0.0
        rng1 = random.Random(seed)
        injector1 = WebErrorInjector(config, time_func=lambda: clock_time, rng=rng1)

        rng2 = random.Random(seed)
        injector2 = WebErrorInjector(config, time_func=lambda: clock_time, rng=rng2)

        for i in range(200):
            d1 = injector1.decide()
            d2 = injector2.decide()
            assert d1.error_type == d2.error_type, f"Diverged at request {i}: {d1.error_type} != {d2.error_type} (seed={seed})"
            assert d1.category == d2.category
            assert d1.status_code == d2.status_code

    @given(seed=st.integers(min_value=0, max_value=2**32 - 1))
    @settings(max_examples=30)
    def test_same_seed_same_sequence_weighted(self, seed: int) -> None:
        """Property: Same seed produces identical sequence in weighted mode."""
        config = WebErrorInjectionConfig(
            rate_limit_pct=20.0,
            timeout_pct=15.0,
            wrong_content_type_pct=10.0,
            selection_mode="weighted",
        )

        clock_time = 0.0
        rng1 = random.Random(seed)
        injector1 = WebErrorInjector(config, time_func=lambda: clock_time, rng=rng1)

        rng2 = random.Random(seed)
        injector2 = WebErrorInjector(config, time_func=lambda: clock_time, rng=rng2)

        for i in range(200):
            d1 = injector1.decide()
            d2 = injector2.decide()
            assert d1.error_type == d2.error_type, (
                f"Weighted mode diverged at request {i}: {d1.error_type} != {d2.error_type} (seed={seed})"
            )


# =============================================================================
# Error Constants Consistency
# =============================================================================


class TestErrorConstants:
    """Property tests for error type constant consistency."""

    def test_http_errors_have_valid_status_codes(self) -> None:
        """Property: All HTTP error status codes are valid HTTP error codes (4xx/5xx)."""
        for error_type, code in WEB_HTTP_ERRORS.items():
            assert 400 <= code <= 599, f"{error_type} has invalid code {code}"

    def test_connection_errors_non_empty(self) -> None:
        """Property: WEB_CONNECTION_ERRORS set is non-empty."""
        assert len(WEB_CONNECTION_ERRORS) > 0

    def test_malformed_types_non_empty(self) -> None:
        """Property: WEB_MALFORMED_TYPES set is non-empty."""
        assert len(WEB_MALFORMED_TYPES) > 0

    def test_redirect_types_non_empty(self) -> None:
        """Property: WEB_REDIRECT_TYPES set is non-empty."""
        assert len(WEB_REDIRECT_TYPES) > 0

    def test_ssrf_targets_non_empty(self) -> None:
        """Property: SSRF_TARGETS list is non-empty."""
        assert len(SSRF_TARGETS) > 0

    def test_no_overlap_between_error_sets(self) -> None:
        """Property: Error type sets are disjoint."""
        http_types = set(WEB_HTTP_ERRORS.keys())
        assert http_types.isdisjoint(WEB_CONNECTION_ERRORS), f"HTTP/CONNECTION overlap: {http_types & WEB_CONNECTION_ERRORS}"
        assert http_types.isdisjoint(WEB_MALFORMED_TYPES), f"HTTP/MALFORMED overlap: {http_types & WEB_MALFORMED_TYPES}"
        assert http_types.isdisjoint(WEB_REDIRECT_TYPES), f"HTTP/REDIRECT overlap: {http_types & WEB_REDIRECT_TYPES}"
        assert WEB_CONNECTION_ERRORS.isdisjoint(WEB_MALFORMED_TYPES), (
            f"CONNECTION/MALFORMED overlap: {WEB_CONNECTION_ERRORS & WEB_MALFORMED_TYPES}"
        )
        assert WEB_CONNECTION_ERRORS.isdisjoint(WEB_REDIRECT_TYPES), (
            f"CONNECTION/REDIRECT overlap: {WEB_CONNECTION_ERRORS & WEB_REDIRECT_TYPES}"
        )
        assert WEB_MALFORMED_TYPES.isdisjoint(WEB_REDIRECT_TYPES), f"MALFORMED/REDIRECT overlap: {WEB_MALFORMED_TYPES & WEB_REDIRECT_TYPES}"

    def test_ssrf_targets_are_all_urls(self) -> None:
        """Property: All SSRF targets start with http:// or https://."""
        for target in SSRF_TARGETS:
            assert target.startswith("http://") or target.startswith("https://"), f"SSRF target is not a URL: {target!r}"

    def test_ssrf_targets_no_duplicates(self) -> None:
        """Property: SSRF_TARGETS list has no duplicates."""
        assert len(SSRF_TARGETS) == len(set(SSRF_TARGETS)), "SSRF_TARGETS contains duplicates"
