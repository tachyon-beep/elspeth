# tests/property/testing/chaosllm/test_metrics_config_properties.py
"""Property-based tests for ChaosLLM metrics functions and config validation.

Tests the invariants of:
- _get_bucket_utc: time bucketing alignment and idempotency
- _classify_outcome: exhaustive and mutually exclusive classification
- Config validation: range constraints, percentage bounds, deep merge
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from elspeth.testing.chaosengine.metrics_store import _get_bucket_utc
from elspeth.testing.chaosllm.config import (
    ChaosLLMConfig,
    ErrorInjectionConfig,
    LatencyConfig,
    RandomResponseConfig,
    ServerConfig,
    _deep_merge,
)
from elspeth.testing.chaosllm.metrics import _classify_outcome

# =============================================================================
# _get_bucket_utc Properties
# =============================================================================


class TestGetBucketUtc:
    """Property tests for time bucket alignment."""

    @given(
        hour=st.integers(min_value=0, max_value=23),
        minute=st.integers(min_value=0, max_value=59),
        second=st.integers(min_value=0, max_value=59),
        bucket_sec=st.sampled_from([1, 5, 10, 15, 30, 60, 300, 900, 3600]),
    )
    @settings(max_examples=200)
    def test_bucket_is_aligned(self, hour: int, minute: int, second: int, bucket_sec: int) -> None:
        """Property: Bucket timestamp is aligned to bucket_sec boundary."""
        ts = f"2024-06-15T{hour:02d}:{minute:02d}:{second:02d}+00:00"
        bucket = _get_bucket_utc(ts, bucket_sec)

        bucket_dt = datetime.fromisoformat(bucket)
        total_seconds = bucket_dt.hour * 3600 + bucket_dt.minute * 60 + bucket_dt.second
        assert total_seconds % bucket_sec == 0, f"Bucket {bucket} not aligned to {bucket_sec}s boundary"

    @given(
        hour=st.integers(min_value=0, max_value=23),
        minute=st.integers(min_value=0, max_value=59),
        second=st.integers(min_value=0, max_value=59),
        bucket_sec=st.sampled_from([1, 5, 10, 30, 60, 300]),
    )
    @settings(max_examples=200)
    def test_bucket_idempotent(self, hour: int, minute: int, second: int, bucket_sec: int) -> None:
        """Property: Bucketing a bucket timestamp returns the same bucket."""
        ts = f"2024-06-15T{hour:02d}:{minute:02d}:{second:02d}+00:00"
        bucket1 = _get_bucket_utc(ts, bucket_sec)
        bucket2 = _get_bucket_utc(bucket1, bucket_sec)
        assert bucket1 == bucket2, f"Not idempotent: {bucket1} -> {bucket2}"

    @given(
        hour=st.integers(min_value=0, max_value=23),
        minute=st.integers(min_value=0, max_value=59),
        second=st.integers(min_value=0, max_value=59),
        bucket_sec=st.sampled_from([1, 5, 10, 30, 60, 300]),
    )
    @settings(max_examples=200)
    def test_bucket_does_not_exceed_timestamp(self, hour: int, minute: int, second: int, bucket_sec: int) -> None:
        """Property: Bucket timestamp is <= original timestamp (truncation, not rounding)."""
        ts = f"2024-06-15T{hour:02d}:{minute:02d}:{second:02d}+00:00"
        bucket = _get_bucket_utc(ts, bucket_sec)

        original_dt = datetime.fromisoformat(ts)
        bucket_dt = datetime.fromisoformat(bucket)
        assert bucket_dt <= original_dt, f"Bucket {bucket} exceeds original {ts}"

    @given(
        hour=st.integers(min_value=0, max_value=23),
        minute=st.integers(min_value=0, max_value=59),
        second=st.integers(min_value=0, max_value=59),
        bucket_sec=st.sampled_from([1, 5, 10, 30, 60, 300]),
    )
    @settings(max_examples=200)
    def test_timestamp_within_one_bucket_of_result(self, hour: int, minute: int, second: int, bucket_sec: int) -> None:
        """Property: Original timestamp is within one bucket_sec of the bucket."""
        ts = f"2024-06-15T{hour:02d}:{minute:02d}:{second:02d}+00:00"
        bucket = _get_bucket_utc(ts, bucket_sec)

        original_dt = datetime.fromisoformat(ts)
        bucket_dt = datetime.fromisoformat(bucket)

        diff = (original_dt - bucket_dt).total_seconds()
        assert 0 <= diff < bucket_sec, f"Diff {diff}s not in [0, {bucket_sec}): ts={ts}, bucket={bucket}"


# =============================================================================
# _classify_outcome Properties
# =============================================================================


class TestClassifyOutcome:
    """Property tests for outcome classification."""

    @given(
        status_code=st.one_of(
            st.just(None),
            st.integers(min_value=200, max_value=599),
        ),
        error_type=st.one_of(
            st.just(None),
            st.sampled_from(
                [
                    "timeout",
                    "connection_failed",
                    "connection_stall",
                    "connection_reset",
                    "rate_limit",
                    "unknown",
                ]
            ),
        ),
        outcome=st.sampled_from(["success", "error_injected", "error_malformed"]),
    )
    @settings(max_examples=200)
    def test_classification_returns_seven_booleans(self, status_code: int | None, error_type: str | None, outcome: str) -> None:
        """Property: _classify_outcome always returns exactly 7 booleans."""
        result = _classify_outcome(outcome, status_code, error_type)
        assert len(result) == 7
        assert all(isinstance(v, bool) for v in result)

    def test_success_outcome_sets_success_flag(self) -> None:
        """Property: outcome='success' sets is_success=True."""
        result = _classify_outcome("success", 200, None)
        assert result[0] is True  # is_success

    @given(status_code=st.integers(min_value=400, max_value=428))
    def test_4xx_not_429_is_client_error(self, status_code: int) -> None:
        """Property: 4xx (not 429) classified as client_error."""
        result = _classify_outcome("error_injected", status_code, None)
        is_client_error = result[4]
        assert is_client_error is True, f"Status {status_code} should be client_error"

    def test_429_is_rate_limited_not_client(self) -> None:
        """Property: 429 is rate_limited, not client_error."""
        result = _classify_outcome("error_injected", 429, None)
        is_rate_limited = result[1]
        is_client_error = result[4]
        assert is_rate_limited is True
        assert is_client_error is False

    def test_529_is_capacity_not_server(self) -> None:
        """Property: 529 is capacity_error, not server_error."""
        result = _classify_outcome("error_injected", 529, None)
        is_capacity = result[2]
        is_server = result[3]
        assert is_capacity is True
        assert is_server is False

    @given(status_code=st.integers(min_value=500, max_value=528))
    def test_5xx_not_529_is_server_error(self, status_code: int) -> None:
        """Property: 5xx (not 529) classified as server_error."""
        result = _classify_outcome("error_injected", status_code, None)
        is_server_error = result[3]
        assert is_server_error is True, f"Status {status_code} should be server_error"

    @given(
        error_type=st.sampled_from(
            [
                "timeout",
                "connection_failed",
                "connection_stall",
                "connection_reset",
            ]
        )
    )
    def test_connection_errors_classified(self, error_type: str) -> None:
        """Property: Connection error types with no status code are connection_error."""
        result = _classify_outcome("error_injected", None, error_type)
        is_connection = result[5]
        assert is_connection is True, f"{error_type} should be connection_error"

    def test_malformed_outcome_classified(self) -> None:
        """Property: outcome='error_malformed' sets is_malformed=True."""
        result = _classify_outcome("error_malformed", 200, None)
        is_malformed = result[6]
        assert is_malformed is True


# =============================================================================
# Config Validation Properties
# =============================================================================


class TestConfigRangeValidation:
    """Property tests for config range [min, max] validation."""

    @given(
        min_val=st.integers(min_value=10, max_value=100),
        max_val=st.integers(min_value=1, max_value=9),
    )
    @settings(max_examples=50)
    def test_retry_after_rejects_min_gt_max(self, min_val: int, max_val: int) -> None:
        """Property: retry_after_sec rejects min > max."""
        with pytest.raises(ValidationError):
            ErrorInjectionConfig(retry_after_sec=(min_val, max_val))

    @given(
        min_val=st.integers(min_value=1, max_value=50),
        max_val=st.integers(min_value=50, max_value=100),
    )
    @settings(max_examples=50)
    def test_retry_after_accepts_min_leq_max(self, min_val: int, max_val: int) -> None:
        """Property: retry_after_sec accepts min <= max."""
        config = ErrorInjectionConfig(retry_after_sec=(min_val, max_val))
        assert config.retry_after_sec == (min_val, max_val)

    @given(
        min_val=st.integers(min_value=60, max_value=120),
        max_val=st.integers(min_value=1, max_value=29),
    )
    @settings(max_examples=50)
    def test_timeout_sec_rejects_min_gt_max(self, min_val: int, max_val: int) -> None:
        """Property: timeout_sec rejects min > max."""
        with pytest.raises(ValidationError):
            ErrorInjectionConfig(timeout_sec=(min_val, max_val))


class TestConfigPercentageBounds:
    """Property tests for percentage field bounds [0, 100]."""

    @given(value=st.floats(min_value=101.0, max_value=1000.0, allow_nan=False, allow_infinity=False))
    @settings(max_examples=50)
    def test_rate_limit_pct_rejects_above_100(self, value: float) -> None:
        """Property: Percentages above 100 are rejected."""
        with pytest.raises(ValidationError):
            ErrorInjectionConfig(rate_limit_pct=value)

    @given(value=st.floats(max_value=-0.1, allow_nan=False, allow_infinity=False))
    @settings(max_examples=50)
    def test_rate_limit_pct_rejects_below_0(self, value: float) -> None:
        """Property: Negative percentages are rejected."""
        with pytest.raises(ValidationError):
            ErrorInjectionConfig(rate_limit_pct=value)

    @given(value=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False))
    @settings(max_examples=50)
    def test_rate_limit_pct_accepts_valid(self, value: float) -> None:
        """Property: Percentages in [0, 100] are accepted."""
        config = ErrorInjectionConfig(rate_limit_pct=value)
        assert config.rate_limit_pct == value


class TestConfigFrozenModels:
    """Property tests for frozen/extra=forbid on config models."""

    def test_server_config_rejects_extra_fields(self) -> None:
        """Property: ServerConfig rejects unknown fields."""
        with pytest.raises(ValidationError):
            ServerConfig(host="0.0.0.0", unknown_field="bad")  # type: ignore[call-arg]

    def test_latency_config_rejects_extra_fields(self) -> None:
        """Property: LatencyConfig rejects unknown fields."""
        with pytest.raises(ValidationError):
            LatencyConfig(base_ms=50, unknown_field="bad")  # type: ignore[call-arg]

    def test_error_injection_rejects_extra_fields(self) -> None:
        """Property: ErrorInjectionConfig rejects unknown fields."""
        with pytest.raises(ValidationError):
            ErrorInjectionConfig(unknown_field="bad")  # type: ignore[call-arg]

    def test_chaosllm_config_rejects_extra_fields(self) -> None:
        """Property: ChaosLLMConfig rejects unknown fields."""
        with pytest.raises(ValidationError):
            ChaosLLMConfig(unknown_field="bad")  # type: ignore[call-arg]


class TestRandomResponseConfigValidation:
    """Property tests for RandomResponseConfig validators."""

    @given(
        min_words=st.integers(min_value=50, max_value=100),
        max_words=st.integers(min_value=1, max_value=49),
    )
    @settings(max_examples=50)
    def test_rejects_min_words_gt_max_words(self, min_words: int, max_words: int) -> None:
        """Property: min_words > max_words is rejected."""
        with pytest.raises(ValidationError):
            RandomResponseConfig(min_words=min_words, max_words=max_words)

    @given(
        min_words=st.integers(min_value=1, max_value=50),
        max_words=st.integers(min_value=50, max_value=200),
    )
    @settings(max_examples=50)
    def test_accepts_min_words_leq_max_words(self, min_words: int, max_words: int) -> None:
        """Property: min_words <= max_words is accepted."""
        config = RandomResponseConfig(min_words=min_words, max_words=max_words)
        assert config.min_words == min_words
        assert config.max_words == max_words


# =============================================================================
# _deep_merge Properties
# =============================================================================


class TestDeepMerge:
    """Property tests for _deep_merge configuration merging."""

    @given(
        base=st.fixed_dictionaries(
            {
                "a": st.integers(),
                "b": st.text(min_size=1, max_size=10),
            }
        ),
    )
    @settings(max_examples=50)
    def test_merge_with_empty_is_identity(self, base: dict[str, Any]) -> None:
        """Property: Merging with empty dict returns base unchanged."""
        result = _deep_merge(base, {})
        assert result == base

    @given(
        override=st.fixed_dictionaries(
            {
                "a": st.integers(),
                "b": st.text(min_size=1, max_size=10),
            }
        ),
    )
    @settings(max_examples=50)
    def test_merge_empty_with_override(self, override: dict[str, Any]) -> None:
        """Property: Merging empty base with override returns override."""
        result = _deep_merge({}, override)
        assert result == override

    @given(
        val1=st.integers(),
        val2=st.integers(),
    )
    @settings(max_examples=50)
    def test_override_takes_precedence(self, val1: int, val2: int) -> None:
        """Property: Override values take precedence over base."""
        assume(val1 != val2)
        base = {"key": val1}
        override = {"key": val2}
        result = _deep_merge(base, override)
        assert result["key"] == val2

    @given(
        a_val=st.integers(),
        b_val=st.integers(),
        c_val=st.integers(),
    )
    @settings(max_examples=50)
    def test_nested_merge_preserves_other_keys(self, a_val: int, b_val: int, c_val: int) -> None:
        """Property: Nested merge preserves non-overlapping keys."""
        base = {"nested": {"a": a_val, "b": b_val}}
        override = {"nested": {"c": c_val}}
        result = _deep_merge(base, override)
        assert result["nested"]["a"] == a_val
        assert result["nested"]["b"] == b_val
        assert result["nested"]["c"] == c_val

    @given(
        a_val=st.integers(),
        a_new=st.integers(),
        b_val=st.integers(),
    )
    @settings(max_examples=50)
    def test_nested_override_replaces_value(self, a_val: int, a_new: int, b_val: int) -> None:
        """Property: Nested override replaces the specific key."""
        assume(a_val != a_new)
        base = {"nested": {"a": a_val, "b": b_val}}
        override = {"nested": {"a": a_new}}
        result = _deep_merge(base, override)
        assert result["nested"]["a"] == a_new
        assert result["nested"]["b"] == b_val
