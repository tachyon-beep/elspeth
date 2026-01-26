# tests/engine/test_orchestrator_lifecycle.py
"""Tests for plugin lifecycle hooks in the Orchestrator.

Extracted from test_orchestrator.py:
- TestLifecycleHooks
- TestSourceLifecycleHooks
- TestSinkLifecycleHooks
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING, Any, ClassVar

import pytest
from pydantic import ConfigDict

from elspeth.contracts import Determinism, RoutingMode, SourceRow
from elspeth.plugins.base import BaseTransform
from tests.conftest import (
    _TestSchema,
    _TestSinkBase,
    _TestSourceBase,
    as_sink,
    as_source,
)

if TYPE_CHECKING:
    from elspeth.contracts.results import TransformResult


class TestLifecycleHooks:
    """Orchestrator invokes plugin lifecycle hooks."""

    def test_on_start_called_before_processing(self) -> None:
        """on_start() called before any rows processed."""
        from unittest.mock import MagicMock

        from elspeth.core.dag import ExecutionGraph
        from elspeth.core.landscape import LandscapeDB
        from elspeth.engine.artifacts import ArtifactDescriptor
        from elspeth.engine.orchestrator import Orchestrator, PipelineConfig
        from elspeth.plugins.results import TransformResult

        call_order: list[str] = []

        from elspeth.contracts import PluginSchema, SourceRow

        class TestSchema(PluginSchema):
            model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow")

        class TrackedTransform(BaseTransform):
            name = "tracked"
            input_schema = TestSchema
            output_schema = TestSchema
            plugin_version = "1.0.0"

            def __init__(self) -> None:
                super().__init__({})

            def on_start(self, ctx: Any) -> None:
                call_order.append("on_start")

            def process(self, row: Any, ctx: Any) -> TransformResult:
                call_order.append("process")
                return TransformResult.success(row)

        db = LandscapeDB.in_memory()

        mock_source = MagicMock()
        mock_source.name = "csv"
        mock_source.determinism = Determinism.IO_READ
        mock_source.plugin_version = "1.0.0"
        schema_mock = MagicMock()

        schema_mock.model_json_schema.return_value = {"type": "object"}

        mock_source.output_schema = schema_mock
        mock_source.load.return_value = iter([SourceRow.valid({"id": 1})])

        transform = TrackedTransform()
        mock_sink = MagicMock()
        mock_sink.name = "csv"
        mock_sink.determinism = Determinism.IO_WRITE
        mock_sink.plugin_version = "1.0.0"
        schema_mock = MagicMock()

        schema_mock.model_json_schema.return_value = {"type": "object"}

        mock_sink.input_schema = schema_mock
        mock_sink.write.return_value = ArtifactDescriptor.for_file(path="memory", size_bytes=0, content_hash="abc123")

        config = PipelineConfig(
            source=mock_source,
            transforms=[transform],
            sinks={"output": mock_sink},
        )

        # Minimal graph
        graph = ExecutionGraph()
        graph.add_node("source", node_type="source", plugin_name="csv")
        graph.add_node("transform", node_type="transform", plugin_name="tracked")
        graph.add_node("sink", node_type="sink", plugin_name="csv")
        graph.add_edge("source", "transform", label="continue", mode=RoutingMode.MOVE)
        graph.add_edge("transform", "sink", label="continue", mode=RoutingMode.MOVE)
        graph._transform_id_map = {0: "transform"}
        graph._sink_id_map = {"output": "sink"}
        graph._output_sink = "output"

        orchestrator = Orchestrator(db)
        orchestrator.run(config, graph=graph)

        # on_start should be called first
        assert call_order[0] == "on_start"
        assert "process" in call_order

    def test_on_complete_called_after_all_rows(self) -> None:
        """on_complete() called after all rows processed."""
        from unittest.mock import MagicMock

        from elspeth.contracts import PluginSchema, SourceRow
        from elspeth.core.dag import ExecutionGraph
        from elspeth.core.landscape import LandscapeDB
        from elspeth.engine.artifacts import ArtifactDescriptor
        from elspeth.engine.orchestrator import Orchestrator, PipelineConfig
        from elspeth.plugins.results import TransformResult

        call_order: list[str] = []

        class TestSchema(PluginSchema):
            model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow")

        class TrackedTransform(BaseTransform):
            name = "tracked"
            input_schema = TestSchema
            output_schema = TestSchema
            plugin_version = "1.0.0"

            def __init__(self) -> None:
                super().__init__({})

            def on_start(self, ctx: Any) -> None:
                call_order.append("on_start")

            def process(self, row: Any, ctx: Any) -> TransformResult:
                call_order.append("process")
                return TransformResult.success(row)

            def on_complete(self, ctx: Any) -> None:
                call_order.append("on_complete")

        db = LandscapeDB.in_memory()

        mock_source = MagicMock()
        mock_source.name = "csv"
        mock_source.determinism = Determinism.IO_READ
        mock_source.plugin_version = "1.0.0"
        schema_mock = MagicMock()

        schema_mock.model_json_schema.return_value = {"type": "object"}

        mock_source.output_schema = schema_mock
        mock_source.load.return_value = iter([SourceRow.valid({"id": 1}), SourceRow.valid({"id": 2})])

        transform = TrackedTransform()
        mock_sink = MagicMock()
        mock_sink.name = "csv"
        mock_sink.determinism = Determinism.IO_WRITE
        mock_sink.plugin_version = "1.0.0"
        schema_mock = MagicMock()

        schema_mock.model_json_schema.return_value = {"type": "object"}

        mock_sink.input_schema = schema_mock
        mock_sink.write.return_value = ArtifactDescriptor.for_file(path="memory", size_bytes=0, content_hash="abc123")

        config = PipelineConfig(
            source=mock_source,
            transforms=[transform],
            sinks={"output": mock_sink},
        )

        graph = ExecutionGraph()
        graph.add_node("source", node_type="source", plugin_name="csv")
        graph.add_node("transform", node_type="transform", plugin_name="tracked")
        graph.add_node("sink", node_type="sink", plugin_name="csv")
        graph.add_edge("source", "transform", label="continue", mode=RoutingMode.MOVE)
        graph.add_edge("transform", "sink", label="continue", mode=RoutingMode.MOVE)
        graph._transform_id_map = {0: "transform"}
        graph._sink_id_map = {"output": "sink"}
        graph._output_sink = "output"

        orchestrator = Orchestrator(db)
        orchestrator.run(config, graph=graph)

        # on_complete should be called last (among transform lifecycle calls)
        transform_calls = [c for c in call_order if c in ["on_start", "process", "on_complete"]]
        assert transform_calls[-1] == "on_complete"
        # All processing should happen before on_complete
        assert call_order.count("process") == 2

    def test_on_complete_called_on_error(self) -> None:
        """on_complete() called even when run fails."""
        from unittest.mock import MagicMock

        from elspeth.contracts import PluginSchema, SourceRow
        from elspeth.core.dag import ExecutionGraph
        from elspeth.core.landscape import LandscapeDB
        from elspeth.engine.orchestrator import Orchestrator, PipelineConfig

        completed: list[bool] = []

        class TestSchema(PluginSchema):
            model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow")

        class FailingTransform(BaseTransform):
            name = "failing"
            input_schema = TestSchema
            output_schema = TestSchema
            plugin_version = "1.0.0"

            def __init__(self) -> None:
                super().__init__({})

            def on_start(self, ctx: Any) -> None:
                pass

            def process(self, row: Any, ctx: Any) -> TransformResult:
                raise RuntimeError("intentional failure")

            def on_complete(self, ctx: Any) -> None:
                completed.append(True)

        db = LandscapeDB.in_memory()

        mock_source = MagicMock()
        mock_source.name = "csv"
        mock_source.determinism = Determinism.IO_READ
        mock_source.plugin_version = "1.0.0"
        schema_mock = MagicMock()

        schema_mock.model_json_schema.return_value = {"type": "object"}

        mock_source.output_schema = schema_mock
        mock_source.load.return_value = iter([SourceRow.valid({"id": 1})])

        transform = FailingTransform()
        mock_sink = MagicMock()
        mock_sink.name = "csv"
        mock_sink.determinism = Determinism.IO_WRITE
        mock_sink.plugin_version = "1.0.0"
        schema_mock = MagicMock()

        schema_mock.model_json_schema.return_value = {"type": "object"}

        mock_sink.input_schema = schema_mock

        config = PipelineConfig(
            source=mock_source,
            transforms=[transform],
            sinks={"output": mock_sink},
        )

        graph = ExecutionGraph()
        graph.add_node("source", node_type="source", plugin_name="failing")
        graph.add_node("transform", node_type="transform", plugin_name="failing")
        graph.add_node("sink", node_type="sink", plugin_name="csv")
        graph.add_edge("source", "transform", label="continue", mode=RoutingMode.MOVE)
        graph.add_edge("transform", "sink", label="continue", mode=RoutingMode.MOVE)
        graph._transform_id_map = {0: "transform"}
        graph._sink_id_map = {"output": "sink"}
        graph._output_sink = "output"

        orchestrator = Orchestrator(db)

        with pytest.raises(RuntimeError):
            orchestrator.run(config, graph=graph)

        # on_complete should still be called
        assert len(completed) == 1


class TestSourceLifecycleHooks:
    """Tests for source plugin lifecycle hook calls."""

    def test_source_lifecycle_hooks_called(self) -> None:
        """Source on_start, on_complete should be called around loading."""
        from unittest.mock import MagicMock

        from elspeth.core.dag import ExecutionGraph
        from elspeth.core.landscape import LandscapeDB
        from elspeth.engine.artifacts import ArtifactDescriptor
        from elspeth.engine.orchestrator import Orchestrator, PipelineConfig

        call_order: list[str] = []

        class TrackedSource(_TestSourceBase):
            """Source that tracks lifecycle calls."""

            name = "tracked_source"
            output_schema = _TestSchema

            def on_start(self, ctx: Any) -> None:
                call_order.append("source_on_start")

            def load(self, ctx: Any) -> Iterator[SourceRow]:
                call_order.append("source_load")
                yield SourceRow.valid({"value": 1})

            def on_complete(self, ctx: Any) -> None:
                call_order.append("source_on_complete")

            def close(self) -> None:
                call_order.append("source_close")

        db = LandscapeDB.in_memory()

        source = TrackedSource()
        mock_sink = MagicMock()
        mock_sink.name = "csv"
        mock_sink.determinism = Determinism.IO_WRITE
        mock_sink.plugin_version = "1.0.0"
        schema_mock = MagicMock()

        schema_mock.model_json_schema.return_value = {"type": "object"}

        mock_sink.input_schema = schema_mock
        mock_sink.write.return_value = ArtifactDescriptor.for_file(path="memory", size_bytes=0, content_hash="abc123")

        config = PipelineConfig(
            source=as_source(source),
            transforms=[],
            sinks={"output": as_sink(mock_sink)},
        )

        # Minimal graph
        graph = ExecutionGraph()
        graph.add_node("source", node_type="source", plugin_name="tracked_source")
        graph.add_node("sink", node_type="sink", plugin_name="csv")
        graph.add_edge("source", "sink", label="continue", mode=RoutingMode.MOVE)
        graph._transform_id_map = {}
        graph._sink_id_map = {"output": "sink"}
        graph._output_sink = "output"

        orchestrator = Orchestrator(db)
        orchestrator.run(config, graph=graph)

        # on_start should be called BEFORE load
        assert "source_on_start" in call_order, "Source on_start should be called"
        assert call_order.index("source_on_start") < call_order.index("source_load"), "Source on_start should be called before load"
        # on_complete should be called AFTER load and BEFORE close
        assert "source_on_complete" in call_order, "Source on_complete should be called"
        assert call_order.index("source_on_complete") > call_order.index("source_load"), "Source on_complete should be called after load"
        assert call_order.index("source_on_complete") < call_order.index("source_close"), "Source on_complete should be called before close"


class TestSinkLifecycleHooks:
    """Tests for sink plugin lifecycle hook calls."""

    def test_sink_lifecycle_hooks_called(self) -> None:
        """Sink on_start and on_complete should be called."""
        from unittest.mock import MagicMock

        from elspeth.core.dag import ExecutionGraph
        from elspeth.core.landscape import LandscapeDB
        from elspeth.engine.artifacts import ArtifactDescriptor
        from elspeth.engine.orchestrator import Orchestrator, PipelineConfig

        call_order: list[str] = []

        class TrackedSink(_TestSinkBase):
            """Sink that tracks lifecycle calls."""

            name = "tracked_sink"

            def on_start(self, ctx: Any) -> None:
                call_order.append("sink_on_start")

            def on_complete(self, ctx: Any) -> None:
                call_order.append("sink_on_complete")

            def write(self, rows: Any, ctx: Any) -> ArtifactDescriptor:
                call_order.append("sink_write")
                return ArtifactDescriptor.for_file(path="memory", size_bytes=0, content_hash="abc123")

            def close(self) -> None:
                call_order.append("sink_close")

        db = LandscapeDB.in_memory()

        mock_source = MagicMock()
        mock_source.name = "csv"
        mock_source.determinism = Determinism.IO_READ
        mock_source.plugin_version = "1.0.0"
        schema_mock = MagicMock()

        schema_mock.model_json_schema.return_value = {"type": "object"}

        mock_source.output_schema = schema_mock
        mock_source.load.return_value = iter([SourceRow.valid({"value": 1})])

        sink = TrackedSink()

        config = PipelineConfig(
            source=mock_source,
            transforms=[],
            sinks={"output": sink},
        )

        # Minimal graph
        graph = ExecutionGraph()
        graph.add_node("source", node_type="source", plugin_name="csv")
        graph.add_node("sink", node_type="sink", plugin_name="tracked_sink")
        graph.add_edge("source", "sink", label="continue", mode=RoutingMode.MOVE)
        graph._transform_id_map = {}
        graph._sink_id_map = {"output": "sink"}
        graph._output_sink = "output"

        orchestrator = Orchestrator(db)
        orchestrator.run(config, graph=graph)

        # on_start should be called before write
        assert "sink_on_start" in call_order, "Sink on_start should be called"
        assert call_order.index("sink_on_start") < call_order.index("sink_write"), "Sink on_start should be called before write"
        # on_complete should be called after write, before close
        assert "sink_on_complete" in call_order, "Sink on_complete should be called"
        assert call_order.index("sink_on_complete") > call_order.index("sink_write"), "Sink on_complete should be called after write"

    def test_sink_on_complete_called_even_on_error(self) -> None:
        """Sink on_complete should be called even when run fails."""
        from unittest.mock import MagicMock

        from elspeth.contracts import PluginSchema, SourceRow
        from elspeth.core.dag import ExecutionGraph
        from elspeth.core.landscape import LandscapeDB
        from elspeth.engine.artifacts import ArtifactDescriptor
        from elspeth.engine.orchestrator import Orchestrator, PipelineConfig

        completed: list[str] = []

        class TestSchema(PluginSchema):
            model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow")

        class FailingTransform(BaseTransform):
            name = "failing"
            input_schema = TestSchema
            output_schema = TestSchema
            plugin_version = "1.0.0"

            def __init__(self) -> None:
                super().__init__({})

            def on_start(self, ctx: Any) -> None:
                pass

            def on_complete(self, ctx: Any) -> None:
                pass

            def process(self, row: Any, ctx: Any) -> TransformResult:
                raise RuntimeError("intentional failure")

        class TrackedSink(_TestSinkBase):
            name = "tracked_sink"

            def on_start(self, ctx: Any) -> None:
                pass

            def on_complete(self, ctx: Any) -> None:
                completed.append("sink_on_complete")

            def write(self, rows: Any, ctx: Any) -> ArtifactDescriptor:
                return ArtifactDescriptor.for_file(path="memory", size_bytes=0, content_hash="abc123")

            def close(self) -> None:
                pass

        db = LandscapeDB.in_memory()

        mock_source = MagicMock()
        mock_source.name = "csv"
        mock_source.determinism = Determinism.IO_READ
        mock_source.plugin_version = "1.0.0"
        schema_mock = MagicMock()

        schema_mock.model_json_schema.return_value = {"type": "object"}

        mock_source.output_schema = schema_mock
        mock_source.load.return_value = iter([SourceRow.valid({"value": 1})])

        transform = FailingTransform()
        sink = TrackedSink()

        config = PipelineConfig(
            source=mock_source,
            transforms=[transform],
            sinks={"output": sink},
        )

        graph = ExecutionGraph()
        graph.add_node("source", node_type="source", plugin_name="csv")
        graph.add_node("transform", node_type="transform", plugin_name="failing")
        graph.add_node("sink", node_type="sink", plugin_name="tracked_sink")
        graph.add_edge("source", "transform", label="continue", mode=RoutingMode.MOVE)
        graph.add_edge("transform", "sink", label="continue", mode=RoutingMode.MOVE)
        graph._transform_id_map = {0: "transform"}
        graph._sink_id_map = {"output": "sink"}
        graph._output_sink = "output"

        orchestrator = Orchestrator(db)

        with pytest.raises(RuntimeError):
            orchestrator.run(config, graph=graph)

        # on_complete should still be called
        assert "sink_on_complete" in completed
