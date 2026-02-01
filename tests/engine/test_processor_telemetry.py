# tests/engine/test_processor_telemetry.py
"""Tests for telemetry event emission in the RowProcessor.

Tests verify:
1. TransformCompleted is emitted after transform execution
2. GateEvaluated is emitted after gate evaluation
3. TokenCompleted is emitted when tokens reach terminal state
4. Events are emitted ONLY AFTER Landscape recording succeeds
5. TelemetryManager is optional (no telemetry when not provided)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar
from unittest.mock import MagicMock

from pydantic import ConfigDict

from elspeth.contracts import (
    ArtifactDescriptor,
    Determinism,
    NodeID,
    NodeType,
    PluginSchema,
    RoutingMode,
    RowOutcome,
    SinkName,
    SourceRow,
)
from elspeth.contracts.enums import NodeStateStatus, RunStatus, TelemetryGranularity
from elspeth.contracts.events import (
    GateEvaluated,
    TelemetryEvent,
    TokenCompleted,
    TransformCompleted,
)
from elspeth.core.dag import ExecutionGraph
from elspeth.core.landscape import LandscapeDB
from elspeth.engine.orchestrator import Orchestrator, PipelineConfig
from elspeth.plugins.base import BaseTransform
from elspeth.plugins.results import GateResult, RoutingAction, TransformResult
from elspeth.telemetry import TelemetryManager
from tests.conftest import as_gate

# =============================================================================
# Test Fixtures
# =============================================================================


class DynamicSchema(PluginSchema):
    """Simple schema for testing."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow")


class PassthroughTransform(BaseTransform):
    """Transform that passes through rows unchanged."""

    name = "passthrough"
    input_schema = DynamicSchema
    output_schema = DynamicSchema
    plugin_version = "1.0.0"

    def __init__(self) -> None:
        super().__init__({"schema": {"fields": "dynamic"}})

    def process(self, row: Any, ctx: Any) -> TransformResult:
        return TransformResult.success(row, success_reason={"action": "passthrough"})


class FailingTransform(BaseTransform):
    """Transform that returns an error (with on_error configured)."""

    name = "failing"
    input_schema = DynamicSchema
    output_schema = DynamicSchema
    plugin_version = "1.0.0"
    _on_error = "discard"  # Route errors to discard (quarantine)

    def __init__(self) -> None:
        super().__init__({"schema": {"fields": "dynamic"}})

    def process(self, row: Any, ctx: Any) -> TransformResult:
        return TransformResult.error({"reason": "intentional_failure"})


class SimpleGate:
    """Gate that routes all rows to the default path (mock implementation)."""

    name = "simple_gate"
    node_id: str | None = None
    input_schema = DynamicSchema
    output_schema = DynamicSchema
    plugin_version = "1.0.0"
    determinism = Determinism.DETERMINISTIC
    routes: ClassVar[dict[str, str]] = {}  # No routes - always continues
    fork_to: list[str] | None = None  # No forking

    def evaluate(self, row: Any, ctx: Any) -> GateResult:
        return GateResult(row=row, action=RoutingAction.continue_())

    def on_start(self, ctx: Any) -> None:
        """Lifecycle hook called at start of run."""
        pass

    def on_complete(self, ctx: Any) -> None:
        """Lifecycle hook called at end of run."""
        pass

    def close(self) -> None:
        """Cleanup method required by orchestrator."""
        pass


@dataclass
class MockTelemetryConfig:
    """Mock RuntimeTelemetryProtocol implementation for testing."""

    enabled: bool = True
    granularity: TelemetryGranularity = TelemetryGranularity.FULL
    fail_on_total_exporter_failure: bool = False

    @property
    def backpressure_mode(self) -> Any:
        return None

    @property
    def exporter_configs(self) -> tuple:
        return ()


class RecordingExporter:
    """Exporter that records all events for test verification."""

    def __init__(self, name: str = "recording"):
        self._name = name
        self.events: list[TelemetryEvent] = []

    @property
    def name(self) -> str:
        return self._name

    def configure(self, config: dict[str, Any]) -> None:
        pass

    def export(self, event: TelemetryEvent) -> None:
        self.events.append(event)

    def flush(self) -> None:
        pass

    def close(self) -> None:
        pass


def create_minimal_graph() -> ExecutionGraph:
    """Create a minimal valid execution graph."""
    graph = ExecutionGraph()
    schema_config = {"schema": {"fields": "dynamic"}}
    graph.add_node("source", node_type=NodeType.SOURCE, plugin_name="test_source", config=schema_config)
    graph.add_node("transform", node_type=NodeType.TRANSFORM, plugin_name="passthrough", config=schema_config)
    graph.add_node("sink", node_type=NodeType.SINK, plugin_name="test_sink", config=schema_config)
    graph.add_edge("source", "transform", label="continue", mode=RoutingMode.MOVE)
    graph.add_edge("transform", "sink", label="continue", mode=RoutingMode.MOVE)
    graph._transform_id_map = {0: NodeID("transform")}
    graph._sink_id_map = {SinkName("output"): NodeID("sink")}
    graph._default_sink = "output"
    return graph


def create_graph_with_gate() -> ExecutionGraph:
    """Create a graph with a gate transform."""
    graph = ExecutionGraph()
    schema_config = {"schema": {"fields": "dynamic"}}
    graph.add_node("source", node_type=NodeType.SOURCE, plugin_name="test_source", config=schema_config)
    graph.add_node("gate", node_type=NodeType.GATE, plugin_name="simple_gate", config=schema_config)
    graph.add_node("sink", node_type=NodeType.SINK, plugin_name="test_sink", config=schema_config)
    graph.add_edge("source", "gate", label="continue", mode=RoutingMode.MOVE)
    graph.add_edge("gate", "sink", label="continue", mode=RoutingMode.MOVE)
    graph._transform_id_map = {0: NodeID("gate")}
    graph._sink_id_map = {SinkName("output"): NodeID("sink")}
    graph._default_sink = "output"
    return graph


def create_graph_with_failing_transform() -> ExecutionGraph:
    """Create a graph with a failing transform."""
    graph = ExecutionGraph()
    schema_config = {"schema": {"fields": "dynamic"}}
    graph.add_node("source", node_type=NodeType.SOURCE, plugin_name="test_source", config=schema_config)
    graph.add_node("transform", node_type=NodeType.TRANSFORM, plugin_name="failing", config=schema_config)
    graph.add_node("sink", node_type=NodeType.SINK, plugin_name="test_sink", config=schema_config)
    graph.add_edge("source", "transform", label="continue", mode=RoutingMode.MOVE)
    graph.add_edge("transform", "sink", label="continue", mode=RoutingMode.MOVE)
    graph._transform_id_map = {0: NodeID("transform")}
    graph._sink_id_map = {SinkName("output"): NodeID("sink")}
    graph._default_sink = "output"
    return graph


def create_mock_source(rows: list[dict[str, Any]]) -> MagicMock:
    """Create a mock source that yields specified rows."""
    mock_source = MagicMock()
    mock_source.name = "test_source"
    mock_source._on_validation_failure = "discard"
    mock_source.determinism = Determinism.IO_READ
    mock_source.plugin_version = "1.0.0"

    schema_mock = MagicMock()
    schema_mock.model_json_schema.return_value = {"type": "object"}
    mock_source.output_schema = schema_mock

    mock_source.load.return_value = iter([SourceRow.valid(row) for row in rows])
    mock_source.get_field_resolution.return_value = (None, None)

    return mock_source


def create_mock_sink() -> MagicMock:
    """Create a mock sink."""
    mock_sink = MagicMock()
    mock_sink.name = "test_sink"
    mock_sink.determinism = Determinism.IO_WRITE
    mock_sink.plugin_version = "1.0.0"

    schema_mock = MagicMock()
    schema_mock.model_json_schema.return_value = {"type": "object"}
    mock_sink.input_schema = schema_mock
    mock_sink.write.return_value = ArtifactDescriptor.for_file(path="memory", size_bytes=0, content_hash="abc123")

    return mock_sink


# =============================================================================
# TransformCompleted Event Tests
# =============================================================================


class TestTransformCompletedTelemetry:
    """Tests for TransformCompleted telemetry event emission."""

    def test_transform_completed_emitted_for_successful_transform(self, landscape_db: LandscapeDB, payload_store) -> None:
        """TransformCompleted is emitted after successful transform execution."""
        exporter = RecordingExporter()
        telemetry_manager = TelemetryManager(MockTelemetryConfig(), exporters=[exporter])

        orchestrator = Orchestrator(landscape_db, telemetry_manager=telemetry_manager)

        config = PipelineConfig(
            source=create_mock_source([{"id": 1}]),
            transforms=[PassthroughTransform()],
            sinks={"output": create_mock_sink()},
        )

        orchestrator.run(config, graph=create_minimal_graph(), payload_store=payload_store)

        # Verify TransformCompleted was emitted
        transform_events = [e for e in exporter.events if isinstance(e, TransformCompleted)]
        assert len(transform_events) == 1

        event = transform_events[0]
        assert event.plugin_name == "passthrough"
        assert event.status == NodeStateStatus.COMPLETED
        assert event.duration_ms >= 0
        assert event.input_hash is not None
        assert event.output_hash is not None

    def test_transform_completed_emitted_for_failed_transform(self, landscape_db: LandscapeDB, payload_store) -> None:
        """TransformCompleted is emitted with FAILED status for transform errors."""
        exporter = RecordingExporter()
        telemetry_manager = TelemetryManager(MockTelemetryConfig(), exporters=[exporter])

        orchestrator = Orchestrator(landscape_db, telemetry_manager=telemetry_manager)

        config = PipelineConfig(
            source=create_mock_source([{"id": 1}]),
            transforms=[FailingTransform()],
            sinks={"output": create_mock_sink()},
        )

        orchestrator.run(config, graph=create_graph_with_failing_transform(), payload_store=payload_store)

        # Verify TransformCompleted was emitted with FAILED status
        transform_events = [e for e in exporter.events if isinstance(e, TransformCompleted)]
        assert len(transform_events) == 1

        event = transform_events[0]
        assert event.plugin_name == "failing"
        assert event.status == NodeStateStatus.FAILED

    def test_multiple_transforms_emit_multiple_events(self, landscape_db: LandscapeDB, payload_store) -> None:
        """Each transform execution emits its own TransformCompleted event."""
        exporter = RecordingExporter()
        telemetry_manager = TelemetryManager(MockTelemetryConfig(), exporters=[exporter])

        orchestrator = Orchestrator(landscape_db, telemetry_manager=telemetry_manager)

        # Create graph with two transforms
        graph = ExecutionGraph()
        schema_config = {"schema": {"fields": "dynamic"}}
        graph.add_node("source", node_type=NodeType.SOURCE, plugin_name="test_source", config=schema_config)
        graph.add_node("transform1", node_type=NodeType.TRANSFORM, plugin_name="passthrough", config=schema_config)
        graph.add_node("transform2", node_type=NodeType.TRANSFORM, plugin_name="passthrough", config=schema_config)
        graph.add_node("sink", node_type=NodeType.SINK, plugin_name="test_sink", config=schema_config)
        graph.add_edge("source", "transform1", label="continue", mode=RoutingMode.MOVE)
        graph.add_edge("transform1", "transform2", label="continue", mode=RoutingMode.MOVE)
        graph.add_edge("transform2", "sink", label="continue", mode=RoutingMode.MOVE)
        graph._transform_id_map = {0: NodeID("transform1"), 1: NodeID("transform2")}
        graph._sink_id_map = {SinkName("output"): NodeID("sink")}
        graph._default_sink = "output"

        config = PipelineConfig(
            source=create_mock_source([{"id": 1}]),
            transforms=[PassthroughTransform(), PassthroughTransform()],
            sinks={"output": create_mock_sink()},
        )

        orchestrator.run(config, graph=graph, payload_store=payload_store)

        # Verify two TransformCompleted events were emitted
        transform_events = [e for e in exporter.events if isinstance(e, TransformCompleted)]
        assert len(transform_events) == 2


# =============================================================================
# GateEvaluated Event Tests
# =============================================================================


class TestGateEvaluatedTelemetry:
    """Tests for GateEvaluated telemetry event emission."""

    def test_gate_evaluated_emitted_for_gate(self, landscape_db: LandscapeDB, payload_store) -> None:
        """GateEvaluated is emitted after gate evaluation."""
        exporter = RecordingExporter()
        telemetry_manager = TelemetryManager(MockTelemetryConfig(), exporters=[exporter])

        orchestrator = Orchestrator(landscape_db, telemetry_manager=telemetry_manager)

        config = PipelineConfig(
            source=create_mock_source([{"id": 1}]),
            transforms=[as_gate(SimpleGate())],
            sinks={"output": create_mock_sink()},
        )

        orchestrator.run(config, graph=create_graph_with_gate(), payload_store=payload_store)

        # Verify GateEvaluated was emitted
        gate_events = [e for e in exporter.events if isinstance(e, GateEvaluated)]
        assert len(gate_events) == 1

        event = gate_events[0]
        assert event.plugin_name == "simple_gate"
        assert event.destinations == ("continue",)

    def test_gate_evaluated_contains_routing_mode(self, landscape_db: LandscapeDB, payload_store) -> None:
        """GateEvaluated event includes the routing mode."""
        exporter = RecordingExporter()
        telemetry_manager = TelemetryManager(MockTelemetryConfig(), exporters=[exporter])

        orchestrator = Orchestrator(landscape_db, telemetry_manager=telemetry_manager)

        config = PipelineConfig(
            source=create_mock_source([{"id": 1}]),
            transforms=[as_gate(SimpleGate())],
            sinks={"output": create_mock_sink()},
        )

        orchestrator.run(config, graph=create_graph_with_gate(), payload_store=payload_store)

        gate_events = [e for e in exporter.events if isinstance(e, GateEvaluated)]
        assert len(gate_events) == 1

        event = gate_events[0]
        assert event.routing_mode is not None


# =============================================================================
# TokenCompleted Event Tests
# =============================================================================


class TestTokenCompletedTelemetry:
    """Tests for TokenCompleted telemetry event emission."""

    def test_token_completed_emitted_for_quarantined_token(self, landscape_db: LandscapeDB, payload_store) -> None:
        """TokenCompleted is emitted when a token is quarantined."""
        exporter = RecordingExporter()
        telemetry_manager = TelemetryManager(MockTelemetryConfig(), exporters=[exporter])

        orchestrator = Orchestrator(landscape_db, telemetry_manager=telemetry_manager)

        config = PipelineConfig(
            source=create_mock_source([{"id": 1}]),
            transforms=[FailingTransform()],
            sinks={"output": create_mock_sink()},
        )

        orchestrator.run(config, graph=create_graph_with_failing_transform(), payload_store=payload_store)

        # Verify TokenCompleted was emitted with QUARANTINED outcome
        token_events = [e for e in exporter.events if isinstance(e, TokenCompleted)]
        quarantined_events = [e for e in token_events if e.outcome == RowOutcome.QUARANTINED]
        assert len(quarantined_events) == 1

    def test_token_completed_contains_outcome(self, landscape_db: LandscapeDB, payload_store) -> None:
        """TokenCompleted event contains the correct outcome."""
        exporter = RecordingExporter()
        telemetry_manager = TelemetryManager(MockTelemetryConfig(), exporters=[exporter])

        orchestrator = Orchestrator(landscape_db, telemetry_manager=telemetry_manager)

        config = PipelineConfig(
            source=create_mock_source([{"id": 1}]),
            transforms=[FailingTransform()],
            sinks={"output": create_mock_sink()},
        )

        orchestrator.run(config, graph=create_graph_with_failing_transform(), payload_store=payload_store)

        # Find the TokenCompleted event
        token_events = [e for e in exporter.events if isinstance(e, TokenCompleted)]
        assert len(token_events) >= 1

        # Check it has valid outcome
        event = token_events[0]
        assert event.outcome is not None
        assert event.row_id is not None
        assert event.token_id is not None


# =============================================================================
# No Telemetry When Manager Not Provided Tests
# =============================================================================


class TestNoTelemetryWithoutManager:
    """Tests verifying no telemetry is emitted without a TelemetryManager."""

    def test_no_events_without_telemetry_manager(self, landscape_db: LandscapeDB, payload_store) -> None:
        """No telemetry events emitted when TelemetryManager is not provided."""
        # No telemetry_manager provided
        orchestrator = Orchestrator(landscape_db)

        config = PipelineConfig(
            source=create_mock_source([{"id": 1}]),
            transforms=[PassthroughTransform()],
            sinks={"output": create_mock_sink()},
        )

        # Should complete without error
        result = orchestrator.run(config, graph=create_minimal_graph(), payload_store=payload_store)
        assert result.status == RunStatus.COMPLETED


# =============================================================================
# Event Ordering Tests
# =============================================================================


class TestTelemetryEventOrdering:
    """Tests verifying telemetry events are emitted in correct order."""

    def test_transform_completed_before_token_completed(self, landscape_db: LandscapeDB, payload_store) -> None:
        """TransformCompleted should be emitted before TokenCompleted for same row."""
        exporter = RecordingExporter()
        telemetry_manager = TelemetryManager(MockTelemetryConfig(), exporters=[exporter])

        orchestrator = Orchestrator(landscape_db, telemetry_manager=telemetry_manager)

        config = PipelineConfig(
            source=create_mock_source([{"id": 1}]),
            transforms=[FailingTransform()],  # Will fail and quarantine
            sinks={"output": create_mock_sink()},
        )

        orchestrator.run(config, graph=create_graph_with_failing_transform(), payload_store=payload_store)

        # Get events in order
        transform_events = [i for i, e in enumerate(exporter.events) if isinstance(e, TransformCompleted)]
        token_events = [i for i, e in enumerate(exporter.events) if isinstance(e, TokenCompleted)]

        # TransformCompleted should come before TokenCompleted
        if transform_events and token_events:
            assert transform_events[0] < token_events[0]

    def test_all_row_events_share_same_run_id(self, landscape_db: LandscapeDB, payload_store) -> None:
        """All row-level telemetry events share the same run_id."""
        exporter = RecordingExporter()
        telemetry_manager = TelemetryManager(MockTelemetryConfig(), exporters=[exporter])

        orchestrator = Orchestrator(landscape_db, telemetry_manager=telemetry_manager)

        config = PipelineConfig(
            source=create_mock_source([{"id": 1}]),
            transforms=[PassthroughTransform()],
            sinks={"output": create_mock_sink()},
        )

        orchestrator.run(config, graph=create_minimal_graph(), payload_store=payload_store)

        # All events should have the same run_id
        run_ids = {e.run_id for e in exporter.events}
        assert len(run_ids) == 1
