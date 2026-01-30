"""Tests for contracts/events.py exports."""

from datetime import UTC, datetime


def test_transform_completed_in_contracts():
    """TransformCompleted should be importable from contracts."""
    from elspeth.contracts import TransformCompleted
    from elspeth.contracts.enums import NodeStateStatus

    event = TransformCompleted(
        timestamp=datetime.now(UTC),
        run_id="run-1",
        row_id="row-1",
        token_id="token-1",
        node_id="node-1",
        plugin_name="test",
        status=NodeStateStatus.COMPLETED,
        duration_ms=100.0,
        input_hash="abc",
        output_hash="def",
    )
    assert event.run_id == "run-1"


def test_gate_evaluated_in_contracts():
    """GateEvaluated should be importable from contracts."""
    from elspeth.contracts import GateEvaluated
    from elspeth.contracts.enums import RoutingMode

    event = GateEvaluated(
        timestamp=datetime.now(UTC),
        run_id="run-1",
        row_id="row-1",
        token_id="token-1",
        node_id="gate-1",
        plugin_name="test_gate",
        routing_mode=RoutingMode.MOVE,
        destinations=("sink1",),
    )
    assert event.destinations == ("sink1",)


def test_token_completed_in_contracts():
    """TokenCompleted should be importable from contracts."""
    from elspeth.contracts import TokenCompleted
    from elspeth.contracts.enums import RowOutcome

    event = TokenCompleted(
        timestamp=datetime.now(UTC),
        run_id="run-1",
        row_id="row-1",
        token_id="token-1",
        outcome=RowOutcome.COMPLETED,
        sink_name="output",
    )
    assert event.outcome == RowOutcome.COMPLETED


def test_telemetry_events_inherit_from_contracts_base():
    """Telemetry-specific events should inherit from contracts TelemetryEvent."""
    from elspeth.contracts.events import TelemetryEvent
    from elspeth.telemetry.events import (
        ExternalCallCompleted,
        PhaseChanged,
        RowCreated,
        RunCompleted,
        RunStarted,
    )

    assert issubclass(RunStarted, TelemetryEvent)
    assert issubclass(RunCompleted, TelemetryEvent)
    assert issubclass(PhaseChanged, TelemetryEvent)
    assert issubclass(RowCreated, TelemetryEvent)
    assert issubclass(ExternalCallCompleted, TelemetryEvent)
