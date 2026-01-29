# tests/unit/telemetry/test_manager.py
"""Unit tests for TelemetryManager event coordination.

Tests cover:
- Event dispatching to exporters
- Granularity filtering integration
- Individual exporter failure isolation
- Aggregate logging every 100 drops (Warning Fatigue prevention)
- Total exporter failure handling (crash vs continue)
- Health metrics tracking
- flush() and close() behavior
- Property-based state machine tests
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from unittest.mock import patch

import pytest
from hypothesis import given
from hypothesis import settings as hypothesis_settings
from hypothesis import strategies as st
from hypothesis.stateful import Bundle, RuleBasedStateMachine, rule

from elspeth.contracts.enums import RunStatus, TelemetryGranularity
from elspeth.telemetry import RunCompleted, RunStarted, TelemetryManager
from elspeth.telemetry.errors import TelemetryExporterError
from elspeth.telemetry.events import TelemetryEvent

# =============================================================================
# Test Doubles
# =============================================================================


@dataclass
class MockConfig:
    """Mock RuntimeTelemetryProtocol implementation for testing."""

    enabled: bool = True
    granularity: TelemetryGranularity = TelemetryGranularity.FULL
    fail_on_total_exporter_failure: bool = False

    # Not used by TelemetryManager but required by protocol
    @property
    def backpressure_mode(self) -> Any:
        return None

    @property
    def exporter_configs(self) -> tuple:
        return ()


class MockExporter:
    """Mock exporter that tracks calls and can simulate failures."""

    def __init__(self, name: str, *, fail_export: bool = False, fail_flush: bool = False, fail_close: bool = False):
        self._name = name
        self._fail_export = fail_export
        self._fail_flush = fail_flush
        self._fail_close = fail_close
        self.exports: list[TelemetryEvent] = []
        self.flush_count = 0
        self.close_count = 0

    @property
    def name(self) -> str:
        return self._name

    def configure(self, config: dict[str, Any]) -> None:
        pass

    def export(self, event: TelemetryEvent) -> None:
        if self._fail_export:
            raise RuntimeError(f"Simulated export failure in {self._name}")
        self.exports.append(event)

    def flush(self) -> None:
        if self._fail_flush:
            raise RuntimeError(f"Simulated flush failure in {self._name}")
        self.flush_count += 1

    def close(self) -> None:
        if self._fail_close:
            raise RuntimeError(f"Simulated close failure in {self._name}")
        self.close_count += 1


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def base_timestamp() -> datetime:
    """Fixed timestamp for deterministic tests."""
    return datetime(2026, 1, 30, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def base_run_id() -> str:
    """Fixed run ID for tests."""
    return "run-manager-test"


def make_run_started(run_id: str, timestamp: datetime | None = None) -> RunStarted:
    """Create a RunStarted event for testing."""
    return RunStarted(
        timestamp=timestamp or datetime.now(tz=UTC),
        run_id=run_id,
        config_hash="abc123",
        source_plugin="csv",
    )


def make_run_completed(run_id: str, timestamp: datetime | None = None) -> RunCompleted:
    """Create a RunCompleted event for testing."""
    return RunCompleted(
        timestamp=timestamp or datetime.now(tz=UTC),
        run_id=run_id,
        status=RunStatus.COMPLETED,
        row_count=100,
        duration_ms=5000.0,
    )


# =============================================================================
# Basic Dispatching Tests
# =============================================================================


class TestBasicDispatching:
    """Tests for basic event dispatching to exporters."""

    def test_event_dispatched_to_single_exporter(self, base_run_id: str) -> None:
        """Event is dispatched to a single configured exporter."""
        exporter = MockExporter("test")
        manager = TelemetryManager(MockConfig(), exporters=[exporter])

        event = make_run_started(base_run_id)
        manager.handle_event(event)

        assert len(exporter.exports) == 1
        assert exporter.exports[0] is event

    def test_event_dispatched_to_multiple_exporters(self, base_run_id: str) -> None:
        """Event is dispatched to all configured exporters."""
        exporter1 = MockExporter("exporter1")
        exporter2 = MockExporter("exporter2")
        exporter3 = MockExporter("exporter3")
        manager = TelemetryManager(MockConfig(), exporters=[exporter1, exporter2, exporter3])

        event = make_run_started(base_run_id)
        manager.handle_event(event)

        assert len(exporter1.exports) == 1
        assert len(exporter2.exports) == 1
        assert len(exporter3.exports) == 1
        assert exporter1.exports[0] is event
        assert exporter2.exports[0] is event
        assert exporter3.exports[0] is event

    def test_no_exporters_is_noop(self, base_run_id: str) -> None:
        """No error when no exporters are configured."""
        manager = TelemetryManager(MockConfig(), exporters=[])

        event = make_run_started(base_run_id)
        # Should not raise
        manager.handle_event(event)

        assert manager.health_metrics["events_emitted"] == 0
        assert manager.health_metrics["events_dropped"] == 0


# =============================================================================
# Granularity Filtering Tests
# =============================================================================


class TestGranularityFiltering:
    """Tests for granularity-based event filtering."""

    def test_lifecycle_granularity_passes_run_started(self, base_run_id: str) -> None:
        """RunStarted passes at LIFECYCLE granularity."""
        exporter = MockExporter("test")
        config = MockConfig(granularity=TelemetryGranularity.LIFECYCLE)
        manager = TelemetryManager(config, exporters=[exporter])

        event = make_run_started(base_run_id)
        manager.handle_event(event)

        assert len(exporter.exports) == 1

    def test_lifecycle_granularity_filters_row_events(self, base_run_id: str, base_timestamp: datetime) -> None:
        """Row events are filtered at LIFECYCLE granularity."""
        from elspeth.telemetry import RowCreated

        exporter = MockExporter("test")
        config = MockConfig(granularity=TelemetryGranularity.LIFECYCLE)
        manager = TelemetryManager(config, exporters=[exporter])

        event = RowCreated(
            timestamp=base_timestamp,
            run_id=base_run_id,
            row_id="row-1",
            token_id="token-1",
            content_hash="hash",
        )
        manager.handle_event(event)

        # Event should be filtered, not dispatched
        assert len(exporter.exports) == 0


# =============================================================================
# Exporter Failure Isolation Tests
# =============================================================================


class TestExporterFailureIsolation:
    """Tests for exporter failure isolation - one failure shouldn't affect others."""

    def test_single_exporter_failure_logged_as_warning(self, base_run_id: str) -> None:
        """Individual exporter failure is logged as warning."""
        failing_exporter = MockExporter("failing", fail_export=True)
        manager = TelemetryManager(MockConfig(), exporters=[failing_exporter])

        with patch("elspeth.telemetry.manager.logger") as mock_logger:
            event = make_run_started(base_run_id)
            manager.handle_event(event)

            mock_logger.warning.assert_called_once()
            call_args = mock_logger.warning.call_args
            assert call_args[0][0] == "Telemetry exporter failed"
            assert call_args[1]["exporter"] == "failing"

    def test_one_failing_exporter_doesnt_stop_others(self, base_run_id: str) -> None:
        """One failing exporter doesn't prevent other exporters from receiving events."""
        working_exporter1 = MockExporter("working1")
        failing_exporter = MockExporter("failing", fail_export=True)
        working_exporter2 = MockExporter("working2")
        manager = TelemetryManager(MockConfig(), exporters=[working_exporter1, failing_exporter, working_exporter2])

        event = make_run_started(base_run_id)
        manager.handle_event(event)

        # Working exporters still receive the event
        assert len(working_exporter1.exports) == 1
        assert len(working_exporter2.exports) == 1

    def test_partial_success_counts_as_emitted(self, base_run_id: str) -> None:
        """Partial success (some exporters work) counts as emitted, not dropped."""
        working_exporter = MockExporter("working")
        failing_exporter = MockExporter("failing", fail_export=True)
        manager = TelemetryManager(MockConfig(), exporters=[working_exporter, failing_exporter])

        event = make_run_started(base_run_id)
        manager.handle_event(event)

        assert manager.health_metrics["events_emitted"] == 1
        assert manager.health_metrics["events_dropped"] == 0

    def test_partial_success_resets_consecutive_failures(self, base_run_id: str) -> None:
        """Partial success resets the consecutive total failure counter."""
        working_exporter = MockExporter("working")
        failing_exporter = MockExporter("failing", fail_export=True)
        manager = TelemetryManager(MockConfig(), exporters=[working_exporter, failing_exporter])

        # Simulate prior total failures by setting internal state
        manager._consecutive_total_failures = 5

        event = make_run_started(base_run_id)
        manager.handle_event(event)

        # Partial success resets the counter
        assert manager._consecutive_total_failures == 0


# =============================================================================
# Total Exporter Failure Tests
# =============================================================================


class TestTotalExporterFailure:
    """Tests for behavior when ALL exporters fail."""

    def test_all_exporters_fail_increments_dropped_count(self, base_run_id: str) -> None:
        """When all exporters fail, event is counted as dropped."""
        failing1 = MockExporter("failing1", fail_export=True)
        failing2 = MockExporter("failing2", fail_export=True)
        manager = TelemetryManager(MockConfig(), exporters=[failing1, failing2])

        event = make_run_started(base_run_id)
        manager.handle_event(event)

        assert manager.health_metrics["events_emitted"] == 0
        assert manager.health_metrics["events_dropped"] == 1

    def test_all_exporters_fail_increments_consecutive_count(self, base_run_id: str) -> None:
        """Consecutive total failures are tracked."""
        failing = MockExporter("failing", fail_export=True)
        manager = TelemetryManager(MockConfig(), exporters=[failing])

        for _ in range(5):
            manager.handle_event(make_run_started(base_run_id))

        assert manager._consecutive_total_failures == 5
        assert manager.health_metrics["events_dropped"] == 5

    def test_aggregate_logging_at_100_drops(self, base_run_id: str) -> None:
        """Aggregate error logged every 100 total failures.

        Note: By default, fail_on_total_exporter_failure=False causes the manager
        to disable itself after 10 consecutive failures. To test aggregate logging
        at 100 drops, we need fail_on_total_exporter_failure=True (which raises
        instead of disabling) OR we need to reset the consecutive counter somehow.

        This test verifies the LOG_INTERVAL logic by using a modified approach:
        we create multiple manager instances to avoid the disable threshold.
        """
        # Test the aggregate logging logic by setting a higher threshold
        failing = MockExporter("failing", fail_export=True)
        manager = TelemetryManager(MockConfig(), exporters=[failing])
        # Override the max_consecutive_failures to allow more events
        manager._max_consecutive_failures = 200

        with patch("elspeth.telemetry.manager.logger") as mock_logger:
            # Send 100 events (all will fail)
            for _ in range(100):
                manager.handle_event(make_run_started(base_run_id))

            # Should have logged aggregate error once
            assert mock_logger.error.call_count == 1
            call_args = mock_logger.error.call_args
            assert call_args[0][0] == "ALL telemetry exporters failing - events dropped"
            assert call_args[1]["dropped_total"] == 100

    def test_aggregate_logging_at_every_100_drops(self, base_run_id: str) -> None:
        """Aggregate error logged at every 100 drop milestone."""
        failing = MockExporter("failing", fail_export=True)
        manager = TelemetryManager(MockConfig(), exporters=[failing])
        # Override the max_consecutive_failures to allow more events
        manager._max_consecutive_failures = 500

        with patch("elspeth.telemetry.manager.logger") as mock_logger:
            # Send 350 events
            for _ in range(350):
                manager.handle_event(make_run_started(base_run_id))

            # Should have logged 3 times (at 100, 200, 300)
            assert mock_logger.error.call_count == 3

    def test_fail_on_total_failure_false_logs_critical_and_continues(self, base_run_id: str) -> None:
        """With fail_on_total_exporter_failure=False, logs CRITICAL and disables telemetry."""
        failing = MockExporter("failing", fail_export=True)
        config = MockConfig(fail_on_total_exporter_failure=False)
        manager = TelemetryManager(config, exporters=[failing])

        with patch("elspeth.telemetry.manager.logger") as mock_logger:
            # Send enough events to trigger the threshold (10 consecutive failures)
            for _ in range(10):
                manager.handle_event(make_run_started(base_run_id))

            # Should have logged CRITICAL
            mock_logger.critical.assert_called_once()
            call_args = mock_logger.critical.call_args
            assert call_args[0][0] == "Telemetry disabled after repeated total failures"

    def test_fail_on_total_failure_false_disables_further_events(self, base_run_id: str) -> None:
        """After telemetry is disabled, further events are silently dropped."""
        failing = MockExporter("failing", fail_export=True)
        config = MockConfig(fail_on_total_exporter_failure=False)
        manager = TelemetryManager(config, exporters=[failing])

        with patch("elspeth.telemetry.manager.logger"):
            # Trigger disable
            for _ in range(10):
                manager.handle_event(make_run_started(base_run_id))

            # Telemetry should now be disabled
            assert manager._disabled is True

            # Further events don't increment counters
            initial_dropped = manager.health_metrics["events_dropped"]
            for _ in range(5):
                manager.handle_event(make_run_started(base_run_id))

            assert manager.health_metrics["events_dropped"] == initial_dropped

    def test_fail_on_total_failure_true_raises_exception(self, base_run_id: str) -> None:
        """With fail_on_total_exporter_failure=True, raises TelemetryExporterError."""
        failing = MockExporter("failing", fail_export=True)
        config = MockConfig(fail_on_total_exporter_failure=True)
        manager = TelemetryManager(config, exporters=[failing])

        # First 9 failures should not raise
        for _ in range(9):
            manager.handle_event(make_run_started(base_run_id))

        # 10th failure should raise
        with pytest.raises(TelemetryExporterError) as exc_info:
            manager.handle_event(make_run_started(base_run_id))

        assert exc_info.value.exporter_name == "all"
        assert "10 consecutive times" in str(exc_info.value)


# =============================================================================
# Health Metrics Tests
# =============================================================================


class TestHealthMetrics:
    """Tests for health metrics tracking."""

    def test_initial_metrics(self) -> None:
        """Initial health metrics are all zeros."""
        manager = TelemetryManager(MockConfig(), exporters=[MockExporter("test")])

        metrics = manager.health_metrics
        assert metrics["events_emitted"] == 0
        assert metrics["events_dropped"] == 0
        assert metrics["exporter_failures"] == {}
        assert metrics["consecutive_total_failures"] == 0

    def test_events_emitted_increments(self, base_run_id: str) -> None:
        """events_emitted increments on successful dispatch."""
        exporter = MockExporter("test")
        manager = TelemetryManager(MockConfig(), exporters=[exporter])

        for _ in range(5):
            manager.handle_event(make_run_started(base_run_id))

        assert manager.health_metrics["events_emitted"] == 5

    def test_exporter_failures_tracked_per_exporter(self, base_run_id: str) -> None:
        """Per-exporter failure counts are tracked."""
        failing1 = MockExporter("failing1", fail_export=True)
        failing2 = MockExporter("failing2", fail_export=True)
        manager = TelemetryManager(MockConfig(), exporters=[failing1, failing2])

        for _ in range(3):
            manager.handle_event(make_run_started(base_run_id))

        failures = manager.health_metrics["exporter_failures"]
        assert failures["failing1"] == 3
        assert failures["failing2"] == 3

    def test_health_metrics_returns_copy(self, base_run_id: str) -> None:
        """health_metrics returns a copy of exporter_failures dict."""
        failing = MockExporter("failing", fail_export=True)
        manager = TelemetryManager(MockConfig(), exporters=[failing])
        manager.handle_event(make_run_started(base_run_id))

        metrics = manager.health_metrics
        metrics["exporter_failures"]["failing"] = 999

        # Internal state should not be modified
        assert manager.health_metrics["exporter_failures"]["failing"] == 1


# =============================================================================
# Flush and Close Tests
# =============================================================================


class TestFlushAndClose:
    """Tests for flush() and close() methods."""

    def test_flush_calls_all_exporters(self) -> None:
        """flush() calls flush() on all exporters."""
        exporter1 = MockExporter("exporter1")
        exporter2 = MockExporter("exporter2")
        manager = TelemetryManager(MockConfig(), exporters=[exporter1, exporter2])

        manager.flush()

        assert exporter1.flush_count == 1
        assert exporter2.flush_count == 1

    def test_flush_failure_logged_but_continues(self) -> None:
        """Exporter flush failure is logged but doesn't stop other exporters."""
        failing = MockExporter("failing", fail_flush=True)
        working = MockExporter("working")
        manager = TelemetryManager(MockConfig(), exporters=[failing, working])

        with patch("elspeth.telemetry.manager.logger") as mock_logger:
            manager.flush()

            mock_logger.warning.assert_called_once()
            call_args = mock_logger.warning.call_args
            assert call_args[0][0] == "Exporter flush failed"
            assert call_args[1]["exporter"] == "failing"

        # Working exporter was still flushed
        assert working.flush_count == 1

    def test_close_calls_all_exporters(self) -> None:
        """close() calls close() on all exporters."""
        exporter1 = MockExporter("exporter1")
        exporter2 = MockExporter("exporter2")
        manager = TelemetryManager(MockConfig(), exporters=[exporter1, exporter2])

        manager.close()

        assert exporter1.close_count == 1
        assert exporter2.close_count == 1

    def test_close_failure_logged_but_continues(self) -> None:
        """Exporter close failure is logged but doesn't stop other exporters."""
        failing = MockExporter("failing", fail_close=True)
        working = MockExporter("working")
        manager = TelemetryManager(MockConfig(), exporters=[failing, working])

        with patch("elspeth.telemetry.manager.logger") as mock_logger:
            manager.close()

            # Should have one warning for failure, one info for closing
            assert mock_logger.warning.call_count == 1
            assert mock_logger.info.call_count == 1

        # Working exporter was still closed
        assert working.close_count == 1

    def test_close_logs_final_metrics(self, base_run_id: str) -> None:
        """close() logs final health metrics."""
        exporter = MockExporter("test")
        manager = TelemetryManager(MockConfig(), exporters=[exporter])

        # Emit some events
        for _ in range(5):
            manager.handle_event(make_run_started(base_run_id))

        with patch("elspeth.telemetry.manager.logger") as mock_logger:
            manager.close()

            mock_logger.info.assert_called_once()
            call_args = mock_logger.info.call_args
            assert call_args[0][0] == "Telemetry manager closing"
            assert call_args[1]["events_emitted"] == 5


# =============================================================================
# Edge Cases
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_log_interval_is_100(self) -> None:
        """LOG_INTERVAL constant is 100."""
        assert TelemetryManager._LOG_INTERVAL == 100

    def test_max_consecutive_failures_is_10(self) -> None:
        """Default max consecutive failures threshold is 10."""
        manager = TelemetryManager(MockConfig(), exporters=[])
        assert manager._max_consecutive_failures == 10

    def test_success_after_total_failures_resets_counter(self, base_run_id: str) -> None:
        """Successful dispatch after total failures resets consecutive counter."""

        # Create an exporter that can be toggled
        class ToggleableExporter(MockExporter):
            def export(self, event: TelemetryEvent) -> None:
                if self._fail_export:
                    raise RuntimeError("Simulated failure")
                self.exports.append(event)

        exporter = ToggleableExporter("toggled")
        exporter._fail_export = True
        manager = TelemetryManager(MockConfig(), exporters=[exporter])

        # Accumulate some consecutive failures
        for _ in range(5):
            manager.handle_event(make_run_started(base_run_id))

        assert manager._consecutive_total_failures == 5

        # Fix the exporter and send another event
        exporter._fail_export = False
        manager.handle_event(make_run_started(base_run_id))

        # Counter should be reset
        assert manager._consecutive_total_failures == 0


# =============================================================================
# Property-Based State Machine Tests
# =============================================================================


class TelemetryManagerStateMachine(RuleBasedStateMachine):
    """State machine for property-based testing of TelemetryManager.

    Tests invariants:
    - events_emitted + events_dropped == total events that passed filtering
    - consecutive_total_failures resets to 0 on any success
    - exporter_failures[name] >= events where that exporter failed
    """

    def __init__(self) -> None:
        super().__init__()
        self.working_exporter = MockExporter("working")
        self.failing_exporter = MockExporter("failing", fail_export=True)
        self.manager = TelemetryManager(
            MockConfig(),
            exporters=[self.working_exporter, self.failing_exporter],
        )
        self.total_events_sent = 0

    events = Bundle("events")

    @rule(target=events, run_id=st.text(min_size=1, max_size=20))
    def create_event(self, run_id: str) -> TelemetryEvent:
        """Create a new event."""
        return make_run_started(run_id)

    @rule(event=events)
    def send_event(self, event: TelemetryEvent) -> None:
        """Send an event to the manager."""
        self.manager.handle_event(event)
        self.total_events_sent += 1

        # Check invariant: events_emitted + events_dropped <= total_events_sent
        metrics = self.manager.health_metrics
        assert metrics["events_emitted"] + metrics["events_dropped"] <= self.total_events_sent

    @rule()
    def check_partial_success_is_emitted(self) -> None:
        """With one working and one failing exporter, events should be emitted, not dropped."""
        metrics = self.manager.health_metrics
        # All events should be emitted (partial success counts as emitted)
        assert metrics["events_emitted"] == self.total_events_sent
        assert metrics["events_dropped"] == 0

    @rule()
    def check_consecutive_failures_zero(self) -> None:
        """With a working exporter, consecutive_total_failures should always be 0."""
        metrics = self.manager.health_metrics
        assert metrics["consecutive_total_failures"] == 0


TestStateMachine = TelemetryManagerStateMachine.TestCase


class AllFailingStateMachine(RuleBasedStateMachine):
    """State machine for testing when all exporters fail."""

    def __init__(self) -> None:
        super().__init__()
        self.failing1 = MockExporter("failing1", fail_export=True)
        self.failing2 = MockExporter("failing2", fail_export=True)
        # Don't crash on failure for this test
        self.manager = TelemetryManager(
            MockConfig(fail_on_total_exporter_failure=False),
            exporters=[self.failing1, self.failing2],
        )
        self.total_events_sent = 0

    @rule(run_id=st.text(min_size=1, max_size=20))
    def send_event(self, run_id: str) -> None:
        """Send an event that will fail."""
        # Suppress logging during property tests
        with patch("elspeth.telemetry.manager.logger"):
            event = make_run_started(run_id)
            self.manager.handle_event(event)
            self.total_events_sent += 1

    @rule()
    def check_all_dropped(self) -> None:
        """All events should be dropped when all exporters fail."""
        if self.manager._disabled:
            # After disabled, count stops incrementing
            return
        metrics = self.manager.health_metrics
        assert metrics["events_emitted"] == 0
        # Before disable threshold, all events are dropped
        if self.total_events_sent <= 10:
            assert metrics["events_dropped"] == self.total_events_sent


TestAllFailingStateMachine = AllFailingStateMachine.TestCase


# =============================================================================
# Additional Property Tests
# =============================================================================


class TestPropertyBasedInvariants:
    """Property-based tests for TelemetryManager invariants."""

    @given(num_events=st.integers(min_value=0, max_value=50))
    @hypothesis_settings(max_examples=25)
    def test_emitted_count_matches_successful_exports(self, num_events: int) -> None:
        """Property: events_emitted equals number of events exported to at least one exporter."""
        exporter = MockExporter("test")
        manager = TelemetryManager(MockConfig(), exporters=[exporter])

        for i in range(num_events):
            manager.handle_event(make_run_started(f"run-{i}"))

        assert manager.health_metrics["events_emitted"] == num_events
        assert len(exporter.exports) == num_events

    @given(num_events=st.integers(min_value=0, max_value=50))
    @hypothesis_settings(max_examples=25)
    def test_dropped_count_when_all_fail(self, num_events: int) -> None:
        """Property: events_dropped equals num_events when all exporters fail (before disable)."""
        failing = MockExporter("failing", fail_export=True)
        # Don't crash on failure
        config = MockConfig(fail_on_total_exporter_failure=False)
        manager = TelemetryManager(config, exporters=[failing])

        with patch("elspeth.telemetry.manager.logger"):
            for i in range(num_events):
                manager.handle_event(make_run_started(f"run-{i}"))

        # After disable threshold (10), events stop being counted
        if num_events <= 10:
            assert manager.health_metrics["events_dropped"] == num_events
        else:
            assert manager.health_metrics["events_dropped"] == 10  # Stopped at disable threshold
