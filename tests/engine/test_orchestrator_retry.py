# tests/engine/test_orchestrator_retry.py
"""Tests for Orchestrator retry functionality.

All test plugins inherit from base classes (BaseTransform, BaseGate)
because the processor uses isinstance() for type-safe plugin detection.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from elspeth.plugins.base import BaseTransform
from tests.conftest import (
    as_sink,
    as_source,
    as_transform,
)
from tests.engine.conftest import CollectSink, ListSource, _TestSchema
from tests.engine.orchestrator_test_helpers import build_production_graph

if TYPE_CHECKING:
    from elspeth.contracts.results import TransformResult


class TestOrchestratorRetry:
    """Tests for retry configuration in Orchestrator."""

    def test_orchestrator_creates_retry_manager_from_settings(self, payload_store) -> None:
        """Orchestrator creates RetryManager when settings.retry is configured."""
        from elspeth.contracts import PipelineRow
        from elspeth.core.config import (
            ElspethSettings,
            RetrySettings,
            SinkSettings,
            SourceSettings,
        )
        from elspeth.core.landscape import LandscapeDB
        from elspeth.engine.orchestrator import Orchestrator, PipelineConfig
        from elspeth.plugins.results import TransformResult

        db = LandscapeDB.in_memory()

        # Transform that tracks retry attempts via closure
        attempt_count = {"count": 0}

        class RetryableTransform(BaseTransform):
            name = "retryable"
            input_schema = _TestSchema
            output_schema = _TestSchema

            def __init__(self) -> None:
                super().__init__({"schema": {"mode": "observed"}})

            def process(self, row: PipelineRow, ctx: Any) -> TransformResult:
                attempt_count["count"] += 1
                # Fail with retryable error on first attempt
                if attempt_count["count"] == 1:
                    raise ConnectionError("Transient failure")
                return TransformResult.success(row.to_dict(), success_reason={"action": "passthrough"})

        # Settings with retry configuration
        settings = ElspethSettings(
            source=SourceSettings(
                plugin="csv",
                options={
                    "path": "test.csv",
                    "on_validation_failure": "discard",
                    "schema": {"mode": "observed"},
                },
            ),
            sinks={"default": SinkSettings(plugin="json", options={"path": "default.json", "schema": {"mode": "observed"}})},
            default_sink="default",
            retry=RetrySettings(
                max_attempts=3,
                initial_delay_seconds=0.01,  # Fast for testing
                max_delay_seconds=0.1,
            ),
        )

        source = ListSource([{"value": 42}])
        transform = RetryableTransform()
        sink = CollectSink()

        config = PipelineConfig(
            source=as_source(source),
            transforms=[as_transform(transform)],
            sinks={"default": as_sink(sink)},
        )

        # Use production graph path for test reliability
        graph = build_production_graph(config)

        orchestrator = Orchestrator(db)
        result = orchestrator.run(config, graph=graph, settings=settings, payload_store=payload_store)

        # Row should succeed after retry
        assert result.status == "completed"
        assert result.rows_processed == 1
        assert result.rows_succeeded == 1
        # Transform was called twice (first attempt failed, second succeeded)
        assert attempt_count["count"] == 2, f"Expected 2 attempts (1 failure + 1 success), got {attempt_count['count']}"
        assert len(sink.results) == 1

    def test_orchestrator_retry_exhausted_marks_row_failed(self, payload_store) -> None:
        """When all retry attempts fail, row should be marked FAILED."""
        from elspeth.contracts import PipelineRow
        from elspeth.core.config import (
            ElspethSettings,
            RetrySettings,
            SinkSettings,
            SourceSettings,
        )
        from elspeth.core.landscape import LandscapeDB
        from elspeth.engine.orchestrator import Orchestrator, PipelineConfig

        db = LandscapeDB.in_memory()

        # Transform that always fails with retryable error
        class AlwaysFailTransform(BaseTransform):
            name = "always_fail"
            input_schema = _TestSchema
            output_schema = _TestSchema

            def __init__(self) -> None:
                super().__init__({"schema": {"mode": "observed"}})

            def process(self, row: PipelineRow, ctx: Any) -> TransformResult:
                raise ConnectionError("Persistent failure")

        settings = ElspethSettings(
            source=SourceSettings(
                plugin="csv",
                options={
                    "path": "test.csv",
                    "on_validation_failure": "discard",
                    "schema": {"mode": "observed"},
                },
            ),
            sinks={"default": SinkSettings(plugin="json", options={"path": "default.json", "schema": {"mode": "observed"}})},
            default_sink="default",
            retry=RetrySettings(
                max_attempts=2,  # Will try twice then fail
                initial_delay_seconds=0.01,
                max_delay_seconds=0.1,
            ),
        )

        source = ListSource([{"value": 42}])
        transform = AlwaysFailTransform()
        sink = CollectSink()

        config = PipelineConfig(
            source=as_source(source),
            transforms=[as_transform(transform)],
            sinks={"default": as_sink(sink)},
        )

        # Use production graph path for test reliability
        graph = build_production_graph(config)

        orchestrator = Orchestrator(db)
        result = orchestrator.run(config, graph=graph, settings=settings, payload_store=payload_store)

        # Row should be marked failed after exhausting retries
        assert result.status == "completed"
        assert result.rows_processed == 1
        assert result.rows_failed == 1
        assert result.rows_succeeded == 0
        assert len(sink.results) == 0
