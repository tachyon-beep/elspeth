# tests/engine/test_orchestrator_lifecycle.py
"""Tests for plugin lifecycle hooks in the Orchestrator.

Tests verify that on_start(), on_complete(), and close() are called at the
correct times during pipeline execution. All tests use the production
ExecutionGraph.from_plugin_instances() path via build_production_graph().
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING, Any, ClassVar

import pytest
from pydantic import ConfigDict

from elspeth.contracts import ArtifactDescriptor, PipelineRow, PluginSchema, SourceRow
from elspeth.core.landscape import LandscapeDB
from elspeth.plugins.base import BaseTransform
from tests.conftest import (
    _TestSchema,
    _TestSinkBase,
    _TestSourceBase,
    as_sink,
    as_source,
    as_transform,
)
from tests.engine.orchestrator_test_helpers import build_production_graph

if TYPE_CHECKING:
    from elspeth.contracts.results import TransformResult


class TestLifecycleHooks:
    """Orchestrator invokes plugin lifecycle hooks."""

    def test_on_start_called_before_processing(self, landscape_db: LandscapeDB, payload_store) -> None:
        """on_start() called before any rows processed."""
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
                super().__init__({"schema": {"mode": "observed"}})

            def on_start(self, ctx: Any) -> None:
                call_order.append("on_start")

            def process(self, row: PipelineRow, ctx: Any) -> TransformResult:
                call_order.append("process")
                return TransformResult.success(row.to_dict(), success_reason={"action": "test"})

        class TrackedSource(_TestSourceBase):
            name = "tracked_source"
            output_schema = TestSchema

            def load(self, ctx: Any) -> Iterator[SourceRow]:
                yield from self.wrap_rows([{"id": 1}])

        class TrackedSink(_TestSinkBase):
            name = "tracked_sink"

            def write(self, rows: Any, ctx: Any) -> ArtifactDescriptor:
                return ArtifactDescriptor.for_file(path="memory", size_bytes=0, content_hash="abc123")

        source = TrackedSource()
        transform = TrackedTransform()
        sink = TrackedSink()

        config = PipelineConfig(
            source=as_source(source),
            transforms=[as_transform(transform)],
            sinks={"output": as_sink(sink)},
        )

        orchestrator = Orchestrator(landscape_db)
        orchestrator.run(config, graph=build_production_graph(config, default_sink="output"), payload_store=payload_store)

        # on_start should be called first
        assert call_order[0] == "on_start"
        assert "process" in call_order

    def test_on_complete_called_after_all_rows(self, landscape_db: LandscapeDB, payload_store) -> None:
        """on_complete() called after all rows processed."""
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
                super().__init__({"schema": {"mode": "observed"}})

            def on_start(self, ctx: Any) -> None:
                call_order.append("on_start")

            def process(self, row: PipelineRow, ctx: Any) -> TransformResult:
                call_order.append("process")
                return TransformResult.success(row.to_dict(), success_reason={"action": "test"})

            def on_complete(self, ctx: Any) -> None:
                call_order.append("on_complete")

        class TrackedSource(_TestSourceBase):
            name = "tracked_source"
            output_schema = TestSchema

            def load(self, ctx: Any) -> Iterator[SourceRow]:
                yield from self.wrap_rows([{"id": 1}, {"id": 2}])

        class TrackedSink(_TestSinkBase):
            name = "tracked_sink"

            def write(self, rows: Any, ctx: Any) -> ArtifactDescriptor:
                return ArtifactDescriptor.for_file(path="memory", size_bytes=0, content_hash="abc123")

        source = TrackedSource()
        transform = TrackedTransform()
        sink = TrackedSink()

        config = PipelineConfig(
            source=as_source(source),
            transforms=[as_transform(transform)],
            sinks={"output": as_sink(sink)},
        )

        orchestrator = Orchestrator(landscape_db)
        orchestrator.run(config, graph=build_production_graph(config, default_sink="output"), payload_store=payload_store)

        # on_complete should be called last (among transform lifecycle calls)
        transform_calls = [c for c in call_order if c in ["on_start", "process", "on_complete"]]
        assert transform_calls[-1] == "on_complete"
        # All processing should happen before on_complete
        assert call_order.count("process") == 2

    def test_on_complete_called_on_error(self, landscape_db: LandscapeDB, payload_store) -> None:
        """on_complete() called even when run fails."""
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
                super().__init__({"schema": {"mode": "observed"}})

            def on_start(self, ctx: Any) -> None:
                pass

            def process(self, row: PipelineRow, ctx: Any) -> TransformResult:
                raise RuntimeError("intentional failure")

            def on_complete(self, ctx: Any) -> None:
                completed.append(True)

        class TrackedSource(_TestSourceBase):
            name = "tracked_source"
            output_schema = TestSchema

            def load(self, ctx: Any) -> Iterator[SourceRow]:
                yield from self.wrap_rows([{"id": 1}])

        class TrackedSink(_TestSinkBase):
            name = "tracked_sink"

            def write(self, rows: Any, ctx: Any) -> ArtifactDescriptor:
                return ArtifactDescriptor.for_file(path="memory", size_bytes=0, content_hash="abc123")

        source = TrackedSource()
        transform = FailingTransform()
        sink = TrackedSink()

        config = PipelineConfig(
            source=as_source(source),
            transforms=[as_transform(transform)],
            sinks={"output": as_sink(sink)},
        )

        orchestrator = Orchestrator(landscape_db)

        with pytest.raises(RuntimeError):
            orchestrator.run(config, graph=build_production_graph(config, default_sink="output"), payload_store=payload_store)

        # on_complete should still be called
        assert len(completed) == 1


class TestSourceLifecycleHooks:
    """Tests for source plugin lifecycle hook calls."""

    def test_source_lifecycle_hooks_called(self, landscape_db: LandscapeDB, payload_store) -> None:
        """Source on_start, on_complete should be called around loading."""
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
                yield from self.wrap_rows([{"value": 1}])

            def on_complete(self, ctx: Any) -> None:
                call_order.append("source_on_complete")

            def close(self) -> None:
                call_order.append("source_close")

        class TrackedSink(_TestSinkBase):
            name = "tracked_sink"

            def write(self, rows: Any, ctx: Any) -> ArtifactDescriptor:
                return ArtifactDescriptor.for_file(path="memory", size_bytes=0, content_hash="abc123")

        source = TrackedSource()
        sink = TrackedSink()

        config = PipelineConfig(
            source=as_source(source),
            transforms=[],
            sinks={"output": as_sink(sink)},
        )

        orchestrator = Orchestrator(landscape_db)
        orchestrator.run(config, graph=build_production_graph(config, default_sink="output"), payload_store=payload_store)

        # on_start should be called BEFORE load
        assert "source_on_start" in call_order, "Source on_start should be called"
        assert call_order.index("source_on_start") < call_order.index("source_load"), "Source on_start should be called before load"
        # on_complete should be called AFTER load and BEFORE close
        assert "source_on_complete" in call_order, "Source on_complete should be called"
        assert call_order.index("source_on_complete") > call_order.index("source_load"), "Source on_complete should be called after load"
        assert call_order.index("source_on_complete") < call_order.index("source_close"), "Source on_complete should be called before close"


class TestSinkLifecycleHooks:
    """Tests for sink plugin lifecycle hook calls."""

    def test_sink_lifecycle_hooks_called(self, landscape_db: LandscapeDB, payload_store) -> None:
        """Sink on_start and on_complete should be called."""
        from elspeth.engine.orchestrator import Orchestrator, PipelineConfig

        call_order: list[str] = []

        class TrackedSource(_TestSourceBase):
            name = "tracked_source"
            output_schema = _TestSchema

            def load(self, ctx: Any) -> Iterator[SourceRow]:
                yield from self.wrap_rows([{"value": 1}])

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

        source = TrackedSource()
        sink = TrackedSink()

        config = PipelineConfig(
            source=as_source(source),
            transforms=[],
            sinks={"output": as_sink(sink)},
        )

        orchestrator = Orchestrator(landscape_db)
        orchestrator.run(config, graph=build_production_graph(config, default_sink="output"), payload_store=payload_store)

        # on_start should be called before write
        assert "sink_on_start" in call_order, "Sink on_start should be called"
        assert call_order.index("sink_on_start") < call_order.index("sink_write"), "Sink on_start should be called before write"
        # on_complete should be called after write, before close
        assert "sink_on_complete" in call_order, "Sink on_complete should be called"
        assert call_order.index("sink_on_complete") > call_order.index("sink_write"), "Sink on_complete should be called after write"

    def test_sink_on_complete_called_even_on_error(self, landscape_db: LandscapeDB, payload_store) -> None:
        """Sink on_complete should be called even when run fails."""
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
                super().__init__({"schema": {"mode": "observed"}})

            def on_start(self, ctx: Any) -> None:
                pass

            def on_complete(self, ctx: Any) -> None:
                pass

            def process(self, row: PipelineRow, ctx: Any) -> TransformResult:
                raise RuntimeError("intentional failure")

        class TrackedSource(_TestSourceBase):
            name = "tracked_source"
            output_schema = TestSchema

            def load(self, ctx: Any) -> Iterator[SourceRow]:
                yield from self.wrap_rows([{"value": 1}])

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

        source = TrackedSource()
        transform = FailingTransform()
        sink = TrackedSink()

        config = PipelineConfig(
            source=as_source(source),
            transforms=[as_transform(transform)],
            sinks={"output": as_sink(sink)},
        )

        orchestrator = Orchestrator(landscape_db)

        with pytest.raises(RuntimeError):
            orchestrator.run(config, graph=build_production_graph(config, default_sink="output"), payload_store=payload_store)

        # on_complete should still be called
        assert "sink_on_complete" in completed
