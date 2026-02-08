# tests/unit/engine/test_clock.py
"""Tests for the Clock abstraction (SystemClock, MockClock, DEFAULT_CLOCK).

The Clock protocol provides a time abstraction enabling deterministic
testing of timeout-dependent code paths (aggregation triggers, coalesce
timeouts). SystemClock delegates to time.monotonic(); MockClock allows
programmatic time control.
"""

import math

import pytest


class TestClockProtocol:
    """Verify that Clock implementations satisfy the protocol structurally.

    The Clock protocol is NOT @runtime_checkable, so we verify structural
    conformance (has callable 'monotonic' returning float) rather than
    using isinstance().
    """

    def test_system_clock_satisfies_clock_protocol(self) -> None:
        """SystemClock has a callable monotonic method."""
        from elspeth.engine.clock import SystemClock

        clock = SystemClock()
        assert hasattr(clock, "monotonic")
        assert callable(clock.monotonic)

    def test_system_clock_monotonic_returns_float(self) -> None:
        """SystemClock.monotonic() returns a float."""
        from elspeth.engine.clock import SystemClock

        clock = SystemClock()
        result = clock.monotonic()
        assert isinstance(result, float)

    def test_mock_clock_satisfies_clock_protocol(self) -> None:
        """MockClock has a callable monotonic method."""
        from elspeth.engine.clock import MockClock

        clock = MockClock()
        assert hasattr(clock, "monotonic")
        assert callable(clock.monotonic)

    def test_mock_clock_monotonic_returns_float(self) -> None:
        """MockClock.monotonic() returns a float."""
        from elspeth.engine.clock import MockClock

        clock = MockClock()
        result = clock.monotonic()
        assert isinstance(result, float)

    def test_default_clock_is_system_clock(self) -> None:
        """DEFAULT_CLOCK is a SystemClock instance."""
        from elspeth.engine.clock import DEFAULT_CLOCK, SystemClock

        assert isinstance(DEFAULT_CLOCK, SystemClock)

    def test_clock_protocol_not_runtime_checkable(self) -> None:
        """Clock protocol does not have @runtime_checkable decorator."""
        from elspeth.engine.clock import Clock

        # Protocol without @runtime_checkable raises TypeError on isinstance
        with pytest.raises(TypeError):
            isinstance(object(), Clock)


class TestSystemClock:
    """Tests for SystemClock — the production clock using time.monotonic()."""

    def test_monotonic_returns_float(self) -> None:
        """monotonic() returns a float value."""
        from elspeth.engine.clock import SystemClock

        clock = SystemClock()
        assert isinstance(clock.monotonic(), float)

    def test_monotonic_returns_positive_value(self) -> None:
        """monotonic() returns a positive value (system uptime-based)."""
        from elspeth.engine.clock import SystemClock

        clock = SystemClock()
        assert clock.monotonic() > 0

    def test_monotonic_is_non_decreasing(self) -> None:
        """Two successive calls return non-decreasing values."""
        from elspeth.engine.clock import SystemClock

        clock = SystemClock()
        t1 = clock.monotonic()
        t2 = clock.monotonic()
        assert t2 >= t1

    def test_two_calls_are_close(self) -> None:
        """Two calls in quick succession return values within 0.1s of each other."""
        from elspeth.engine.clock import SystemClock

        clock = SystemClock()
        t1 = clock.monotonic()
        t2 = clock.monotonic()
        assert abs(t2 - t1) < 0.1

    def test_multiple_clocks_return_similar_times(self) -> None:
        """Two different SystemClock instances return similar times."""
        from elspeth.engine.clock import SystemClock

        clock_a = SystemClock()
        clock_b = SystemClock()
        t_a = clock_a.monotonic()
        t_b = clock_b.monotonic()
        assert abs(t_a - t_b) < 0.1

    def test_monotonic_delegates_to_time_monotonic(self) -> None:
        """SystemClock.monotonic() returns a value close to time.monotonic()."""
        import time

        from elspeth.engine.clock import SystemClock

        clock = SystemClock()
        before = time.monotonic()
        result = clock.monotonic()
        after = time.monotonic()
        assert before <= result <= after


class TestMockClock:
    """Tests for MockClock — the deterministic testing clock."""

    # --- Construction ---

    def test_default_start_is_zero(self) -> None:
        """Default start value is 0.0."""
        from elspeth.engine.clock import MockClock

        clock = MockClock()
        assert clock.monotonic() == 0.0

    def test_custom_start_value(self) -> None:
        """Custom start value is returned by monotonic()."""
        from elspeth.engine.clock import MockClock

        clock = MockClock(start=42.5)
        assert clock.monotonic() == 42.5

    def test_start_with_negative_value(self) -> None:
        """Negative start values are allowed (it is just a number)."""
        from elspeth.engine.clock import MockClock

        clock = MockClock(start=-10.0)
        assert clock.monotonic() == -10.0

    def test_start_with_large_value(self) -> None:
        """Large start values are allowed."""
        from elspeth.engine.clock import MockClock

        clock = MockClock(start=1e12)
        assert clock.monotonic() == 1e12

    def test_start_with_zero_explicit(self) -> None:
        """Explicitly passing start=0.0 works same as default."""
        from elspeth.engine.clock import MockClock

        clock = MockClock(start=0.0)
        assert clock.monotonic() == 0.0

    # --- monotonic() ---

    def test_monotonic_returns_current_value(self) -> None:
        """monotonic() returns the internal current value."""
        from elspeth.engine.clock import MockClock

        clock = MockClock(start=7.0)
        assert clock.monotonic() == 7.0

    def test_monotonic_is_idempotent(self) -> None:
        """Calling monotonic() multiple times returns the same value."""
        from elspeth.engine.clock import MockClock

        clock = MockClock(start=3.14)
        assert clock.monotonic() == 3.14
        assert clock.monotonic() == 3.14
        assert clock.monotonic() == 3.14

    # --- advance() ---

    def test_advance_by_positive_amount(self) -> None:
        """Advancing by a positive amount increases time."""
        from elspeth.engine.clock import MockClock

        clock = MockClock(start=0.0)
        clock.advance(5.0)
        assert clock.monotonic() == 5.0

    def test_advance_by_zero(self) -> None:
        """Advancing by zero is allowed and is a no-op."""
        from elspeth.engine.clock import MockClock

        clock = MockClock(start=10.0)
        clock.advance(0.0)
        assert clock.monotonic() == 10.0

    def test_advance_by_negative_raises_value_error(self) -> None:
        """Advancing by a negative amount raises ValueError."""
        from elspeth.engine.clock import MockClock

        clock = MockClock(start=10.0)
        with pytest.raises(ValueError, match="Cannot advance time by negative amount"):
            clock.advance(-1.0)

    def test_advance_by_negative_preserves_state(self) -> None:
        """Failed advance does not change internal time."""
        from elspeth.engine.clock import MockClock

        clock = MockClock(start=10.0)
        with pytest.raises(ValueError):
            clock.advance(-1.0)
        assert clock.monotonic() == 10.0

    def test_advance_accumulates(self) -> None:
        """Multiple advance calls accumulate correctly."""
        from elspeth.engine.clock import MockClock

        clock = MockClock(start=0.0)
        clock.advance(1.0)
        clock.advance(2.0)
        clock.advance(3.0)
        assert clock.monotonic() == 6.0

    def test_advance_with_small_float(self) -> None:
        """Advance works with small fractional amounts."""
        from elspeth.engine.clock import MockClock

        clock = MockClock(start=0.0)
        clock.advance(0.001)
        assert clock.monotonic() == pytest.approx(0.001)

    def test_advance_float_precision(self) -> None:
        """Many small advances maintain reasonable float precision."""
        from elspeth.engine.clock import MockClock

        clock = MockClock(start=0.0)
        for _ in range(1000):
            clock.advance(0.001)
        assert clock.monotonic() == pytest.approx(1.0, abs=1e-9)

    def test_advance_error_message_includes_value(self) -> None:
        """ValueError message includes the negative value that was passed."""
        from elspeth.engine.clock import MockClock

        clock = MockClock()
        with pytest.raises(ValueError, match=r"-5\.0"):
            clock.advance(-5.0)

    # --- set() ---

    def test_set_to_specific_value(self) -> None:
        """set() changes the current time to the given value."""
        from elspeth.engine.clock import MockClock

        clock = MockClock(start=0.0)
        clock.set(100.0)
        assert clock.monotonic() == 100.0

    def test_set_can_go_backwards(self) -> None:
        """set() can move time backwards (unlike real monotonic clocks)."""
        from elspeth.engine.clock import MockClock

        clock = MockClock(start=100.0)
        clock.set(50.0)
        assert clock.monotonic() == 50.0

    def test_set_to_negative_value(self) -> None:
        """set() allows negative values (it is just a number)."""
        from elspeth.engine.clock import MockClock

        clock = MockClock(start=10.0)
        clock.set(-5.0)
        assert clock.monotonic() == -5.0

    def test_set_to_zero(self) -> None:
        """set() to zero works."""
        from elspeth.engine.clock import MockClock

        clock = MockClock(start=99.0)
        clock.set(0.0)
        assert clock.monotonic() == 0.0

    def test_set_to_same_value(self) -> None:
        """set() to the current value is a no-op."""
        from elspeth.engine.clock import MockClock

        clock = MockClock(start=42.0)
        clock.set(42.0)
        assert clock.monotonic() == 42.0

    # --- Combinations ---

    def test_set_then_advance(self) -> None:
        """set() followed by advance() yields set + advance."""
        from elspeth.engine.clock import MockClock

        clock = MockClock()
        clock.set(10.0)
        clock.advance(5.0)
        assert clock.monotonic() == 15.0

    def test_advance_then_set(self) -> None:
        """advance() followed by set() overrides to the set value."""
        from elspeth.engine.clock import MockClock

        clock = MockClock()
        clock.advance(100.0)
        clock.set(5.0)
        assert clock.monotonic() == 5.0

    def test_interleaved_set_and_advance(self) -> None:
        """Interleaved set and advance operations produce correct result."""
        from elspeth.engine.clock import MockClock

        clock = MockClock(start=0.0)
        clock.advance(10.0)  # 10.0
        clock.set(3.0)  # 3.0
        clock.advance(2.0)  # 5.0
        clock.set(100.0)  # 100.0
        clock.advance(0.5)  # 100.5
        assert clock.monotonic() == 100.5

    def test_advance_after_negative_start(self) -> None:
        """advance() from a negative start goes toward zero."""
        from elspeth.engine.clock import MockClock

        clock = MockClock(start=-10.0)
        clock.advance(5.0)
        assert clock.monotonic() == -5.0

    # --- Edge cases ---

    def test_monotonic_return_type_after_advance(self) -> None:
        """monotonic() still returns float after advance."""
        from elspeth.engine.clock import MockClock

        clock = MockClock()
        clock.advance(1)  # int argument
        result = clock.monotonic()
        assert isinstance(result, float)

    def test_advance_with_int_argument(self) -> None:
        """advance() accepts int arguments (coerced by float arithmetic)."""
        from elspeth.engine.clock import MockClock

        clock = MockClock(start=0.0)
        clock.advance(5)
        assert clock.monotonic() == 5.0

    def test_set_with_int_argument(self) -> None:
        """set() accepts int arguments."""
        from elspeth.engine.clock import MockClock

        clock = MockClock()
        clock.set(42)
        assert clock.monotonic() == 42.0

    def test_advance_with_inf_value(self) -> None:
        """advance() with infinity produces infinity."""
        from elspeth.engine.clock import MockClock

        clock = MockClock(start=0.0)
        clock.advance(math.inf)
        assert clock.monotonic() == math.inf

    def test_set_with_inf_value(self) -> None:
        """set() with infinity is allowed."""
        from elspeth.engine.clock import MockClock

        clock = MockClock()
        clock.set(math.inf)
        assert clock.monotonic() == math.inf


class TestDefaultClock:
    """Tests for the module-level DEFAULT_CLOCK instance."""

    def test_default_clock_exists(self) -> None:
        """DEFAULT_CLOCK is importable and not None."""
        from elspeth.engine.clock import DEFAULT_CLOCK

        assert DEFAULT_CLOCK is not None

    def test_default_clock_is_system_clock(self) -> None:
        """DEFAULT_CLOCK is a SystemClock instance."""
        from elspeth.engine.clock import DEFAULT_CLOCK, SystemClock

        assert isinstance(DEFAULT_CLOCK, SystemClock)

    def test_default_clock_monotonic_returns_float(self) -> None:
        """DEFAULT_CLOCK.monotonic() returns a float."""
        from elspeth.engine.clock import DEFAULT_CLOCK

        result = DEFAULT_CLOCK.monotonic()
        assert isinstance(result, float)

    def test_default_clock_monotonic_returns_positive(self) -> None:
        """DEFAULT_CLOCK.monotonic() returns a positive value."""
        from elspeth.engine.clock import DEFAULT_CLOCK

        assert DEFAULT_CLOCK.monotonic() > 0
