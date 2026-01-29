# tests/property/engine/test_retry_properties.py
"""Property-based tests for retry configuration.

These tests verify that RetryConfig correctly validates configurations
and factory methods produce valid configs.

Properties tested:
1. Valid configs are accepted
2. Invalid configs are rejected
3. Factory methods produce valid configs
4. Coercion at trust boundary (from_policy) handles bad data
"""

from __future__ import annotations

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from elspeth.engine.retry import RetryConfig
from tests.property.conftest import valid_delays, valid_jitter, valid_max_attempts


class TestRetryConfigValidationProperties:
    """Property tests for RetryConfig validation."""

    @given(
        max_attempts=valid_max_attempts,
        base_delay=valid_delays,
        max_delay=valid_delays,
        jitter=valid_jitter,
    )
    @settings(max_examples=300)
    def test_valid_config_construction(
        self,
        max_attempts: int,
        base_delay: float,
        max_delay: float,
        jitter: float,
    ) -> None:
        """Property: Valid configs construct without error."""
        config = RetryConfig(
            max_attempts=max_attempts,
            base_delay=base_delay,
            max_delay=max_delay,
            jitter=jitter,
        )

        assert config.max_attempts == max_attempts
        assert config.base_delay == base_delay
        assert config.max_delay == max_delay
        assert config.jitter == jitter

    @given(max_attempts=st.integers(max_value=0))
    @settings(max_examples=50)
    def test_invalid_max_attempts_rejected(self, max_attempts: int) -> None:
        """Property: max_attempts < 1 is rejected."""
        with pytest.raises(ValueError, match="max_attempts must be >= 1"):
            RetryConfig(max_attempts=max_attempts)

    @given(
        max_attempts=valid_max_attempts,
        base_delay=valid_delays,
        max_delay=valid_delays,
        jitter=valid_jitter,
    )
    @settings(max_examples=100)
    def test_config_fields_are_immutable_readable(
        self,
        max_attempts: int,
        base_delay: float,
        max_delay: float,
        jitter: float,
    ) -> None:
        """Property: Config fields are readable after construction."""
        config = RetryConfig(
            max_attempts=max_attempts,
            base_delay=base_delay,
            max_delay=max_delay,
            jitter=jitter,
        )

        # All fields must be readable
        _ = config.max_attempts
        _ = config.base_delay
        _ = config.max_delay
        _ = config.jitter


class TestRetryConfigFactoryProperties:
    """Property tests for RetryConfig factory methods."""

    def test_no_retry_is_single_attempt(self) -> None:
        """Property: no_retry() produces single-attempt config."""
        config = RetryConfig.no_retry()

        assert config.max_attempts == 1, f"no_retry() should have max_attempts=1, got {config.max_attempts}"

    @given(
        max_attempts=st.integers(min_value=-100, max_value=100),
        base_delay=st.floats(min_value=-100.0, max_value=100.0, allow_nan=False, allow_infinity=False),
        max_delay=st.floats(min_value=-100.0, max_value=100.0, allow_nan=False, allow_infinity=False),
        jitter=st.floats(min_value=-100.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=200)
    def test_from_policy_always_produces_valid_config(
        self,
        max_attempts: int,
        base_delay: float,
        max_delay: float,
        jitter: float,
    ) -> None:
        """Property: from_policy() always produces valid config, even with bad input.

        This is a trust boundary - external policy config may have invalid values.
        The factory must coerce to valid values without crashing.
        """
        policy = {
            "max_attempts": max_attempts,
            "base_delay": base_delay,
            "max_delay": max_delay,
            "jitter": jitter,
        }

        # Should NOT raise, even with invalid inputs
        config = RetryConfig.from_policy(policy)

        # Result must be valid
        assert config.max_attempts >= 1, "max_attempts must be >= 1 after coercion"
        assert config.base_delay >= 0.01, "base_delay must be >= 0.01 after coercion"
        assert config.max_delay >= 0.1, "max_delay must be >= 0.1 after coercion"
        assert config.jitter >= 0.0, "jitter must be >= 0.0 after coercion"

    def test_from_policy_none_returns_no_retry(self) -> None:
        """Property: from_policy(None) returns no-retry config."""
        config = RetryConfig.from_policy(None)

        assert config.max_attempts == 1, f"from_policy(None) should return no_retry (max_attempts=1), got {config.max_attempts}"

    @given(policy=st.fixed_dictionaries({}))
    @settings(max_examples=10)
    def test_from_policy_empty_dict_uses_defaults(self, policy: dict) -> None:
        """Property: from_policy({}) uses sensible defaults."""
        config = RetryConfig.from_policy(policy)

        # Should have default values
        assert config.max_attempts >= 1
        assert config.base_delay > 0
        assert config.max_delay > 0
        assert config.jitter >= 0

    @given(
        max_attempts=valid_max_attempts,
        base_delay=valid_delays,
        max_delay=valid_delays,
        jitter=valid_jitter,
    )
    @settings(max_examples=100)
    def test_from_policy_preserves_valid_values(
        self,
        max_attempts: int,
        base_delay: float,
        max_delay: float,
        jitter: float,
    ) -> None:
        """Property: from_policy() preserves valid input values."""
        # Ensure values are above coercion thresholds
        assume(max_attempts >= 1)
        assume(base_delay >= 0.01)
        assume(max_delay >= 0.1)
        assume(jitter >= 0.0)

        policy = {
            "max_attempts": max_attempts,
            "base_delay": base_delay,
            "max_delay": max_delay,
            "jitter": jitter,
        }

        config = RetryConfig.from_policy(policy)

        # Valid values should be preserved (not coerced)
        assert config.max_attempts == max_attempts
        assert config.base_delay == base_delay
        assert config.max_delay == max_delay
        assert config.jitter == jitter


class TestRetryConfigCoercionProperties:
    """Property tests for trust boundary coercion in from_policy()."""

    @given(bad_max_attempts=st.integers(max_value=0))
    @settings(max_examples=50)
    def test_negative_max_attempts_coerced_to_minimum(self, bad_max_attempts: int) -> None:
        """Property: Negative/zero max_attempts coerced to 1."""
        policy = {"max_attempts": bad_max_attempts}
        config = RetryConfig.from_policy(policy)

        assert config.max_attempts >= 1, f"Bad max_attempts {bad_max_attempts} should coerce to >= 1, got {config.max_attempts}"

    @given(bad_base_delay=st.floats(max_value=0.0, allow_nan=False, allow_infinity=False))
    @settings(max_examples=50)
    def test_negative_base_delay_coerced_to_minimum(self, bad_base_delay: float) -> None:
        """Property: Negative/zero base_delay coerced to minimum."""
        policy = {"base_delay": bad_base_delay}
        config = RetryConfig.from_policy(policy)

        assert config.base_delay >= 0.01, f"Bad base_delay {bad_base_delay} should coerce to >= 0.01, got {config.base_delay}"

    @given(bad_jitter=st.floats(max_value=-0.01, allow_nan=False, allow_infinity=False))
    @settings(max_examples=50)
    def test_negative_jitter_coerced_to_zero(self, bad_jitter: float) -> None:
        """Property: Negative jitter coerced to 0."""
        policy = {"jitter": bad_jitter}
        config = RetryConfig.from_policy(policy)

        assert config.jitter >= 0.0, f"Bad jitter {bad_jitter} should coerce to >= 0.0, got {config.jitter}"
