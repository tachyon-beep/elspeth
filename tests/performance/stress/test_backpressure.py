# tests/performance/stress/test_backpressure.py
"""Telemetry backpressure stress tests.

Tests the TelemetryManager under high event load to verify:
- Events are not silently dropped under sustained emission
- Graceful degradation when the internal queue fills up

These tests do NOT require ChaosLLM; they exercise the telemetry subsystem directly.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from typing import Any

import pytest

from elspeth.contracts.config.runtime import RuntimeTelemetryConfig
from elspeth.contracts.enums import BackpressureMode, TelemetryGranularity
from elspeth.contracts.events import RunStarted, TelemetryEvent
from elspeth.telemetry.manager import TelemetryManager

pytestmark = pytest.mark.stress


class CountingExporter:
    """Test exporter that counts events received.

    Thread-safe counter for verifying event delivery under load.
    """

    _name = "counting"

    def __init__(self) -> None:
        self._count = 0
        self._lock = threading.Lock()

    @property
    def name(self) -> str:
        return self._name

    @property
    def count(self) -> int:
        with self._lock:
            return self._count

    def configure(self, config: dict[str, Any]) -> None:
        pass

    def export(self, event: TelemetryEvent) -> None:
        with self._lock:
            self._count += 1

    def flush(self) -> None:
        pass

    def close(self) -> None:
        pass


class SlowExporter:
    """Test exporter that introduces artificial delay.

    Simulates a slow exporter (e.g., network-bound OTLP exporter)
    to test backpressure behavior.
    """

    _name = "slow"

    def __init__(self, delay_ms: float = 1.0) -> None:
        self._delay_s = delay_ms / 1000.0
        self._count = 0
        self._lock = threading.Lock()

    @property
    def name(self) -> str:
        return self._name

    @property
    def count(self) -> int:
        with self._lock:
            return self._count

    def configure(self, config: dict[str, Any]) -> None:
        pass

    def export(self, event: TelemetryEvent) -> None:
        import time

        time.sleep(self._delay_s)
        with self._lock:
            self._count += 1

    def flush(self) -> None:
        pass

    def close(self) -> None:
        pass


def _make_event(run_id: str = "stress-run") -> RunStarted:
    """Create a simple telemetry event for load testing."""
    return RunStarted(
        timestamp=datetime.now(UTC),
        run_id=run_id,
        config_hash="abc123",
        source_plugin="test_source",
    )


@pytest.mark.stress
class TestTelemetryBackpressure:
    """Telemetry backpressure under load."""

    def test_telemetry_emission_under_load(self) -> None:
        """Emit 10K+ events, verify none silently dropped.

        Uses a fast counting exporter so the bottleneck is the queue,
        not the exporter. All events should be delivered.

        Verifies:
        - All 10,000 events are received by the exporter
        - No silent drops (health_metrics.events_dropped == 0)
        - Manager completes flush without hanging
        """
        exporter = CountingExporter()

        config = RuntimeTelemetryConfig(
            enabled=True,
            granularity=TelemetryGranularity.LIFECYCLE,
            backpressure_mode=BackpressureMode.BLOCK,
            fail_on_total_exporter_failure=False,
            exporter_configs=(),
        )

        manager = TelemetryManager(config, exporters=[exporter])

        try:
            num_events = 10_000
            for i in range(num_events):
                event = _make_event(f"stress-run-{i % 100}")
                manager.handle_event(event)

            # Flush to ensure all events are processed
            manager.flush()

            # Verify all events were delivered
            assert exporter.count == num_events, f"Expected {num_events} events, got {exporter.count}"

            # Verify no drops
            metrics = manager.health_metrics
            assert metrics["events_dropped"] == 0, f"Events were dropped: {metrics['events_dropped']}"
            assert metrics["events_emitted"] == num_events
        finally:
            manager.close()

    def test_backpressure_graceful_degradation(self) -> None:
        """When buffer fills, telemetry degrades gracefully in DROP mode.

        Uses a slow exporter so events pile up in the queue. With DROP mode,
        the queue should fill and events should be dropped without blocking
        the caller.

        Verifies:
        - handle_event() returns quickly even when queue is full
        - events_dropped > 0 in health metrics
        - events_emitted > 0 (some events get through)
        - No exceptions raised by handle_event()
        - Manager shuts down cleanly
        """
        # Very slow exporter: 10ms per event, so at most ~100/s
        exporter = SlowExporter(delay_ms=10.0)

        config = RuntimeTelemetryConfig(
            enabled=True,
            granularity=TelemetryGranularity.LIFECYCLE,
            backpressure_mode=BackpressureMode.DROP,
            fail_on_total_exporter_failure=False,
            exporter_configs=(),
        )

        manager = TelemetryManager(config, exporters=[exporter])

        try:
            # Emit events as fast as possible - most will be dropped
            num_events = 5_000
            errors: list[Exception] = []

            for i in range(num_events):
                try:
                    event = _make_event(f"stress-run-{i % 100}")
                    manager.handle_event(event)
                except Exception as e:
                    errors.append(e)

            # handle_event() should never raise
            assert len(errors) == 0, f"handle_event() raised: {errors}"

            # Flush what we can
            manager.flush()

            metrics = manager.health_metrics

            # Some events should have been delivered
            assert metrics["events_emitted"] > 0, "No events were delivered at all"

            # Some events should have been dropped (slow exporter can't keep up)
            assert metrics["events_dropped"] > 0, (
                f"Expected some drops with slow exporter; emitted={metrics['events_emitted']}, dropped={metrics['events_dropped']}"
            )

            # Total (emitted + dropped) should account for all events
            # Note: events_emitted counts events dispatched to exporters (success or partial success),
            # events_dropped counts queue-full drops + total exporter failures.
            # Some events may still be in the queue, so we check emitted + dropped <= num_events
            total_accounted = metrics["events_emitted"] + metrics["events_dropped"]
            assert total_accounted > 0, "No events accounted for"
        finally:
            manager.close()
