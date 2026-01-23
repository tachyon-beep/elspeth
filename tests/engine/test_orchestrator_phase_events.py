"""Tests for phase event emission in Orchestrator.

Verifies that PhaseError events are emitted exactly once per failure,
and that failures are attributed to the correct phase (SOURCE vs PROCESS).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

import pytest

from elspeth.contracts import PluginSchema, RoutingMode, SourceRow
from elspeth.contracts.events import PhaseError, PipelinePhase
from elspeth.core.dag import ExecutionGraph
from elspeth.core.events import EventBus
from elspeth.plugins.base import BaseGate, BaseTransform
from tests.conftest import _TestSchema, _TestSinkBase, _TestSourceBase, as_sink, as_source

if TYPE_CHECKING:
    from elspeth.contracts.results import TransformResult
    from elspeth.engine.orchestrator import PipelineConfig


def _build_test_graph(config: PipelineConfig) -> ExecutionGraph:
    """Build a simple graph for testing (copied from test_orchestrator.py)."""
    graph = ExecutionGraph()

    # Add source
    graph.add_node("source", node_type="source", plugin_name=config.source.name)

    # Add transforms and populate transform_id_map
    transform_ids: dict[int, str] = {}
    prev = "source"
    for i, t in enumerate(config.transforms):
        node_id = f"transform_{i}"
        transform_ids[i] = node_id
        is_gate = isinstance(t, BaseGate)
        graph.add_node(
            node_id,
            node_type="gate" if is_gate else "transform",
            plugin_name=t.name,
        )
        graph.add_edge(prev, node_id, label="continue", mode=RoutingMode.MOVE)
        prev = node_id

    # Add sinks first (need sink_ids for gate routing)
    sink_ids: dict[str, str] = {}
    for sink_name, sink in config.sinks.items():
        node_id = f"sink_{sink_name}"
        sink_ids[sink_name] = node_id
        graph.add_node(node_id, node_type="sink", plugin_name=sink.name)

    # Populate route resolution map
    route_resolution_map: dict[tuple[str, str], str] = {}

    # Edge from last node to output sink
    if "default" in sink_ids:
        output_sink = "default"
    elif sink_ids:
        output_sink = next(iter(sink_ids))
    else:
        output_sink = ""

    if output_sink:
        graph.add_edge(prev, sink_ids[output_sink], label="continue", mode=RoutingMode.MOVE)

    # Populate internal ID maps (required by orchestrator)
    graph._sink_id_map = sink_ids
    graph._transform_id_map = transform_ids
    graph._config_gate_id_map = {}
    graph._route_resolution_map = route_resolution_map
    graph._output_sink = output_sink

    return graph


class TestPhaseErrorEmission:
    """Test that PhaseError events are emitted correctly."""

    def test_process_failure_emits_single_phase_error(self) -> None:
        """PROCESS phase failure should emit exactly ONE PhaseError(PROCESS)."""
        from elspeth.core.landscape import LandscapeDB
        from elspeth.engine.orchestrator import Orchestrator, PipelineConfig

        db = LandscapeDB.in_memory()

        class ValueSchema(PluginSchema):
            value: int

        class ListSource(_TestSourceBase):
            name = "test_source"
            output_schema = ValueSchema

            def __init__(self, data: list[dict[str, Any]]) -> None:
                self._data = data

            def on_start(self, ctx: Any) -> None:
                pass

            def load(self, ctx: Any) -> Iterator[SourceRow]:
                for row in self._data:
                    yield SourceRow.valid(row)

            def close(self) -> None:
                pass

        class ExplodingTransform(BaseTransform):
            name = "exploding"
            input_schema = ValueSchema
            output_schema = ValueSchema

            def __init__(self) -> None:
                super().__init__({})

            def process(self, row: Any, ctx: Any) -> TransformResult:
                raise RuntimeError("Transform exploded!")

        class CollectSink(_TestSinkBase):
            name = "default"

            def __init__(self) -> None:
                self.results: list[dict[str, Any]] = []

            def on_start(self, ctx: Any) -> None:
                pass

            def write(self, row: dict[str, Any], ctx: Any) -> None:
                self.results.append(row)

            def close(self) -> None:
                pass

        # Create pipeline with failing transform
        source = as_source(ListSource([{"value": 42}]))
        transform = ExplodingTransform()
        sink = as_sink(CollectSink())

        config = PipelineConfig(
            source=source,
            transforms=[transform],
            sinks={"default": sink},
        )

        # Capture events
        event_bus = EventBus()
        phase_errors: list[PhaseError] = []

        def capture_phase_error(event: PhaseError) -> None:
            phase_errors.append(event)

        event_bus.subscribe(PhaseError, capture_phase_error)

        orchestrator = Orchestrator(db, event_bus=event_bus)

        # Run should fail
        with pytest.raises(RuntimeError, match="Transform exploded"):
            orchestrator.run(config=config, graph=_build_test_graph(config))

        # Should have exactly ONE PhaseError for PROCESS phase
        assert len(phase_errors) == 1, f"Expected 1 PhaseError, got {len(phase_errors)}"
        assert phase_errors[0].phase == PipelinePhase.PROCESS
        assert "Transform exploded" in str(phase_errors[0].error)

    def test_source_failure_emits_source_phase_error(self) -> None:
        """SOURCE phase failure should emit PhaseError(SOURCE), not PROCESS."""
        from elspeth.core.landscape import LandscapeDB
        from elspeth.engine.orchestrator import Orchestrator, PipelineConfig

        db = LandscapeDB.in_memory()

        class ExplodingSource(_TestSourceBase):
            name = "exploding_source"
            output_schema = _TestSchema

            def on_start(self, ctx: Any) -> None:
                pass

            def load(self, ctx: Any) -> Iterator[SourceRow]:
                raise RuntimeError("Source load failed!")

            def close(self) -> None:
                pass

        class CollectSink(_TestSinkBase):
            name = "default"

            def __init__(self) -> None:
                self.results: list[dict[str, Any]] = []

            def on_start(self, ctx: Any) -> None:
                pass

            def write(self, row: dict[str, Any], ctx: Any) -> None:
                self.results.append(row)

            def close(self) -> None:
                pass

        # Create pipeline with failing source
        source = as_source(ExplodingSource())
        sink = as_sink(CollectSink())

        config = PipelineConfig(
            source=source,
            transforms=[],
            sinks={"default": sink},
        )

        # Capture events
        event_bus = EventBus()
        phase_errors: list[PhaseError] = []

        def capture_phase_error(event: PhaseError) -> None:
            phase_errors.append(event)

        event_bus.subscribe(PhaseError, capture_phase_error)

        orchestrator = Orchestrator(db, event_bus=event_bus)

        # Run should fail
        with pytest.raises(RuntimeError, match="Source load failed"):
            orchestrator.run(config=config, graph=_build_test_graph(config))

        # Should have exactly ONE PhaseError for SOURCE phase (not PROCESS)
        assert len(phase_errors) == 1, f"Expected 1 PhaseError, got {len(phase_errors)}"
        assert phase_errors[0].phase == PipelinePhase.SOURCE, "SOURCE failure should emit SOURCE PhaseError, not PROCESS"
        assert "Source load failed" in str(phase_errors[0].error)
