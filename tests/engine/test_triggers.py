"""Tests for TriggerEvaluator."""


class TestTriggerEvaluator:
    """Tests for TriggerEvaluator class.

    Per plugin-protocol.md: Multiple triggers can be combined (first one to fire wins).
    The evaluator checks ALL configured triggers with OR logic.
    """

    def test_count_trigger_not_reached(self) -> None:
        """Count trigger returns False when threshold not reached."""
        from elspeth.core.config import TriggerConfig
        from elspeth.engine.triggers import TriggerEvaluator

        config = TriggerConfig(count=100)
        evaluator = TriggerEvaluator(config)

        for _ in range(50):
            evaluator.record_accept()

        assert evaluator.should_trigger() is False

    def test_count_trigger_reached(self) -> None:
        """Count trigger returns True when threshold reached."""
        from elspeth.core.config import TriggerConfig
        from elspeth.engine.triggers import TriggerEvaluator

        config = TriggerConfig(count=100)
        evaluator = TriggerEvaluator(config)

        for _ in range(100):
            evaluator.record_accept()

        assert evaluator.should_trigger() is True

    def test_count_trigger_exceeded(self) -> None:
        """Count trigger returns True when threshold exceeded."""
        from elspeth.core.config import TriggerConfig
        from elspeth.engine.triggers import TriggerEvaluator

        config = TriggerConfig(count=100)
        evaluator = TriggerEvaluator(config)

        for _ in range(150):
            evaluator.record_accept()

        assert evaluator.should_trigger() is True

    def test_timeout_trigger_not_reached(self) -> None:
        """Timeout trigger returns False when time not exceeded."""
        from elspeth.core.config import TriggerConfig
        from elspeth.engine.triggers import TriggerEvaluator

        config = TriggerConfig(timeout_seconds=10.0)
        evaluator = TriggerEvaluator(config)

        evaluator.record_accept()
        assert evaluator.should_trigger() is False

    def test_timeout_trigger_reached(self) -> None:
        """Timeout trigger returns True when time exceeded."""
        from elspeth.core.config import TriggerConfig
        from elspeth.engine.clock import MockClock
        from elspeth.engine.triggers import TriggerEvaluator

        clock = MockClock(start=0.0)
        config = TriggerConfig(timeout_seconds=0.01)
        evaluator = TriggerEvaluator(config, clock=clock)

        evaluator.record_accept()
        clock.advance(0.02)  # Advance past timeout
        assert evaluator.should_trigger() is True

    def test_condition_trigger_not_met(self) -> None:
        """Condition trigger returns False when condition not met."""
        from elspeth.core.config import TriggerConfig
        from elspeth.engine.triggers import TriggerEvaluator

        # Use row['batch_count'] syntax per ExpressionParser security model
        config = TriggerConfig(condition="row['batch_count'] >= 50")
        evaluator = TriggerEvaluator(config)

        for _ in range(30):
            evaluator.record_accept()

        assert evaluator.should_trigger() is False

    def test_condition_trigger_met(self) -> None:
        """Condition trigger returns True when condition met."""
        from elspeth.core.config import TriggerConfig
        from elspeth.engine.triggers import TriggerEvaluator

        config = TriggerConfig(condition="row['batch_count'] >= 50")
        evaluator = TriggerEvaluator(config)

        for _ in range(50):
            evaluator.record_accept()

        assert evaluator.should_trigger() is True

    def test_condition_trigger_with_age(self) -> None:
        """Condition trigger can use batch_age_seconds."""
        from elspeth.core.config import TriggerConfig
        from elspeth.engine.clock import MockClock
        from elspeth.engine.triggers import TriggerEvaluator

        clock = MockClock(start=0.0)
        config = TriggerConfig(
            condition="row['batch_count'] >= 10 and row['batch_age_seconds'] > 0.01",
        )
        evaluator = TriggerEvaluator(config, clock=clock)

        for _ in range(15):
            evaluator.record_accept()

        clock.advance(0.02)  # Advance past condition threshold
        assert evaluator.should_trigger() is True

    def test_combined_count_and_timeout_count_wins(self) -> None:
        """Combined triggers: count fires first (OR logic)."""
        from elspeth.core.config import TriggerConfig
        from elspeth.engine.triggers import TriggerEvaluator

        config = TriggerConfig(count=10, timeout_seconds=3600.0)
        evaluator = TriggerEvaluator(config)

        for _ in range(10):
            evaluator.record_accept()

        result = evaluator.should_trigger()
        assert result is True
        assert evaluator.which_triggered() == "count"

    def test_combined_count_and_timeout_timeout_wins(self) -> None:
        """Combined triggers: timeout fires first (OR logic)."""
        from elspeth.core.config import TriggerConfig
        from elspeth.engine.clock import MockClock
        from elspeth.engine.triggers import TriggerEvaluator

        clock = MockClock(start=0.0)
        config = TriggerConfig(count=1000, timeout_seconds=0.01)
        evaluator = TriggerEvaluator(config, clock=clock)

        for _ in range(5):
            evaluator.record_accept()

        clock.advance(0.02)  # Advance past timeout

        result = evaluator.should_trigger()
        assert result is True
        assert evaluator.which_triggered() == "timeout"

    def test_combined_all_triggers_count_wins(self) -> None:
        """Combined count + timeout + condition: count fires first."""
        from elspeth.core.config import TriggerConfig
        from elspeth.engine.triggers import TriggerEvaluator

        config = TriggerConfig(
            count=5,
            timeout_seconds=3600.0,
            condition="row['batch_count'] >= 1000",
        )
        evaluator = TriggerEvaluator(config)

        for _ in range(5):
            evaluator.record_accept()

        assert evaluator.should_trigger() is True
        assert evaluator.which_triggered() == "count"

    def test_combined_none_fire_yet(self) -> None:
        """Combined triggers: none fire until at least one condition met."""
        from elspeth.core.config import TriggerConfig
        from elspeth.engine.triggers import TriggerEvaluator

        config = TriggerConfig(
            count=100,
            timeout_seconds=3600.0,
        )
        evaluator = TriggerEvaluator(config)

        for _ in range(10):
            evaluator.record_accept()

        assert evaluator.should_trigger() is False
        assert evaluator.which_triggered() is None

    def test_reset_clears_state(self) -> None:
        """Reset clears batch count and timer."""
        from elspeth.core.config import TriggerConfig
        from elspeth.engine.triggers import TriggerEvaluator

        config = TriggerConfig(count=100)
        evaluator = TriggerEvaluator(config)

        for _ in range(100):
            evaluator.record_accept()

        assert evaluator.should_trigger() is True

        evaluator.reset()

        assert evaluator.should_trigger() is False
        assert evaluator.batch_count == 0

    def test_batch_count_property(self) -> None:
        """batch_count property returns current count."""
        from elspeth.core.config import TriggerConfig
        from elspeth.engine.triggers import TriggerEvaluator

        config = TriggerConfig(count=100)
        evaluator = TriggerEvaluator(config)

        assert evaluator.batch_count == 0

        for _ in range(42):
            evaluator.record_accept()

        assert evaluator.batch_count == 42

    def test_batch_age_seconds_property(self) -> None:
        """batch_age_seconds returns time since first accept."""
        from elspeth.core.config import TriggerConfig
        from elspeth.engine.clock import MockClock
        from elspeth.engine.triggers import TriggerEvaluator

        clock = MockClock(start=0.0)
        config = TriggerConfig(timeout_seconds=10.0)
        evaluator = TriggerEvaluator(config, clock=clock)

        assert evaluator.batch_age_seconds == 0.0

        evaluator.record_accept()
        clock.advance(0.5)  # Advance time by 500ms

        assert evaluator.batch_age_seconds == 0.5


class TestTriggerFirstToFireWins:
    """Tests for 'first to fire wins' semantics per plugin-protocol.md:1211.

    When multiple triggers are satisfied simultaneously, the one that
    FIRED FIRST (became true earliest) should be reported, not the one
    checked first in code order.

    Bug: P2-2026-01-22-trigger-type-priority-misreports-first-fire
    """

    def test_timeout_fires_before_count_reports_timeout(self) -> None:
        """When timeout elapsed before count reached, report TIMEOUT.

        Scenario:
        - Count=100, Timeout=1.0s
        - Accept 99 rows at t=0
        - Time advances to t=1.1s (timeout fired at t=1.0s)
        - Accept row 100 at t=1.1s (count fires now)
        - Both conditions are now true, but timeout fired FIRST

        Expected: which_triggered() == "timeout"
        Bug behavior: which_triggered() == "count" (checked first in code)
        """
        from elspeth.core.config import TriggerConfig
        from elspeth.engine.clock import MockClock
        from elspeth.engine.triggers import TriggerEvaluator

        clock = MockClock(start=0.0)
        config = TriggerConfig(count=100, timeout_seconds=1.0)
        evaluator = TriggerEvaluator(config, clock=clock)

        # Accept 99 rows quickly at t=0
        for _ in range(99):
            evaluator.record_accept()

        # Timeout hasn't fired yet (only 99 rows, age ~0)
        assert evaluator.should_trigger() is False

        # Time advances past timeout threshold
        clock.advance(1.1)  # Now at t=1.1s, timeout fired at t=1.0s

        # Accept the 100th row - count threshold now reached at t=1.1s
        evaluator.record_accept()

        # Both triggers are satisfied, but timeout fired first (at t=1.0s)
        assert evaluator.should_trigger() is True
        assert evaluator.which_triggered() == "timeout", (
            "Timeout fired at t=1.0s, count fired at t=1.1s. Per 'first to fire wins' contract, should report 'timeout', not 'count'."
        )

    def test_count_fires_before_timeout_reports_count(self) -> None:
        """When count reached before timeout elapsed, report COUNT.

        Scenario:
        - Count=10, Timeout=5.0s
        - Accept 10 rows quickly at t=0.1s
        - Count fires at t=0.1s, timeout would fire at t=5.0s

        Expected: which_triggered() == "count"
        """
        from elspeth.core.config import TriggerConfig
        from elspeth.engine.clock import MockClock
        from elspeth.engine.triggers import TriggerEvaluator

        clock = MockClock(start=0.0)
        config = TriggerConfig(count=10, timeout_seconds=5.0)
        evaluator = TriggerEvaluator(config, clock=clock)

        # Accept 10 rows quickly
        clock.advance(0.1)
        for _ in range(10):
            evaluator.record_accept()

        # Count reached at t=0.1s, timeout would fire at t=5.0s
        assert evaluator.should_trigger() is True
        assert evaluator.which_triggered() == "count"

    def test_condition_fires_before_timeout_reports_condition(self) -> None:
        """When condition becomes true before timeout, report CONDITION.

        Scenario:
        - Condition: batch_count >= 5
        - Timeout: 2.0s
        - Accept 5 rows at t=0.5s (condition fires)
        - Time advances to t=2.5s (timeout also fires)

        Expected: which_triggered() == "condition"
        """
        from elspeth.core.config import TriggerConfig
        from elspeth.engine.clock import MockClock
        from elspeth.engine.triggers import TriggerEvaluator

        clock = MockClock(start=0.0)
        config = TriggerConfig(
            timeout_seconds=2.0,
            condition="row['batch_count'] >= 5",
        )
        evaluator = TriggerEvaluator(config, clock=clock)

        # Accept 5 rows at t=0.5s
        clock.advance(0.5)
        for _ in range(5):
            evaluator.record_accept()

        # Condition fires at t=0.5s
        # Time advances past timeout
        clock.advance(2.0)  # Now at t=2.5s

        # Both condition (t=0.5s) and timeout (t=2.0s) have fired
        assert evaluator.should_trigger() is True
        assert evaluator.which_triggered() == "condition", (
            "Condition fired at t=0.5s, timeout fired at t=2.0s. Per 'first to fire wins' contract, should report 'condition'."
        )

    def test_timeout_fires_before_condition_reports_timeout(self) -> None:
        """When timeout elapses before condition becomes true, report TIMEOUT.

        Scenario:
        - Condition: batch_count >= 100
        - Timeout: 1.0s
        - Accept 50 rows at t=0 (condition not yet true)
        - Time advances to t=1.5s (timeout fires at t=1.0s)
        - Accept 50 more rows at t=1.5s (condition now fires)

        Expected: which_triggered() == "timeout"
        """
        from elspeth.core.config import TriggerConfig
        from elspeth.engine.clock import MockClock
        from elspeth.engine.triggers import TriggerEvaluator

        clock = MockClock(start=0.0)
        config = TriggerConfig(
            timeout_seconds=1.0,
            condition="row['batch_count'] >= 100",
        )
        evaluator = TriggerEvaluator(config, clock=clock)

        # Accept 50 rows at t=0 (condition not yet true)
        for _ in range(50):
            evaluator.record_accept()

        assert evaluator.should_trigger() is False

        # Time advances past timeout
        clock.advance(1.5)  # Timeout fires at t=1.0s

        # Accept 50 more rows - condition now true at t=1.5s
        for _ in range(50):
            evaluator.record_accept()

        # Timeout (t=1.0s) fired before condition (t=1.5s)
        assert evaluator.should_trigger() is True
        assert evaluator.which_triggered() == "timeout", (
            "Timeout fired at t=1.0s, condition fired at t=1.5s. Per 'first to fire wins' contract, should report 'timeout'."
        )
