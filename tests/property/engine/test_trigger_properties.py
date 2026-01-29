# tests/property/engine/test_trigger_properties.py
"""Property-based tests for aggregation trigger evaluation.

These tests verify the fundamental properties of ELSPETH's trigger system:

Trigger Properties:
- Count trigger fires exactly at threshold, not before
- Timeout trigger fires when elapsed time >= threshold
- Condition trigger evaluates batch-level context correctly
- OR logic: any trigger firing causes should_trigger() to return True

State Properties:
- batch_count increments correctly on each record_accept()
- batch_age_seconds tracks time since first accept
- reset() clears all state completely
- which_triggered() correctly identifies the firing trigger

The trigger system is critical for aggregation batching - incorrect behavior
would cause premature or delayed batch flushes, affecting audit integrity.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from elspeth.contracts.enums import TriggerType
from elspeth.core.config import TriggerConfig
from elspeth.engine.clock import MockClock
from elspeth.engine.triggers import TriggerEvaluator

# =============================================================================
# Strategies for generating trigger configurations
# =============================================================================

# Count thresholds (positive integers)
count_thresholds = st.integers(min_value=1, max_value=100)

# Timeout thresholds (positive floats in seconds)
timeout_thresholds = st.floats(min_value=0.1, max_value=100.0, allow_nan=False, allow_infinity=False)

# Small advancement times for deterministic testing
time_advances = st.floats(min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False)

# Number of accepts to perform
accept_counts = st.integers(min_value=0, max_value=50)


# =============================================================================
# Count Trigger Property Tests
# =============================================================================


class TestCountTriggerProperties:
    """Property tests for count-based trigger behavior."""

    @given(threshold=count_thresholds, accepts_before=st.integers(min_value=0, max_value=99))
    @settings(max_examples=100)
    def test_count_does_not_fire_before_threshold(self, threshold: int, accepts_before: int) -> None:
        """Property: Count trigger does NOT fire when batch_count < threshold."""
        # Only test if accepts_before is less than threshold
        if accepts_before >= threshold:
            accepts_before = threshold - 1

        config = TriggerConfig(count=threshold)
        evaluator = TriggerEvaluator(config)

        # Accept rows up to (but not reaching) threshold
        for _ in range(accepts_before):
            evaluator.record_accept()

        # Should NOT trigger yet
        assert evaluator.should_trigger() is False, f"Count trigger fired at {evaluator.batch_count}, threshold is {threshold}"

    @given(threshold=count_thresholds)
    @settings(max_examples=100)
    def test_count_fires_exactly_at_threshold(self, threshold: int) -> None:
        """Property: Count trigger fires EXACTLY when batch_count >= threshold."""
        config = TriggerConfig(count=threshold)
        evaluator = TriggerEvaluator(config)

        # Accept exactly threshold rows
        for _ in range(threshold):
            evaluator.record_accept()

        # Should trigger now
        assert evaluator.should_trigger() is True
        assert evaluator.which_triggered() == "count"
        assert evaluator.get_trigger_type() == TriggerType.COUNT

    @given(threshold=count_thresholds, extra=st.integers(min_value=1, max_value=10))
    @settings(max_examples=50)
    def test_count_fires_beyond_threshold(self, threshold: int, extra: int) -> None:
        """Property: Count trigger still fires when batch_count > threshold."""
        config = TriggerConfig(count=threshold)
        evaluator = TriggerEvaluator(config)

        # Accept more than threshold
        for _ in range(threshold + extra):
            evaluator.record_accept()

        # Should still trigger
        assert evaluator.should_trigger() is True
        assert evaluator.which_triggered() == "count"


class TestBatchCountProperties:
    """Property tests for batch_count tracking."""

    @given(accepts=accept_counts)
    @settings(max_examples=100)
    def test_batch_count_increments_correctly(self, accepts: int) -> None:
        """Property: batch_count equals number of record_accept() calls."""
        config = TriggerConfig(count=1000)  # High threshold so we don't trigger
        evaluator = TriggerEvaluator(config)

        for _ in range(accepts):
            evaluator.record_accept()

        assert evaluator.batch_count == accepts

    @given(accepts1=accept_counts, accepts2=accept_counts)
    @settings(max_examples=50)
    def test_reset_clears_batch_count(self, accepts1: int, accepts2: int) -> None:
        """Property: reset() sets batch_count back to zero."""
        config = TriggerConfig(count=1000)
        evaluator = TriggerEvaluator(config)

        # First batch
        for _ in range(accepts1):
            evaluator.record_accept()
        assert evaluator.batch_count == accepts1

        # Reset
        evaluator.reset()
        assert evaluator.batch_count == 0

        # Second batch
        for _ in range(accepts2):
            evaluator.record_accept()
        assert evaluator.batch_count == accepts2


# =============================================================================
# Timeout Trigger Property Tests
# =============================================================================


class TestTimeoutTriggerProperties:
    """Property tests for timeout-based trigger behavior."""

    @given(timeout=timeout_thresholds, elapsed=st.floats(min_value=0.0, max_value=100.0))
    @settings(max_examples=100)
    def test_timeout_fires_at_threshold(self, timeout: float, elapsed: float) -> None:
        """Property: Timeout trigger fires iff elapsed time >= threshold."""
        clock = MockClock(start=0.0)
        config = TriggerConfig(timeout_seconds=timeout)
        evaluator = TriggerEvaluator(config, clock=clock)

        # Must have at least one accept for timer to start
        evaluator.record_accept()

        # Advance time
        clock.advance(elapsed)

        expected_trigger = elapsed >= timeout
        actual_trigger = evaluator.should_trigger()

        assert actual_trigger == expected_trigger, (
            f"Timeout trigger mismatch: elapsed={elapsed}, threshold={timeout}, expected={expected_trigger}, actual={actual_trigger}"
        )

        if expected_trigger:
            assert evaluator.which_triggered() == "timeout"
            assert evaluator.get_trigger_type() == TriggerType.TIMEOUT

    @given(timeout=timeout_thresholds)
    @settings(max_examples=50)
    def test_timeout_not_triggered_without_accepts(self, timeout: float) -> None:
        """Property: Timeout never triggers if no rows have been accepted."""
        clock = MockClock(start=0.0)
        config = TriggerConfig(timeout_seconds=timeout)
        evaluator = TriggerEvaluator(config, clock=clock)

        # Advance time way past threshold
        clock.advance(timeout * 10)

        # Should NOT trigger (no accepts, so timer never started)
        assert evaluator.should_trigger() is False


class TestBatchAgeProperties:
    """Property tests for batch_age_seconds tracking."""

    def test_batch_age_is_zero_before_first_accept(self) -> None:
        """Property: batch_age_seconds is 0 before any accepts."""
        clock = MockClock(start=100.0)  # Start at non-zero time
        config = TriggerConfig(timeout_seconds=10.0)
        evaluator = TriggerEvaluator(config, clock=clock)

        assert evaluator.batch_age_seconds == 0.0

    @given(start_time=st.floats(min_value=0.0, max_value=1000.0), advance1=time_advances, advance2=time_advances)
    @settings(max_examples=50)
    def test_batch_age_tracks_time_since_first_accept(self, start_time: float, advance1: float, advance2: float) -> None:
        """Property: batch_age_seconds = current_time - first_accept_time."""
        clock = MockClock(start=start_time)
        config = TriggerConfig(timeout_seconds=100.0)
        evaluator = TriggerEvaluator(config, clock=clock)

        # Advance before first accept
        clock.advance(advance1)

        # First accept starts timer
        evaluator.record_accept()
        first_accept_time = clock.monotonic()

        # Advance after accept
        clock.advance(advance2)

        expected_age = clock.monotonic() - first_accept_time
        actual_age = evaluator.batch_age_seconds

        assert abs(actual_age - expected_age) < 1e-9, f"Age mismatch: expected {expected_age}, got {actual_age}"

    @given(advance1=time_advances, advance2=time_advances)
    @settings(max_examples=30)
    def test_reset_clears_timer(self, advance1: float, advance2: float) -> None:
        """Property: reset() clears the timer, making batch_age_seconds = 0."""
        clock = MockClock(start=0.0)
        config = TriggerConfig(timeout_seconds=100.0)
        evaluator = TriggerEvaluator(config, clock=clock)

        # First batch
        evaluator.record_accept()
        clock.advance(advance1)
        assert evaluator.batch_age_seconds > 0 or advance1 == 0

        # Reset
        evaluator.reset()
        assert evaluator.batch_age_seconds == 0.0

        # Second batch - timer not started until accept
        clock.advance(advance2)
        assert evaluator.batch_age_seconds == 0.0  # Still 0 until accept


# =============================================================================
# Condition Trigger Property Tests
# =============================================================================


class TestConditionTriggerProperties:
    """Property tests for expression-based trigger conditions."""

    @given(threshold=st.integers(min_value=1, max_value=20), accepts=st.integers(min_value=0, max_value=30))
    @settings(max_examples=50)
    def test_condition_evaluates_batch_count(self, threshold: int, accepts: int) -> None:
        """Property: Condition can evaluate batch_count correctly."""
        config = TriggerConfig(condition=f"row['batch_count'] >= {threshold}")
        evaluator = TriggerEvaluator(config)

        for _ in range(accepts):
            evaluator.record_accept()

        expected_trigger = accepts >= threshold
        actual_trigger = evaluator.should_trigger()

        assert actual_trigger == expected_trigger, f"Condition trigger mismatch: accepts={accepts}, threshold={threshold}"

        if expected_trigger:
            assert evaluator.which_triggered() == "condition"
            assert evaluator.get_trigger_type() == TriggerType.CONDITION

    @given(timeout=st.floats(min_value=0.5, max_value=10.0), elapsed=st.floats(min_value=0.0, max_value=15.0))
    @settings(max_examples=50)
    def test_condition_evaluates_batch_age(self, timeout: float, elapsed: float) -> None:
        """Property: Condition can evaluate batch_age_seconds correctly."""
        clock = MockClock(start=0.0)
        config = TriggerConfig(condition=f"row['batch_age_seconds'] >= {timeout}")
        evaluator = TriggerEvaluator(config, clock=clock)

        # Must accept to start timer
        evaluator.record_accept()
        clock.advance(elapsed)

        expected_trigger = elapsed >= timeout
        actual_trigger = evaluator.should_trigger()

        assert actual_trigger == expected_trigger, f"Condition age trigger mismatch: elapsed={elapsed}, threshold={timeout}"


# =============================================================================
# OR Logic Property Tests
# =============================================================================


class TestTriggerOrLogicProperties:
    """Property tests for trigger combination (OR logic)."""

    @given(count_threshold=st.integers(min_value=5, max_value=20), timeout_threshold=st.floats(min_value=1.0, max_value=10.0))
    @settings(max_examples=30)
    def test_count_triggers_first_if_threshold_met_first(self, count_threshold: int, timeout_threshold: float) -> None:
        """Property: When count threshold met first, which_triggered() returns 'count'."""
        clock = MockClock(start=0.0)
        config = TriggerConfig(count=count_threshold, timeout_seconds=timeout_threshold)
        evaluator = TriggerEvaluator(config, clock=clock)

        # Meet count threshold before timeout
        for _ in range(count_threshold):
            evaluator.record_accept()
        # Don't advance time much
        clock.advance(timeout_threshold / 10)

        assert evaluator.should_trigger() is True
        assert evaluator.which_triggered() == "count"

    @given(count_threshold=st.integers(min_value=100, max_value=200), timeout_threshold=st.floats(min_value=0.5, max_value=2.0))
    @settings(max_examples=30)
    def test_timeout_triggers_first_if_threshold_met_first(self, count_threshold: int, timeout_threshold: float) -> None:
        """Property: When timeout threshold met first, which_triggered() returns 'timeout'."""
        clock = MockClock(start=0.0)
        config = TriggerConfig(count=count_threshold, timeout_seconds=timeout_threshold)
        evaluator = TriggerEvaluator(config, clock=clock)

        # Accept just 1 row (starts timer, but far from count threshold)
        evaluator.record_accept()

        # Advance past timeout
        clock.advance(timeout_threshold + 0.1)

        assert evaluator.should_trigger() is True
        assert evaluator.which_triggered() == "timeout"

    @given(count_threshold=st.integers(min_value=10, max_value=20), timeout_threshold=st.floats(min_value=5.0, max_value=10.0))
    @settings(max_examples=20)
    def test_neither_trigger_fires_when_both_below_threshold(self, count_threshold: int, timeout_threshold: float) -> None:
        """Property: No trigger fires when both thresholds are unmet."""
        clock = MockClock(start=0.0)
        config = TriggerConfig(count=count_threshold, timeout_seconds=timeout_threshold)
        evaluator = TriggerEvaluator(config, clock=clock)

        # Accept fewer than threshold
        for _ in range(count_threshold - 1):
            evaluator.record_accept()

        # Advance less than timeout
        clock.advance(timeout_threshold / 2)

        assert evaluator.should_trigger() is False
        assert evaluator.which_triggered() is None


# =============================================================================
# Reset Property Tests
# =============================================================================


class TestResetProperties:
    """Property tests for reset() behavior."""

    @given(accepts=accept_counts, advance=time_advances)
    @settings(max_examples=50)
    def test_reset_clears_all_state(self, accepts: int, advance: float) -> None:
        """Property: reset() returns evaluator to initial state."""
        clock = MockClock(start=0.0)
        config = TriggerConfig(count=1000, timeout_seconds=1000.0)
        evaluator = TriggerEvaluator(config, clock=clock)

        # Build up state
        for _ in range(accepts):
            evaluator.record_accept()
        clock.advance(advance)
        evaluator.should_trigger()  # Sets _last_triggered

        # Reset
        evaluator.reset()

        # Verify all state is cleared
        assert evaluator.batch_count == 0
        assert evaluator.batch_age_seconds == 0.0
        assert evaluator.which_triggered() is None

    def test_reset_allows_reuse(self) -> None:
        """Property: After reset(), evaluator can be used for new batch."""
        config = TriggerConfig(count=5)
        evaluator = TriggerEvaluator(config)

        # First batch - trigger at 5
        for _ in range(5):
            evaluator.record_accept()
        assert evaluator.should_trigger() is True

        # Reset and new batch
        evaluator.reset()
        for _ in range(3):
            evaluator.record_accept()
        assert evaluator.should_trigger() is False  # Only 3, threshold is 5

        for _ in range(2):
            evaluator.record_accept()
        assert evaluator.should_trigger() is True  # Now 5


# =============================================================================
# Determinism Property Tests
# =============================================================================


class TestTriggerDeterminismProperties:
    """Property tests for deterministic behavior."""

    @given(threshold=count_thresholds, accepts=accept_counts)
    @settings(max_examples=50)
    def test_should_trigger_is_deterministic(self, threshold: int, accepts: int) -> None:
        """Property: Same inputs produce same should_trigger() result."""
        config = TriggerConfig(count=threshold)

        # Run twice with same inputs
        evaluator1 = TriggerEvaluator(config)
        evaluator2 = TriggerEvaluator(config)

        for _ in range(accepts):
            evaluator1.record_accept()
            evaluator2.record_accept()

        result1 = evaluator1.should_trigger()
        result2 = evaluator2.should_trigger()

        assert result1 == result2, "should_trigger() is not deterministic"

    @given(accepts=accept_counts)
    @settings(max_examples=30)
    def test_multiple_should_trigger_calls_are_idempotent(self, accepts: int) -> None:
        """Property: Calling should_trigger() multiple times gives same result."""
        config = TriggerConfig(count=10)
        evaluator = TriggerEvaluator(config)

        for _ in range(accepts):
            evaluator.record_accept()

        result1 = evaluator.should_trigger()
        result2 = evaluator.should_trigger()
        result3 = evaluator.should_trigger()

        assert result1 == result2 == result3


# =============================================================================
# Edge Case Property Tests
# =============================================================================


class TestTriggerEdgeCaseProperties:
    """Property tests for edge cases."""

    def test_no_triggers_configured_is_rejected(self) -> None:
        """Property: TriggerConfig requires at least one trigger configured.

        An aggregation without triggers would never flush, causing unbounded
        memory growth. The config validation prevents this.
        """
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            TriggerConfig()  # No count, timeout, or condition

    def test_count_of_one_fires_immediately(self) -> None:
        """Property: count=1 fires on first accept."""
        config = TriggerConfig(count=1)
        evaluator = TriggerEvaluator(config)

        evaluator.record_accept()
        assert evaluator.should_trigger() is True
        assert evaluator.which_triggered() == "count"

    def test_timeout_of_zero_point_one_fires_quickly(self) -> None:
        """Property: Very small timeout still works correctly."""
        clock = MockClock(start=0.0)
        config = TriggerConfig(timeout_seconds=0.1)
        evaluator = TriggerEvaluator(config, clock=clock)

        evaluator.record_accept()
        clock.advance(0.05)
        assert evaluator.should_trigger() is False

        clock.advance(0.05)
        assert evaluator.should_trigger() is True

    @given(threshold=count_thresholds)
    @settings(max_examples=20)
    def test_get_age_seconds_alias_matches_batch_age_seconds(self, threshold: int) -> None:
        """Property: get_age_seconds() returns same value as batch_age_seconds."""
        clock = MockClock(start=0.0)
        config = TriggerConfig(count=threshold)
        evaluator = TriggerEvaluator(config, clock=clock)

        evaluator.record_accept()
        clock.advance(5.5)

        assert evaluator.get_age_seconds() == evaluator.batch_age_seconds
