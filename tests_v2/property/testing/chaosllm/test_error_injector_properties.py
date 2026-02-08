# tests_v2/property/testing/chaosllm/test_error_injector_properties.py
"""Property-based tests for ChaosLLM ErrorInjector.

The ErrorInjector is the core decision engine for ChaosLLM's fault injection.
It has ZERO unit or property tests — only integration tests through the full
HTTP server. This module tests the critical invariants:

- Error rate statistical accuracy over N trials
- Burst timing periodicity (deterministic with injectable time_func)
- ErrorDecision factory method invariants (frozen, correct categories)
- Retry-After values within configured range
- Delay calculations are non-negative
- Priority vs weighted selection mode behavior
"""

from __future__ import annotations

import random

from hypothesis import given, settings
from hypothesis import strategies as st

from elspeth.testing.chaosllm.config import BurstConfig, ErrorInjectionConfig
from elspeth.testing.chaosllm.error_injector import (
    CONNECTION_ERRORS,
    HTTP_ERRORS,
    MALFORMED_TYPES,
    ErrorCategory,
    ErrorDecision,
    ErrorInjector,
)


# =============================================================================
# ErrorDecision Dataclass Properties
# =============================================================================


class TestErrorDecisionFactories:
    """Property tests for ErrorDecision factory methods."""

    def test_success_has_no_error(self) -> None:
        """Property: success() produces a non-injecting decision."""
        d = ErrorDecision.success()
        assert not d.should_inject
        assert d.error_type is None
        assert d.category is None
        assert d.status_code is None

    @given(
        error_type=st.sampled_from(list(HTTP_ERRORS.keys())),
        status_code=st.sampled_from(list(HTTP_ERRORS.values())),
    )
    def test_http_error_has_correct_category(self, error_type: str, status_code: int) -> None:
        """Property: http_error() always has HTTP category."""
        d = ErrorDecision.http_error(error_type, status_code)
        assert d.should_inject
        assert d.category == ErrorCategory.HTTP
        assert d.status_code == status_code
        assert d.error_type == error_type
        assert not d.is_connection_level
        assert not d.is_malformed

    @given(error_type=st.sampled_from(sorted(CONNECTION_ERRORS)))
    def test_connection_error_has_correct_category(self, error_type: str) -> None:
        """Property: connection_error() always has CONNECTION category."""
        d = ErrorDecision.connection_error(error_type)
        assert d.should_inject
        assert d.category == ErrorCategory.CONNECTION
        assert d.is_connection_level
        assert not d.is_malformed

    @given(malformed_type=st.sampled_from(sorted(MALFORMED_TYPES)))
    def test_malformed_has_correct_category(self, malformed_type: str) -> None:
        """Property: malformed_response() has MALFORMED category and status 200."""
        d = ErrorDecision.malformed_response(malformed_type)
        assert d.should_inject
        assert d.category == ErrorCategory.MALFORMED
        assert d.status_code == 200
        assert d.is_malformed
        assert not d.is_connection_level
        assert d.malformed_type == malformed_type


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
        """Property: Over 2000 trials, rate_limit rate is within ±5% of configured."""
        config = ErrorInjectionConfig(rate_limit_pct=rate)
        rng = random.Random(seed)
        injector = ErrorInjector(config, rng=rng)

        n_trials = 2000
        errors = sum(1 for _ in range(n_trials) if injector.decide().should_inject)
        observed_rate = (errors / n_trials) * 100

        # Allow ±5 percentage points margin for statistical fluctuation
        assert abs(observed_rate - rate) < 5.0, (
            f"Configured rate={rate:.1f}%, observed={observed_rate:.1f}% "
            f"over {n_trials} trials (seed={seed}). Margin exceeded."
        )

    @given(seed=st.integers(min_value=0, max_value=2**32 - 1))
    @settings(max_examples=30)
    def test_zero_rate_produces_no_errors(self, seed: int) -> None:
        """Property: 0% error rate produces zero errors."""
        config = ErrorInjectionConfig()  # All rates default to 0.0
        rng = random.Random(seed)
        injector = ErrorInjector(config, rng=rng)

        for _ in range(500):
            d = injector.decide()
            assert not d.should_inject, "0% rate should never inject errors"

    @given(seed=st.integers(min_value=0, max_value=2**32 - 1))
    @settings(max_examples=30)
    def test_100_pct_rate_always_errors(self, seed: int) -> None:
        """Property: 100% rate_limit produces errors on every request."""
        config = ErrorInjectionConfig(rate_limit_pct=100.0)
        rng = random.Random(seed)
        injector = ErrorInjector(config, rng=rng)

        for _ in range(200):
            d = injector.decide()
            assert d.should_inject, "100% rate should always inject"


# =============================================================================
# Retry-After Range Bounds
# =============================================================================


class TestRetryAfterBounds:
    """Property tests for Retry-After header values."""

    @given(
        min_sec=st.integers(min_value=1, max_value=10),
        max_sec=st.integers(min_value=10, max_value=60),
        seed=st.integers(min_value=0, max_value=2**32 - 1),
    )
    @settings(max_examples=100)
    def test_retry_after_within_range(self, min_sec: int, max_sec: int, seed: int) -> None:
        """Property: Retry-After values are always within [min, max]."""
        config = ErrorInjectionConfig(
            rate_limit_pct=100.0,
            retry_after_sec=(min_sec, max_sec),
        )
        rng = random.Random(seed)
        injector = ErrorInjector(config, rng=rng)

        for _ in range(100):
            d = injector.decide()
            if d.retry_after_sec is not None:
                assert min_sec <= d.retry_after_sec <= max_sec, (
                    f"Retry-After {d.retry_after_sec} outside [{min_sec}, {max_sec}]"
                )


# =============================================================================
# Delay Non-Negativity
# =============================================================================


class TestDelayBounds:
    """Property tests for delay calculations."""

    @given(seed=st.integers(min_value=0, max_value=2**32 - 1))
    @settings(max_examples=50)
    def test_timeout_delay_non_negative(self, seed: int) -> None:
        """Property: Timeout delays are never negative."""
        config = ErrorInjectionConfig(timeout_pct=100.0, timeout_sec=(1, 30))
        rng = random.Random(seed)
        injector = ErrorInjector(config, rng=rng)

        for _ in range(100):
            d = injector.decide()
            if d.delay_sec is not None:
                assert d.delay_sec >= 0, f"Negative delay: {d.delay_sec}"

    @given(seed=st.integers(min_value=0, max_value=2**32 - 1))
    @settings(max_examples=50)
    def test_connection_stall_delays_non_negative(self, seed: int) -> None:
        """Property: Connection stall delays are never negative."""
        config = ErrorInjectionConfig(
            connection_stall_pct=100.0,
            connection_stall_sec=(1, 30),
            connection_stall_start_sec=(0, 5),
        )
        rng = random.Random(seed)
        injector = ErrorInjector(config, rng=rng)

        for _ in range(100):
            d = injector.decide()
            if d.delay_sec is not None:
                assert d.delay_sec >= 0
            if d.start_delay_sec is not None:
                assert d.start_delay_sec >= 0


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
        burst_config = BurstConfig(
            enabled=True,
            interval_sec=interval,
            duration_sec=min(duration, interval - 1),
            rate_limit_pct=90.0,
        )
        config = ErrorInjectionConfig(rate_limit_pct=5.0, burst=burst_config)
        effective_duration = min(duration, interval - 1)

        # Simulate a clock
        clock_time = 0.0
        injector = ErrorInjector(config, time_func=lambda: clock_time)

        # Check at specific times
        # t=0 → in burst (start of first interval)
        clock_time = 0.1
        _ = injector._get_current_time()  # Initialize
        assert injector._is_in_burst(0.1)

        # t=effective_duration + 0.1 → out of burst
        assert not injector._is_in_burst(effective_duration + 0.1)

        # t=interval → in burst (start of second interval)
        assert injector._is_in_burst(float(interval))

        # t=interval + effective_duration + 0.1 → out of burst
        assert not injector._is_in_burst(float(interval) + effective_duration + 0.1)

    def test_burst_disabled_never_in_burst(self) -> None:
        """Property: Disabled burst means never in burst."""
        config = ErrorInjectionConfig(
            burst=BurstConfig(enabled=False),
        )
        injector = ErrorInjector(config)

        for t in [0.0, 5.0, 30.0, 100.0, 1000.0]:
            assert not injector._is_in_burst(t)

    @given(seed=st.integers(min_value=0, max_value=2**32 - 1))
    @settings(max_examples=30)
    def test_burst_elevates_error_rate(self, seed: int) -> None:
        """Property: During burst, error rate increases to burst level."""
        burst_config = BurstConfig(
            enabled=True,
            interval_sec=100,
            duration_sec=50,
            rate_limit_pct=90.0,
        )
        config = ErrorInjectionConfig(rate_limit_pct=5.0, burst=burst_config)

        # Time is during burst (t=10 within [0, 50] burst window)
        clock_time = 10.0
        rng = random.Random(seed)
        injector = ErrorInjector(config, time_func=lambda: clock_time, rng=rng)

        n_trials = 500
        errors = sum(1 for _ in range(n_trials) if injector.decide().should_inject)
        observed = (errors / n_trials) * 100

        # During burst, rate should be ~90% (burst rate), not ~5% (base rate)
        assert observed > 50.0, (
            f"During burst, expected high error rate (~90%), got {observed:.1f}%"
        )


# =============================================================================
# Selection Mode Properties
# =============================================================================


class TestSelectionModes:
    """Property tests for priority vs weighted selection."""

    @given(seed=st.integers(min_value=0, max_value=2**32 - 1))
    @settings(max_examples=30)
    def test_priority_mode_connection_first(self, seed: int) -> None:
        """Property: In priority mode, connection errors take precedence.

        When both connection_failed and rate_limit are at 100%,
        connection_failed should always win (it's checked first).
        """
        config = ErrorInjectionConfig(
            connection_failed_pct=100.0,
            rate_limit_pct=100.0,
            selection_mode="priority",
        )
        rng = random.Random(seed)
        injector = ErrorInjector(config, rng=rng)

        for _ in range(100):
            d = injector.decide()
            assert d.error_type == "connection_failed", (
                f"Priority mode: connection_failed should win over rate_limit, "
                f"got {d.error_type}"
            )

    @given(seed=st.integers(min_value=0, max_value=2**32 - 1))
    @settings(max_examples=30)
    def test_weighted_mode_distributes(self, seed: int) -> None:
        """Property: Weighted mode distributes among multiple error types.

        With equal weights, both connection_failed and rate_limit should appear.
        """
        config = ErrorInjectionConfig(
            connection_failed_pct=50.0,
            rate_limit_pct=50.0,
            selection_mode="weighted",
        )
        rng = random.Random(seed)
        injector = ErrorInjector(config, rng=rng)

        seen_types: set[str | None] = set()
        for _ in range(500):
            d = injector.decide()
            if d.should_inject:
                seen_types.add(d.error_type)

        assert "connection_failed" in seen_types, "Weighted mode should produce connection_failed"
        assert "rate_limit" in seen_types, "Weighted mode should produce rate_limit"


# =============================================================================
# Determinism with Seeded RNG
# =============================================================================


class TestDeterminism:
    """Property tests for deterministic behavior with seeded RNG."""

    @given(seed=st.integers(min_value=0, max_value=2**32 - 1))
    @settings(max_examples=30)
    def test_same_seed_same_sequence(self, seed: int) -> None:
        """Property: Same seed produces identical decision sequence."""
        config = ErrorInjectionConfig(
            rate_limit_pct=30.0,
            timeout_pct=10.0,
            invalid_json_pct=5.0,
        )

        clock_time = 0.0
        rng1 = random.Random(seed)
        injector1 = ErrorInjector(config, time_func=lambda: clock_time, rng=rng1)

        rng2 = random.Random(seed)
        injector2 = ErrorInjector(config, time_func=lambda: clock_time, rng=rng2)

        for i in range(200):
            d1 = injector1.decide()
            d2 = injector2.decide()
            assert d1.error_type == d2.error_type, (
                f"Diverged at request {i}: {d1.error_type} != {d2.error_type} (seed={seed})"
            )
            assert d1.category == d2.category


# =============================================================================
# HTTP_ERRORS / CONNECTION_ERRORS / MALFORMED_TYPES Constants
# =============================================================================


class TestErrorConstants:
    """Property tests for error type constant consistency."""

    def test_http_errors_have_valid_status_codes(self) -> None:
        """Property: All HTTP error status codes are valid HTTP error codes."""
        for error_type, code in HTTP_ERRORS.items():
            assert 400 <= code <= 599, f"{error_type} has invalid code {code}"

    def test_connection_errors_non_empty(self) -> None:
        """Property: CONNECTION_ERRORS set is non-empty."""
        assert len(CONNECTION_ERRORS) > 0

    def test_malformed_types_non_empty(self) -> None:
        """Property: MALFORMED_TYPES set is non-empty."""
        assert len(MALFORMED_TYPES) > 0

    def test_no_overlap_between_sets(self) -> None:
        """Property: Error type sets are disjoint."""
        http_types = set(HTTP_ERRORS.keys())
        assert http_types.isdisjoint(CONNECTION_ERRORS)
        assert http_types.isdisjoint(MALFORMED_TYPES)
        assert CONNECTION_ERRORS.isdisjoint(MALFORMED_TYPES)
