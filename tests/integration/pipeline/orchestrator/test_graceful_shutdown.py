# tests/integration/pipeline/orchestrator/test_graceful_shutdown.py
"""Integration tests for graceful shutdown (SIGINT/SIGTERM).

Tests the full orchestrator interrupt flow: shutdown event triggers loop break,
pending work is flushed, run is marked INTERRUPTED, and is resumable.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

import pytest

from elspeth.contracts import PipelineRow, RunStatus
from elspeth.contracts.enums import Determinism
from elspeth.contracts.errors import GracefulShutdownError
from elspeth.contracts.results import SourceRow
from elspeth.plugins.base import BaseTransform
from elspeth.plugins.results import TransformResult
from tests.fixtures.base_classes import (
    _TestSchema,
    as_sink,
    as_source,
    as_transform,
)
from tests.fixtures.pipeline import build_production_graph
from tests.fixtures.plugins import CollectSink, ListSource

if TYPE_CHECKING:
    from elspeth.core.landscape import LandscapeDB


class InterruptAfterN(BaseTransform):
    """Transform that sets a shutdown event after processing N rows."""

    name = "interrupt_after_n"
    input_schema = _TestSchema
    output_schema = _TestSchema

    def __init__(self, n: int, shutdown_event: threading.Event) -> None:
        super().__init__({"schema": {"mode": "observed"}})
        self._n = n
        self._event = shutdown_event
        self._count = 0

    def process(self, row: PipelineRow, ctx: Any) -> TransformResult:
        self._count += 1
        if self._count >= self._n:
            self._event.set()
        return TransformResult.success(row, success_reason={"action": "processed"})


class QuarantineSource:
    """Source that emits quarantined rows, setting shutdown event after N."""

    name = "quarantine_source"
    output_schema = _TestSchema
    node_id: str | None = None
    determinism = Determinism.DETERMINISTIC
    plugin_version = "1.0.0"
    _on_validation_failure: str = "quarantine"
    on_success: str = "default"

    def __init__(self, total: int, interrupt_after: int, shutdown_event: threading.Event) -> None:
        self.config: dict[str, Any] = {"schema": {"mode": "observed"}}
        self._total = total
        self._interrupt_after = interrupt_after
        self._event = shutdown_event
        self._count = 0

    def on_start(self, ctx: Any) -> None:
        pass

    def load(self, ctx: Any) -> Iterator[SourceRow]:
        for i in range(self._total):
            self._count += 1
            if self._count >= self._interrupt_after:
                self._event.set()
            yield SourceRow.quarantined(
                row={"value": i},
                error=f"validation_error_{i}",
                destination="quarantine",
            )

    def on_complete(self, ctx: Any) -> None:
        pass

    def close(self) -> None:
        pass

    def get_field_resolution(self) -> tuple[dict[str, str], str | None] | None:
        return None

    def get_schema_contract(self) -> None:
        return None


class TestShutdownBreaksLoop:
    """Tests that shutdown event correctly interrupts the processing loop."""

    def test_shutdown_breaks_loop_after_current_row(self, landscape_db: LandscapeDB, payload_store) -> None:
        """GracefulShutdownError raised with correct rows_processed."""
        from elspeth.engine.orchestrator import Orchestrator, PipelineConfig

        shutdown_event = threading.Event()
        source = ListSource([{"value": i} for i in range(10)])
        transform = InterruptAfterN(3, shutdown_event)
        transform.on_success = "default"
        sink = CollectSink()

        config = PipelineConfig(
            source=as_source(source),
            transforms=[as_transform(transform)],
            sinks={"default": as_sink(sink)},
        )

        orchestrator = Orchestrator(db=landscape_db)
        graph = build_production_graph(config)

        with pytest.raises(GracefulShutdownError) as exc_info:
            orchestrator.run(config, graph=graph, payload_store=payload_store, shutdown_event=shutdown_event)

        assert exc_info.value.rows_processed == 3
        assert exc_info.value.run_id is not None

    def test_shutdown_writes_pending_tokens(self, landscape_db: LandscapeDB, payload_store) -> None:
        """All processed tokens reach sinks before shutdown error."""
        from elspeth.engine.orchestrator import Orchestrator, PipelineConfig

        shutdown_event = threading.Event()
        source = ListSource([{"value": i} for i in range(10)])
        transform = InterruptAfterN(5, shutdown_event)
        transform.on_success = "default"
        sink = CollectSink()

        config = PipelineConfig(
            source=as_source(source),
            transforms=[as_transform(transform)],
            sinks={"default": as_sink(sink)},
        )

        orchestrator = Orchestrator(db=landscape_db)
        graph = build_production_graph(config)

        with pytest.raises(GracefulShutdownError):
            orchestrator.run(config, graph=graph, payload_store=payload_store, shutdown_event=shutdown_event)

        # All 5 processed rows should have been written to the sink
        assert len(sink.results) == 5

    def test_shutdown_run_status_is_interrupted(self, landscape_db: LandscapeDB, payload_store) -> None:
        """Database shows INTERRUPTED status, not FAILED."""
        from sqlalchemy import select

        from elspeth.core.landscape.schema import runs_table
        from elspeth.engine.orchestrator import Orchestrator, PipelineConfig

        shutdown_event = threading.Event()
        source = ListSource([{"value": i} for i in range(10)])
        transform = InterruptAfterN(3, shutdown_event)
        transform.on_success = "default"
        sink = CollectSink()

        config = PipelineConfig(
            source=as_source(source),
            transforms=[as_transform(transform)],
            sinks={"default": as_sink(sink)},
        )

        orchestrator = Orchestrator(db=landscape_db)
        graph = build_production_graph(config)

        with pytest.raises(GracefulShutdownError) as exc_info:
            orchestrator.run(config, graph=graph, payload_store=payload_store, shutdown_event=shutdown_event)

        run_id = exc_info.value.run_id

        with landscape_db.engine.connect() as conn:
            run = conn.execute(select(runs_table.c.status).where(runs_table.c.run_id == run_id)).fetchone()

        assert run is not None
        assert run.status == RunStatus.INTERRUPTED

    def test_shutdown_calls_plugin_cleanup(self, landscape_db: LandscapeDB, payload_store) -> None:
        """close() is called on all plugins during shutdown."""
        from elspeth.engine.orchestrator import Orchestrator, PipelineConfig

        shutdown_event = threading.Event()
        source = ListSource([{"value": i} for i in range(5)])
        transform = InterruptAfterN(2, shutdown_event)
        transform.on_success = "default"
        sink = CollectSink()

        # Track close() calls
        close_calls: list[str] = []
        original_source_close = source.close
        original_sink_close = sink.close

        def track_source_close() -> None:
            close_calls.append("source")
            original_source_close()

        def track_sink_close() -> None:
            close_calls.append("sink")
            original_sink_close()

        source.close = track_source_close  # type: ignore[method-assign]
        sink.close = track_sink_close  # type: ignore[method-assign]

        config = PipelineConfig(
            source=as_source(source),
            transforms=[as_transform(transform)],
            sinks={"default": as_sink(sink)},
        )

        orchestrator = Orchestrator(db=landscape_db)
        graph = build_production_graph(config)

        with pytest.raises(GracefulShutdownError):
            orchestrator.run(config, graph=graph, payload_store=payload_store, shutdown_event=shutdown_event)

        assert "source" in close_calls
        assert "sink" in close_calls

    def test_no_interrupt_if_all_rows_consumed(self, landscape_db: LandscapeDB, payload_store) -> None:
        """Signal on last row still results in GracefulShutdownError with all rows processed."""
        from elspeth.engine.orchestrator import Orchestrator, PipelineConfig

        shutdown_event = threading.Event()
        # Interrupt after row 5 out of 5 — all rows consumed, but event is set
        source = ListSource([{"value": i} for i in range(5)])
        transform = InterruptAfterN(5, shutdown_event)
        transform.on_success = "default"
        sink = CollectSink()

        config = PipelineConfig(
            source=as_source(source),
            transforms=[as_transform(transform)],
            sinks={"default": as_sink(sink)},
        )

        orchestrator = Orchestrator(db=landscape_db)
        graph = build_production_graph(config)

        # Event is set on the LAST row, so the shutdown check fires at end of loop
        with pytest.raises(GracefulShutdownError) as exc_info:
            orchestrator.run(config, graph=graph, payload_store=payload_store, shutdown_event=shutdown_event)

        # All 5 rows were processed before shutdown triggered
        assert exc_info.value.rows_processed == 5
        assert len(sink.results) == 5

    def test_shutdown_interrupts_quarantined_row_stream(self, landscape_db: LandscapeDB, payload_store) -> None:
        """Shutdown event is checked on quarantine path, not just normal path."""
        from elspeth.engine.orchestrator import Orchestrator, PipelineConfig

        shutdown_event = threading.Event()
        # Source emits 100 quarantined rows; event set after row 5
        source = QuarantineSource(total=100, interrupt_after=5, shutdown_event=shutdown_event)
        quarantine_sink = CollectSink()

        config = PipelineConfig(
            source=as_source(source),
            transforms=[],
            sinks={"default": as_sink(CollectSink()), "quarantine": as_sink(quarantine_sink)},
        )

        orchestrator = Orchestrator(db=landscape_db)
        graph = build_production_graph(config)

        with pytest.raises(GracefulShutdownError) as exc_info:
            orchestrator.run(config, graph=graph, payload_store=payload_store, shutdown_event=shutdown_event)

        # Should stop well before 100 rows — event fires at row 5,
        # so at most a few more rows may be processed before the check fires.
        assert exc_info.value.rows_processed <= 10
        assert exc_info.value.rows_processed >= 5


class TestInterruptAndResume:
    """Tests for interrupt → resume pipeline lifecycle."""

    def test_interrupted_run_is_resumable(self, landscape_db: LandscapeDB, payload_store) -> None:
        """Interrupt after N of M rows, verify checkpoint and resumability."""
        from elspeth.contracts.config.runtime import RuntimeCheckpointConfig
        from elspeth.core.checkpoint import CheckpointManager, RecoveryManager
        from elspeth.core.config import CheckpointSettings
        from elspeth.engine.orchestrator import Orchestrator, PipelineConfig

        total_rows = 10
        interrupt_after = 5

        checkpoint_mgr = CheckpointManager(landscape_db)
        settings = CheckpointSettings(enabled=True, frequency="every_row")
        checkpoint_config = RuntimeCheckpointConfig.from_settings(settings)

        # Run and interrupt
        shutdown_event = threading.Event()
        source = ListSource([{"value": i} for i in range(total_rows)])
        transform = InterruptAfterN(interrupt_after, shutdown_event)
        transform.on_success = "default"
        sink = CollectSink()

        config = PipelineConfig(
            source=as_source(source),
            transforms=[as_transform(transform)],
            sinks={"default": as_sink(sink)},
        )

        orchestrator = Orchestrator(
            db=landscape_db,
            checkpoint_manager=checkpoint_mgr,
            checkpoint_config=checkpoint_config,
        )
        graph = build_production_graph(config)

        with pytest.raises(GracefulShutdownError) as exc_info:
            orchestrator.run(config, graph=graph, payload_store=payload_store, shutdown_event=shutdown_event)

        run_id = exc_info.value.run_id
        assert exc_info.value.rows_processed == interrupt_after
        assert len(sink.results) == interrupt_after

        # Verify DB status is INTERRUPTED
        from sqlalchemy import select

        from elspeth.core.landscape.schema import runs_table

        with landscape_db.engine.connect() as conn:
            run = conn.execute(select(runs_table.c.status).where(runs_table.c.run_id == run_id)).fetchone()
        assert run is not None
        assert run.status == RunStatus.INTERRUPTED

        # Verify the run IS resumable
        recovery = RecoveryManager(landscape_db, checkpoint_mgr)
        check = recovery.can_resume(run_id, graph)
        assert check.can_resume, f"Expected resumable, got: {check.reason}"

    def test_shutdown_creates_checkpoint(self, landscape_db: LandscapeDB, payload_store) -> None:
        """Checkpoint exists after graceful shutdown."""
        from elspeth.contracts.config.runtime import RuntimeCheckpointConfig
        from elspeth.core.checkpoint import CheckpointManager
        from elspeth.core.config import CheckpointSettings
        from elspeth.engine.orchestrator import Orchestrator, PipelineConfig

        checkpoint_mgr = CheckpointManager(landscape_db)
        settings = CheckpointSettings(enabled=True, frequency="every_row")
        checkpoint_config = RuntimeCheckpointConfig.from_settings(settings)

        shutdown_event = threading.Event()
        source = ListSource([{"value": i} for i in range(10)])
        transform = InterruptAfterN(5, shutdown_event)
        transform.on_success = "default"
        sink = CollectSink()

        config = PipelineConfig(
            source=as_source(source),
            transforms=[as_transform(transform)],
            sinks={"default": as_sink(sink)},
        )

        orchestrator = Orchestrator(
            db=landscape_db,
            checkpoint_manager=checkpoint_mgr,
            checkpoint_config=checkpoint_config,
        )
        graph = build_production_graph(config)

        with pytest.raises(GracefulShutdownError) as exc_info:
            orchestrator.run(config, graph=graph, payload_store=payload_store, shutdown_event=shutdown_event)

        run_id = exc_info.value.run_id

        # Verify checkpoint was created
        checkpoint = checkpoint_mgr.get_latest_checkpoint(run_id)
        assert checkpoint is not None
