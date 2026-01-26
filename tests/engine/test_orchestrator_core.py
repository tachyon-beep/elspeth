# tests/engine/test_orchestrator_core.py
"""Core orchestrator tests.

Extracted from test_orchestrator.py: TestOrchestrator, TestOrchestratorMultipleTransforms,
TestOrchestratorEmptyPipeline, TestOrchestratorAcceptsGraph.

All test plugins inherit from base classes (BaseTransform, BaseGate)
because the processor uses isinstance() for type-safe plugin detection.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from elspeth.cli_helpers import instantiate_plugins_from_config
from elspeth.contracts import Determinism, RoutingMode, SourceRow
from elspeth.plugins.base import BaseTransform
from tests.conftest import (
    _TestSinkBase,
    _TestSourceBase,
    as_sink,
    as_source,
)
from tests.engine.orchestrator_test_helpers import build_test_graph

if TYPE_CHECKING:
    from elspeth.contracts.results import TransformResult


class TestOrchestrator:
    """Full run orchestration."""

    def test_run_simple_pipeline(self) -> None:
        from elspeth.contracts import PluginSchema
        from elspeth.core.landscape import LandscapeDB
        from elspeth.engine.artifacts import ArtifactDescriptor
        from elspeth.engine.orchestrator import Orchestrator, PipelineConfig
        from elspeth.plugins.results import TransformResult

        db = LandscapeDB.in_memory()

        class InputSchema(PluginSchema):
            value: int

        class OutputSchema(PluginSchema):
            value: int
            doubled: int

        class ListSource(_TestSourceBase):
            name = "list_source"
            output_schema = InputSchema

            def __init__(self, data: list[dict[str, Any]]) -> None:
                self._data = data

            def on_start(self, ctx: Any) -> None:
                pass

            def load(self, ctx: Any) -> Any:
                for _row in self._data:
                    yield SourceRow.valid(_row)

            def close(self) -> None:
                pass

        class DoubleTransform(BaseTransform):
            name = "double"
            input_schema = InputSchema
            output_schema = OutputSchema

            def __init__(self) -> None:
                super().__init__({})

            def process(self, row: Any, ctx: Any) -> TransformResult:
                return TransformResult.success(
                    {
                        "value": row["value"],
                        "doubled": row["value"] * 2,
                    }
                )

        class CollectSink(_TestSinkBase):
            name = "collect"

            def __init__(self) -> None:
                self.results: list[dict[str, Any]] = []

            def on_start(self, ctx: Any) -> None:
                pass

            def on_complete(self, ctx: Any) -> None:
                pass

            def write(self, rows: Any, ctx: Any) -> ArtifactDescriptor:
                self.results.extend(rows)
                return ArtifactDescriptor.for_file(path="memory", size_bytes=0, content_hash="")

            def close(self) -> None:
                pass

        source = ListSource([{"value": 1}, {"value": 2}, {"value": 3}])
        transform = DoubleTransform()
        sink = CollectSink()

        config = PipelineConfig(
            source=as_source(source),
            transforms=[transform],
            sinks={"default": as_sink(sink)},
        )

        orchestrator = Orchestrator(db)
        run_result = orchestrator.run(config, graph=build_test_graph(config))

        assert run_result.status == "completed"
        assert run_result.rows_processed == 3
        assert len(sink.results) == 3
        assert sink.results[0] == {"value": 1, "doubled": 2}

    def test_run_with_gate_routing(self) -> None:
        from elspeth.contracts import PluginSchema
        from elspeth.core.config import GateSettings
        from elspeth.core.landscape import LandscapeDB
        from elspeth.engine.artifacts import ArtifactDescriptor
        from elspeth.engine.orchestrator import Orchestrator, PipelineConfig

        db = LandscapeDB.in_memory()

        class RowSchema(PluginSchema):
            value: int

        class ListSource(_TestSourceBase):
            name = "list_source"
            output_schema = RowSchema

            def __init__(self, data: list[dict[str, Any]]) -> None:
                self._data = data

            def on_start(self, ctx: Any) -> None:
                pass

            def load(self, ctx: Any) -> Any:
                for _row in self._data:
                    yield SourceRow.valid(_row)

            def close(self) -> None:
                pass

        class CollectSink(_TestSinkBase):
            name = "collect"

            def __init__(self) -> None:
                self.results: list[dict[str, Any]] = []

            def on_start(self, ctx: Any) -> None:
                pass

            def on_complete(self, ctx: Any) -> None:
                pass

            def write(self, rows: Any, ctx: Any) -> ArtifactDescriptor:
                self.results.extend(rows)
                return ArtifactDescriptor.for_file(path="memory", size_bytes=0, content_hash="")

            def close(self) -> None:
                pass

        # Config-driven gate: routes values > 50 to "high" sink, else continues
        threshold_gate = GateSettings(
            name="threshold",
            condition="row['value'] > 50",
            routes={"true": "high", "false": "continue"},
        )

        source = ListSource([{"value": 10}, {"value": 100}, {"value": 30}])
        default_sink = CollectSink()
        high_sink = CollectSink()

        config = PipelineConfig(
            source=as_source(source),
            transforms=[],
            sinks={"default": as_sink(default_sink), "high": as_sink(high_sink)},
            gates=[threshold_gate],
        )

        orchestrator = Orchestrator(db)
        run_result = orchestrator.run(config, graph=build_test_graph(config))

        assert run_result.status == "completed"
        # value=10 and value=30 go to default, value=100 goes to high
        assert len(default_sink.results) == 2
        assert len(high_sink.results) == 1


class TestOrchestratorMultipleTransforms:
    """Test pipelines with multiple transforms."""

    def test_run_multiple_transforms_in_sequence(self) -> None:
        """Test that multiple transforms execute in order."""
        from elspeth.contracts import PluginSchema
        from elspeth.core.landscape import LandscapeDB
        from elspeth.engine.artifacts import ArtifactDescriptor
        from elspeth.engine.orchestrator import Orchestrator, PipelineConfig
        from elspeth.plugins.results import TransformResult

        db = LandscapeDB.in_memory()

        class NumberSchema(PluginSchema):
            value: int

        class ListSource(_TestSourceBase):
            name = "numbers"
            output_schema = NumberSchema

            def __init__(self, data: list[dict[str, Any]]) -> None:
                self._data = data

            def on_start(self, ctx: Any) -> None:
                pass

            def load(self, ctx: Any) -> Any:
                for _row in self._data:
                    yield SourceRow.valid(_row)

            def close(self) -> None:
                pass

        class AddOneTransform(BaseTransform):
            name = "add_one"
            input_schema = NumberSchema
            output_schema = NumberSchema

            def __init__(self) -> None:
                super().__init__({})

            def process(self, row: Any, ctx: Any) -> TransformResult:
                return TransformResult.success({"value": row["value"] + 1})

        class MultiplyTwoTransform(BaseTransform):
            name = "multiply_two"
            input_schema = NumberSchema
            output_schema = NumberSchema

            def __init__(self) -> None:
                super().__init__({})

            def process(self, row: Any, ctx: Any) -> TransformResult:
                return TransformResult.success({"value": row["value"] * 2})

        class CollectSink(_TestSinkBase):
            name = "collect"

            def __init__(self) -> None:
                self.results: list[dict[str, Any]] = []

            def on_start(self, ctx: Any) -> None:
                pass

            def on_complete(self, ctx: Any) -> None:
                pass

            def write(self, rows: Any, ctx: Any) -> ArtifactDescriptor:
                self.results.extend(rows)
                return ArtifactDescriptor.for_file(path="memory", size_bytes=0, content_hash="")

            def close(self) -> None:
                pass

        source = ListSource([{"value": 5}])
        transform1 = AddOneTransform()
        transform2 = MultiplyTwoTransform()
        sink = CollectSink()

        config = PipelineConfig(
            source=as_source(source),
            transforms=[transform1, transform2],
            sinks={"default": as_sink(sink)},
        )

        orchestrator = Orchestrator(db)
        run_result = orchestrator.run(config, graph=build_test_graph(config))

        assert run_result.status == "completed"
        assert len(sink.results) == 1
        # (5 + 1) * 2 = 12
        assert sink.results[0]["value"] == 12


class TestOrchestratorEmptyPipeline:
    """Test edge cases."""

    def test_run_no_transforms(self) -> None:
        """Test pipeline with source directly to sink."""
        from elspeth.contracts import PluginSchema
        from elspeth.core.landscape import LandscapeDB
        from elspeth.engine.artifacts import ArtifactDescriptor
        from elspeth.engine.orchestrator import Orchestrator, PipelineConfig

        db = LandscapeDB.in_memory()

        class ValueSchema(PluginSchema):
            value: int

        class ListSource(_TestSourceBase):
            name = "direct"
            output_schema = ValueSchema

            def __init__(self, data: list[dict[str, Any]]) -> None:
                self._data = data

            def on_start(self, ctx: Any) -> None:
                pass

            def load(self, ctx: Any) -> Any:
                for _row in self._data:
                    yield SourceRow.valid(_row)

            def close(self) -> None:
                pass

        class CollectSink(_TestSinkBase):
            name = "collect"

            def __init__(self) -> None:
                self.results: list[dict[str, Any]] = []

            def on_start(self, ctx: Any) -> None:
                pass

            def on_complete(self, ctx: Any) -> None:
                pass

            def write(self, rows: Any, ctx: Any) -> ArtifactDescriptor:
                self.results.extend(rows)
                return ArtifactDescriptor.for_file(path="memory", size_bytes=0, content_hash="")

            def close(self) -> None:
                pass

        source = ListSource([{"value": 99}])
        sink = CollectSink()

        config = PipelineConfig(
            source=as_source(source),
            transforms=[],
            sinks={"default": as_sink(sink)},
        )

        orchestrator = Orchestrator(db)
        run_result = orchestrator.run(config, graph=build_test_graph(config))

        assert run_result.status == "completed"
        assert run_result.rows_processed == 1
        assert len(sink.results) == 1
        assert sink.results[0] == {"value": 99}

    def test_run_empty_source(self) -> None:
        """Test pipeline with no rows from source."""
        from elspeth.contracts import PluginSchema
        from elspeth.core.landscape import LandscapeDB
        from elspeth.engine.artifacts import ArtifactDescriptor
        from elspeth.engine.orchestrator import Orchestrator, PipelineConfig
        from elspeth.plugins.results import TransformResult

        db = LandscapeDB.in_memory()

        class ValueSchema(PluginSchema):
            value: int

        class EmptySource(_TestSourceBase):
            name = "empty"
            output_schema = ValueSchema

            def on_start(self, ctx: Any) -> None:
                pass

            def load(self, ctx: Any) -> Any:
                return iter([])

            def close(self) -> None:
                pass

        class IdentityTransform(BaseTransform):
            name = "identity"
            input_schema = ValueSchema
            output_schema = ValueSchema

            def __init__(self) -> None:
                super().__init__({})

            def process(self, row: Any, ctx: Any) -> TransformResult:
                return TransformResult.success(row)

        class CollectSink(_TestSinkBase):
            name = "collect"

            def __init__(self) -> None:
                self.results: list[dict[str, Any]] = []

            def on_start(self, ctx: Any) -> None:
                pass

            def on_complete(self, ctx: Any) -> None:
                pass

            def write(self, rows: Any, ctx: Any) -> ArtifactDescriptor:
                self.results.extend(rows)
                return ArtifactDescriptor.for_file(path="memory", size_bytes=0, content_hash="")

            def close(self) -> None:
                pass

        source = EmptySource()
        transform = IdentityTransform()
        sink = CollectSink()

        config = PipelineConfig(
            source=as_source(source),
            transforms=[transform],
            sinks={"default": as_sink(sink)},
        )

        orchestrator = Orchestrator(db)
        run_result = orchestrator.run(config, graph=build_test_graph(config))

        assert run_result.status == "completed"
        assert run_result.rows_processed == 0
        assert len(sink.results) == 0


class TestOrchestratorAcceptsGraph:
    """Orchestrator accepts ExecutionGraph parameter."""

    def test_orchestrator_uses_graph_node_ids(self, plugin_manager) -> None:
        """Orchestrator uses node IDs from graph, not generated IDs."""
        from unittest.mock import MagicMock

        from elspeth.core.config import (
            DatasourceSettings,
            ElspethSettings,
            SinkSettings,
        )
        from elspeth.core.dag import ExecutionGraph
        from elspeth.core.landscape import LandscapeDB
        from elspeth.engine.orchestrator import Orchestrator, PipelineConfig

        db = LandscapeDB.in_memory()

        # Build config and graph from settings
        settings = ElspethSettings(
            datasource=DatasourceSettings(
                plugin="csv",
                options={
                    "path": "test.csv",
                    "on_validation_failure": "discard",
                    "schema": {"fields": "dynamic"},
                },
            ),
            sinks={"output": SinkSettings(plugin="csv", options={"path": "output.csv", "schema": {"fields": "dynamic"}})},
            output_sink="output",
        )
        plugins = instantiate_plugins_from_config(settings)

        graph = ExecutionGraph.from_plugin_instances(
            source=plugins["source"],
            transforms=plugins["transforms"],
            sinks=plugins["sinks"],
            aggregations=plugins["aggregations"],
            gates=list(settings.gates),
            output_sink=settings.output_sink,
            coalesce_settings=settings.coalesce,
        )

        # P2 Fix: Use explicit node_id initialization instead of hasattr on MagicMock
        # MagicMock auto-creates attributes on access, making hasattr meaningless.
        # Initialize node_id to a sentinel value to verify it was actually set.
        mock_source = MagicMock()
        mock_source.name = "csv"
        mock_source.determinism = Determinism.IO_READ
        mock_source.plugin_version = "1.0.0"
        mock_source.node_id = None  # Explicit initialization - orchestrator should set this
        schema_mock = MagicMock()

        schema_mock.model_json_schema.return_value = {"type": "object"}

        mock_source.output_schema = schema_mock
        mock_source.load.return_value = iter([])  # Empty source

        mock_sink = MagicMock()
        mock_sink.name = "csv"
        mock_sink.determinism = Determinism.IO_WRITE
        mock_sink.plugin_version = "1.0.0"
        mock_sink.node_id = None  # Explicit initialization - orchestrator should set this
        schema_mock = MagicMock()

        schema_mock.model_json_schema.return_value = {"type": "object"}

        mock_sink.input_schema = schema_mock

        pipeline_config = PipelineConfig(
            source=mock_source,
            transforms=[],
            sinks={"output": mock_sink},
        )

        orchestrator = Orchestrator(db)
        orchestrator.run(pipeline_config, graph=graph)

        # Source should have node_id set from graph (was None, now should be set)
        expected_source_id = graph.get_source()
        assert mock_source.node_id == expected_source_id, (
            f"Source node_id not set: expected {expected_source_id}, got {mock_source.node_id}"
        )

        # Sink should have node_id set from graph's sink_id_map
        sink_id_map = graph.get_sink_id_map()
        expected_sink_id = sink_id_map["output"]
        assert mock_sink.node_id == expected_sink_id, f"Sink node_id not set: expected {expected_sink_id}, got {mock_sink.node_id}"

    def test_orchestrator_run_accepts_graph(self) -> None:
        """Orchestrator.run() accepts graph parameter."""
        import inspect

        from elspeth.core.dag import ExecutionGraph
        from elspeth.core.landscape import LandscapeDB
        from elspeth.engine.orchestrator import Orchestrator

        db = LandscapeDB.in_memory()

        # Build a simple graph
        graph = ExecutionGraph()
        graph.add_node("source_1", node_type="source", plugin_name="csv")
        graph.add_node("sink_1", node_type="sink", plugin_name="csv")
        graph.add_edge("source_1", "sink_1", label="continue", mode=RoutingMode.MOVE)

        orchestrator = Orchestrator(db)

        # Should accept graph parameter (signature check)
        sig = inspect.signature(orchestrator.run)
        assert "graph" in sig.parameters

    def test_orchestrator_run_requires_graph(self) -> None:
        """Orchestrator.run() raises ValueError if graph is None."""
        from elspeth.contracts import PluginSchema
        from elspeth.core.landscape import LandscapeDB
        from elspeth.engine.artifacts import ArtifactDescriptor
        from elspeth.engine.orchestrator import Orchestrator, PipelineConfig

        db = LandscapeDB.in_memory()

        class ValueSchema(PluginSchema):
            value: int

        class DummySource(_TestSourceBase):
            name = "dummy"
            output_schema = ValueSchema

            def load(self, ctx: Any) -> Any:
                yield from []

            def close(self) -> None:
                pass

        class DummySink(_TestSinkBase):
            name = "dummy"

            def __init__(self) -> None:
                self.results: list[dict[str, Any]] = []

            def write(self, rows: Any, ctx: Any) -> ArtifactDescriptor:
                self.results.extend(rows)
                return ArtifactDescriptor.for_file(path="memory", size_bytes=0, content_hash="")

            def close(self) -> None:
                pass

        config = PipelineConfig(
            source=as_source(DummySource()),
            transforms=[],
            sinks={"default": as_sink(DummySink())},
        )

        orchestrator = Orchestrator(db)

        # graph=None should raise ValueError
        with pytest.raises(ValueError, match="ExecutionGraph is required"):
            orchestrator.run(config, graph=None)
