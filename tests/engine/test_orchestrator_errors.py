# tests/engine/test_orchestrator_errors.py
"""Tests for Orchestrator error handling and quarantine functionality.

All test plugins inherit from base classes (BaseTransform, BaseGate)
because the processor uses isinstance() for type-safe plugin detection.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from elspeth.contracts import SourceRow
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


class TestOrchestratorErrorHandling:
    """Test error handling in orchestration."""

    def test_run_marks_failed_on_transform_exception(self) -> None:
        """If a transform raises, run status should be failed in Landscape."""
        from elspeth.contracts import PluginSchema
        from elspeth.core.landscape import LandscapeDB, LandscapeRecorder
        from elspeth.engine.artifacts import ArtifactDescriptor
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

            def load(self, ctx: Any) -> Any:
                for _row in self._data:
                    yield SourceRow.valid(_row)

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
            name = "test_sink"

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

        source = ListSource([{"value": 42}])
        transform = ExplodingTransform()
        sink = CollectSink()

        config = PipelineConfig(
            source=as_source(source),
            transforms=[transform],
            sinks={"default": as_sink(sink)},
        )

        orchestrator = Orchestrator(db)

        with pytest.raises(RuntimeError, match="Transform exploded!"):
            orchestrator.run(config, graph=build_test_graph(config))

        # Verify run was marked as failed in Landscape audit trail
        # Query for all runs and find the one that was created
        from elspeth.contracts import RunStatus

        recorder = LandscapeRecorder(db)
        runs = recorder.list_runs()
        assert len(runs) == 1, "Expected exactly one run in Landscape"

        failed_run = runs[0]
        assert failed_run.status == RunStatus.FAILED, f"Landscape audit trail must record status=FAILED, got status={failed_run.status!r}"


class TestOrchestratorSourceQuarantineValidation:
    """Test that invalid source quarantine destinations fail at startup.

    Per P2-2026-01-19-source-quarantine-silent-drop:
    Source on_validation_failure destinations should be validated at startup,
    just like gate routes and transform error sinks.
    """

    def test_invalid_source_quarantine_destination_fails_at_init(self) -> None:
        """Source quarantine to non-existent sink should fail before processing rows.

        When a source has on_validation_failure set to a sink that doesn't exist,
        the orchestrator should fail at initialization with a clear error message,
        NOT silently drop quarantined rows at runtime.
        """
        from elspeth.contracts import PluginSchema
        from elspeth.core.landscape import LandscapeDB
        from elspeth.engine.artifacts import ArtifactDescriptor
        from elspeth.engine.orchestrator import (
            Orchestrator,
            PipelineConfig,
            RouteValidationError,
        )

        db = LandscapeDB.in_memory()

        class RowSchema(PluginSchema):
            id: int
            name: str

        class QuarantiningSource(_TestSourceBase):
            """Source that yields one valid row and one quarantined row."""

            name = "quarantining_source"
            output_schema = RowSchema

            def __init__(self) -> None:
                self.load_called = False
                # Track the quarantine destination for validation
                self._on_validation_failure = "nonexistent_quarantine_sink"

            def on_start(self, ctx: Any) -> None:
                pass

            def load(self, ctx: Any) -> Any:
                self.load_called = True
                # Valid row
                yield SourceRow.valid({"id": 1, "name": "alice"})
                # Quarantined row - destination doesn't exist!
                yield SourceRow.quarantined(
                    row={"id": 2, "name": "bob", "bad_field": "invalid"},
                    error="Validation failed",
                    destination="nonexistent_quarantine_sink",
                )

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

        source = QuarantiningSource()
        default_sink = CollectSink()
        # Note: NO 'nonexistent_quarantine_sink' provided!

        config = PipelineConfig(
            source=as_source(source),
            transforms=[],
            sinks={"default": as_sink(default_sink)},  # Only default, no quarantine sink
        )

        orchestrator = Orchestrator(db)

        # Should fail at initialization with clear error message
        with pytest.raises(RouteValidationError) as exc_info:
            orchestrator.run(config, graph=build_test_graph(config))

        # Verify error message contains helpful information
        error_msg = str(exc_info.value)
        assert "nonexistent_quarantine_sink" in error_msg  # Invalid destination
        assert "default" in error_msg  # Available sinks

        # Verify no rows were processed (failed at validation, not runtime)
        assert not source.load_called, "Source.load() should not be called - validation failed first"


class TestOrchestratorQuarantineMetrics:
    """Test that QUARANTINED rows are counted separately from FAILED."""

    def test_orchestrator_counts_quarantined_rows(self) -> None:
        """Orchestrator should count QUARANTINED rows separately.

        A transform with _on_error="discard" intentionally quarantines rows
        when it returns TransformResult.error(). These should be counted
        as quarantined, not failed.
        """
        from elspeth.contracts import PluginSchema
        from elspeth.core.landscape import LandscapeDB
        from elspeth.engine.artifacts import ArtifactDescriptor
        from elspeth.engine.orchestrator import Orchestrator, PipelineConfig
        from elspeth.plugins.results import TransformResult

        db = LandscapeDB.in_memory()

        class ValueSchema(PluginSchema):
            value: int
            quality: str

        class ListSource(_TestSourceBase):
            name = "list_source"
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

        class QualityFilter(BaseTransform):
            """Transform that errors on 'bad' quality rows.

            With _on_error="discard", these become QUARANTINED.
            """

            name = "quality_filter"
            input_schema = ValueSchema
            output_schema = ValueSchema
            _on_error = "discard"  # Intentionally discard errors

            def __init__(self) -> None:
                super().__init__({})

            def process(self, row: Any, ctx: Any) -> TransformResult:
                if row.get("quality") == "bad":
                    return TransformResult.error({"reason": "bad_quality", "value": row["value"]})
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

        # 3 rows: good, bad, good
        source = ListSource(
            [
                {"value": 1, "quality": "good"},
                {"value": 2, "quality": "bad"},  # Will be quarantined
                {"value": 3, "quality": "good"},
            ]
        )
        transform = QualityFilter()
        sink = CollectSink()

        config = PipelineConfig(
            source=as_source(source),
            transforms=[transform],
            sinks={"default": as_sink(sink)},
        )

        orchestrator = Orchestrator(db)
        run_result = orchestrator.run(config, graph=build_test_graph(config))

        # Verify counts
        assert run_result.status == "completed"
        assert run_result.rows_processed == 3, "All 3 rows should be processed"
        assert run_result.rows_succeeded == 2, "2 good quality rows should succeed"
        assert run_result.rows_quarantined == 1, "1 bad quality row should be quarantined"
        assert run_result.rows_failed == 0, "No rows should fail (quarantine != fail)"

        # Only good rows written to sink
        assert len(sink.results) == 2
        assert all(r["quality"] == "good" for r in sink.results)
