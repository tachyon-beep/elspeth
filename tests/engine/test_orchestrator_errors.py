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
    as_transform,
)
from tests.engine.orchestrator_test_helpers import build_production_graph

if TYPE_CHECKING:
    from elspeth.contracts.results import TransformResult


class TestOrchestratorErrorHandling:
    """Test error handling in orchestration."""

    def test_run_marks_failed_on_transform_exception(self, payload_store) -> None:
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
                super().__init__({"schema": {"fields": "dynamic"}})

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
            transforms=[as_transform(transform)],
            sinks={"default": as_sink(sink)},
        )

        orchestrator = Orchestrator(db)

        with pytest.raises(RuntimeError, match="Transform exploded!"):
            orchestrator.run(config, graph=build_production_graph(config), payload_store=payload_store)

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

    def test_invalid_source_quarantine_destination_fails_at_init(self, payload_store) -> None:
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
            orchestrator.run(config, graph=build_production_graph(config), payload_store=payload_store)

        # Verify error message contains helpful information
        error_msg = str(exc_info.value)
        assert "nonexistent_quarantine_sink" in error_msg  # Invalid destination
        assert "default" in error_msg  # Available sinks

        # Verify no rows were processed (failed at validation, not runtime)
        assert not source.load_called, "Source.load() should not be called - validation failed first"


class TestOrchestratorQuarantineMetrics:
    """Test that QUARANTINED rows are counted separately from FAILED."""

    def test_orchestrator_counts_quarantined_rows(self, payload_store) -> None:
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
                super().__init__({"schema": {"fields": "dynamic"}})

            def process(self, row: Any, ctx: Any) -> TransformResult:
                if row.get("quality") == "bad":
                    return TransformResult.error({"reason": "validation_failed", "error": "bad_quality", "value": row["value"]})
                return TransformResult.success(row, success_reason={"action": "quality_check_passed"})

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
            transforms=[as_transform(transform)],
            sinks={"default": as_sink(sink)},
        )

        orchestrator = Orchestrator(db)
        run_result = orchestrator.run(config, graph=build_production_graph(config), payload_store=payload_store)

        # Verify counts
        assert run_result.status == "completed"
        assert run_result.rows_processed == 3, "All 3 rows should be processed"
        assert run_result.rows_succeeded == 2, "2 good quality rows should succeed"
        assert run_result.rows_quarantined == 1, "1 bad quality row should be quarantined"
        assert run_result.rows_failed == 0, "No rows should fail (quarantine != fail)"

        # Only good rows written to sink
        assert len(sink.results) == 2
        assert all(r["quality"] == "good" for r in sink.results)


class TestSourceQuarantineTokenOutcome:
    """Test that source-level quarantine records QUARANTINED token_outcome.

    BUG: Quarantined source rows lack QUARANTINED token_outcome
    - Source yields SourceRow.quarantined() for invalid rows
    - Orchestrator creates token and routes to quarantine sink
    - BUT: orchestrator never calls recorder.record_token_outcome(QUARANTINED)
    - Result: token_outcomes table has no terminal state for quarantined rows

    This violates the audit trail completeness requirement (CLAUDE.md: every row
    reaches exactly one terminal state).
    """

    def test_source_quarantine_records_quarantined_token_outcome(self, payload_store) -> None:
        """Source-quarantined rows MUST have QUARANTINED outcome in token_outcomes.

        When a source yields SourceRow.quarantined(), the orchestrator should:
        1. Create a token for the quarantined row
        2. Record QUARANTINED token_outcome with error_hash
        3. Route the row to the quarantine sink

        The audit trail must be complete - explain/lineage queries should find
        the terminal state for quarantined rows.
        """
        from collections.abc import Iterator

        from elspeth.contracts import PluginSchema, RowOutcome
        from elspeth.core.landscape import LandscapeDB
        from elspeth.engine.artifacts import ArtifactDescriptor
        from elspeth.engine.orchestrator import Orchestrator, PipelineConfig

        db = LandscapeDB.in_memory()

        class RowSchema(PluginSchema):
            id: int
            name: str

        class QuarantiningSource(_TestSourceBase):
            """Source that yields one valid row and one quarantined row."""

            name = "quarantining_source"
            output_schema = RowSchema

            def load(self, ctx: Any) -> Iterator[SourceRow]:
                # Valid row
                yield SourceRow.valid({"id": 1, "name": "alice"})
                # Quarantined row - simulates validation failure
                yield SourceRow.quarantined(
                    row={"id": 2, "name": "bob", "invalid_field": "bad_data"},
                    error="Schema validation failed: unexpected field 'invalid_field'",
                    destination="quarantine",
                )
                # Another valid row
                yield SourceRow.valid({"id": 3, "name": "charlie"})

        class CollectSink(_TestSinkBase):
            name = "collect_sink"

            def __init__(self) -> None:
                self.results: list[dict[str, Any]] = []

            def write(self, rows: Any, ctx: Any) -> ArtifactDescriptor:
                self.results.extend(rows)
                return ArtifactDescriptor.for_file(path="memory", size_bytes=0, content_hash="")

        source = QuarantiningSource()
        default_sink = CollectSink()
        quarantine_sink = CollectSink()

        config = PipelineConfig(
            source=as_source(source),
            transforms=[],
            sinks={
                "default": as_sink(default_sink),
                "quarantine": as_sink(quarantine_sink),
            },
        )

        orchestrator = Orchestrator(db)
        run_result = orchestrator.run(config, graph=build_production_graph(config), payload_store=payload_store)

        # Verify run completed successfully
        assert run_result.status == "completed"
        assert run_result.rows_processed == 3
        assert run_result.rows_succeeded == 2  # alice and charlie
        assert run_result.rows_quarantined == 1  # bob

        # Verify sinks received correct rows
        assert len(default_sink.results) == 2
        assert len(quarantine_sink.results) == 1
        assert quarantine_sink.results[0]["id"] == 2  # bob went to quarantine

        # === THE CRITICAL ASSERTION ===
        # Query token_outcomes table to verify QUARANTINED outcome was recorded
        run_id = run_result.run_id

        # Get all token outcomes for this run
        from sqlalchemy import select

        from elspeth.core.landscape.schema import token_outcomes_table

        with db.engine.connect() as conn:
            outcomes = conn.execute(select(token_outcomes_table).where(token_outcomes_table.c.run_id == run_id)).fetchall()

        # Should have 3 terminal outcomes: 2 COMPLETED + 1 QUARANTINED
        assert len(outcomes) == 3, f"Expected 3 token outcomes, got {len(outcomes)}"

        # Find the QUARANTINED outcome specifically
        quarantined_outcomes = [o for o in outcomes if o.outcome == RowOutcome.QUARANTINED.value]
        assert len(quarantined_outcomes) == 1, (
            f"Expected exactly 1 QUARANTINED outcome, got {len(quarantined_outcomes)}. "
            f"All outcomes: {[(o.outcome, o.error_hash) for o in outcomes]}"
        )

        # Verify error_hash was recorded (for audit trail completeness)
        quarantined = quarantined_outcomes[0]
        assert quarantined.error_hash is not None, (
            "QUARANTINED outcome must have error_hash for audit trail. "
            "The error hash allows correlating with the original validation error."
        )
