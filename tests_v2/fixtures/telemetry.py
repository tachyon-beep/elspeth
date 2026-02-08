# tests_v2/fixtures/telemetry.py
"""Telemetry test fixtures for tests_v2.

Re-exports TelemetryTestExporter and MockTelemetryConfig from the
original test infrastructure. These are pure helper classes with no
dependency on old test conftest.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pytest

from elspeth.contracts.enums import BackpressureMode, TelemetryGranularity
from elspeth.telemetry import TelemetryManager

if TYPE_CHECKING:
    from elspeth.contracts.events import TelemetryEvent


class TelemetryTestExporter:
    """In-memory exporter that captures events for test verification.

    Implements ExporterProtocol and stores all events in memory
    for inspection during tests.
    """

    def __init__(self, name: str = "test"):
        self._name = name
        self.events: list[TelemetryEvent] = []
        self.flush_count = 0
        self.close_count = 0
        self._configured = False

    @property
    def name(self) -> str:
        return self._name

    def configure(self, config: dict[str, Any]) -> None:
        self._configured = True

    def export(self, event: TelemetryEvent) -> None:
        self.events.append(event)

    def flush(self) -> None:
        self.flush_count += 1

    def close(self) -> None:
        self.close_count += 1

    def assert_event_emitted(
        self,
        event_type: str | type,
        **filters: Any,
    ) -> TelemetryEvent:
        """Assert that an event matching the criteria was emitted."""
        type_name = event_type if isinstance(event_type, str) else event_type.__name__

        matches = []
        for event in self.events:
            if type(event).__name__ != type_name:
                continue

            all_match = True
            for key, expected in filters.items():
                actual = getattr(event, key, None)
                if actual is not None and hasattr(actual, "value"):
                    actual = actual.value
                if hasattr(expected, "value"):
                    expected = expected.value
                if actual != expected:
                    all_match = False
                    break

            if all_match:
                matches.append(event)

        assert matches, (
            f"No {type_name} event found with filters {filters}. "
            f"Events captured: {[type(e).__name__ for e in self.events]}"
        )
        return matches[0]

    def assert_no_event_emitted(self, event_type: str | type) -> None:
        """Assert that no event of this type was emitted."""
        type_name = event_type if isinstance(event_type, str) else event_type.__name__

        for event in self.events:
            if type(event).__name__ == type_name:
                raise AssertionError(f"Expected no {type_name} events, but found: {event}")

    def get_events_of_type(self, event_type: str | type) -> list[TelemetryEvent]:
        """Get all events of a specific type."""
        type_name = event_type if isinstance(event_type, str) else event_type.__name__
        return [e for e in self.events if type(e).__name__ == type_name]

    def clear(self) -> None:
        self.events.clear()

    @property
    def event_types(self) -> list[str]:
        return [type(e).__name__ for e in self.events]

    @property
    def event_count(self) -> int:
        return len(self.events)


@dataclass
class MockTelemetryConfig:
    """Mock RuntimeTelemetryProtocol implementation for testing."""

    enabled: bool = True
    granularity: TelemetryGranularity = TelemetryGranularity.FULL
    fail_on_total_exporter_failure: bool = False
    backpressure_mode: BackpressureMode = BackpressureMode.BLOCK

    @property
    def exporter_configs(self) -> tuple[()]:
        return ()


@pytest.fixture
def telemetry_test_exporter() -> TelemetryTestExporter:
    """Fixture providing a fresh test exporter."""
    return TelemetryTestExporter()


@pytest.fixture
def telemetry_config() -> MockTelemetryConfig:
    """Fixture providing default telemetry config."""
    return MockTelemetryConfig()


@pytest.fixture
def telemetry_manager_with_exporter(
    telemetry_test_exporter: TelemetryTestExporter,
    telemetry_config: MockTelemetryConfig,
) -> TelemetryManager:
    """Fixture providing TelemetryManager wired to test exporter."""
    return TelemetryManager(telemetry_config, exporters=[telemetry_test_exporter])
