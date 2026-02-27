# tests/integration/pipeline/orchestrator/test_t18_characterization.py
"""Characterization tests for T18 orchestrator decomposition.

These tests exercise the full _execute_run() and _process_resumed_rows() paths
with multi-feature pipelines. They serve as regression oracles for the 15-commit
extraction sequence — if any extraction breaks behavior, these tests catch it.

IMPORTANT: Do NOT modify these tests during the extraction. If a test fails
after an extraction commit, the extraction introduced a regression.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from sqlalchemy import text

from elspeth.contracts import (
    PipelineRow,
    RunStatus,
)
from elspeth.contracts.results import SourceRow
from elspeth.contracts.schema_contract import FieldContract, SchemaContract
from elspeth.core.landscape import LandscapeDB
from elspeth.core.landscape.recorder import LandscapeRecorder
from elspeth.engine.orchestrator import Orchestrator, PipelineConfig
from elspeth.plugins.results import TransformResult
from elspeth.testing import make_pipeline_row, make_source_row
from tests.fixtures.base_classes import (
    _TestSchema,
    _TestSourceBase,
    _TestTransformBase,
    as_sink,
    as_source,
    as_transform,
)
from tests.fixtures.pipeline import build_production_graph
from tests.fixtures.plugins import CollectSink, ListSource
from tests.fixtures.stores import MockPayloadStore

# ---------------------------------------------------------------------------
# Test fixtures: Quarantine-capable source
# ---------------------------------------------------------------------------


class QuarantiningSource(_TestSourceBase):
    """Source that quarantines rows based on a 'valid' field.

    Rows with valid=False are quarantined. This exercises:
    - Field resolution ordering (must be from first VALID row)
    - Quarantine routing (direct to configured sink)
    - Schema contract recording (must skip quarantined rows)
    """

    name = "quarantining_source"
    output_schema = _TestSchema

    def __init__(self, rows: list[dict[str, Any]], quarantine_sink: str = "errors") -> None:
        super().__init__()
        self._rows = rows
        self._on_validation_failure = quarantine_sink

    def load(self, ctx: Any) -> Any:
        for row in self._rows:
            if not row.get("valid", True):
                yield SourceRow.quarantined(
                    row=row,
                    error="validation_failed:valid=False",
                    destination=self._on_validation_failure,
                )
            else:
                yield make_source_row(row)

    def get_field_resolution(self) -> tuple[dict[str, str], str] | None:
        return ({"value": "value", "valid": "valid"}, "identity")


class DoubleValueTransform(_TestTransformBase):
    """Transform that doubles the 'value' field."""

    name = "double_value"
    input_schema = _TestSchema
    output_schema = _TestSchema

    def process(self, row: PipelineRow, ctx: Any) -> TransformResult:
        data = row.to_dict()
        data["doubled"] = data.get("value", 0) * 2
        return TransformResult.success(
            make_pipeline_row(data),
            success_reason={"action": "doubled"},
        )


# ---------------------------------------------------------------------------
# Helper: set up recorder + run_id for direct _execute_run() calls
# ---------------------------------------------------------------------------


def _begin_test_run(db: LandscapeDB) -> tuple[LandscapeRecorder, str, MockPayloadStore]:
    """Create a recorder and begin a run for testing.

    Returns (recorder, run_id, payload_store).
    """
    payload_store = MockPayloadStore()
    recorder = LandscapeRecorder(db, payload_store=payload_store)
    run = recorder.begin_run(
        config={},
        canonical_version="sha256-rfc8785-v1",
    )
    return recorder, run.run_id, payload_store


# ---------------------------------------------------------------------------
# Characterization test: Full _execute_run() path
# ---------------------------------------------------------------------------


class TestT18CharacterizationExecuteRun:
    """Regression oracle for the T18 extraction sequence.

    Pipeline: QuarantiningSource → DoubleValueTransform → CollectSink("output") + CollectSink("errors")
    Input: 5 rows — first 2 quarantined, next 3 valid.

    This exercises:
    - Quarantine routing (rows 0-1 → errors sink)
    - Field resolution from first VALID row (row 2, not row 0)
    - Transform processing (rows 2-4 → output sink)
    - Counter arithmetic with quarantine + success
    - operation_id attribution (transforms see None)
    - Landscape audit records (nodes, node_states, routing_events)
    """

    def _build_pipeline(
        self,
    ) -> tuple[
        QuarantiningSource,
        DoubleValueTransform,
        CollectSink,
        CollectSink,
        PipelineConfig,
    ]:
        rows = [
            {"value": 10, "valid": False},  # quarantined (row 0)
            {"value": 20, "valid": False},  # quarantined (row 1)
            {"value": 30, "valid": True},  # valid (row 2) — first valid row
            {"value": 40, "valid": True},  # valid (row 3)
            {"value": 50, "valid": True},  # valid (row 4)
        ]
        source = as_source(QuarantiningSource(rows, quarantine_sink="errors"))
        transform = as_transform(DoubleValueTransform())
        output_sink = as_sink(CollectSink("output"))
        error_sink = as_sink(CollectSink("errors"))

        config = PipelineConfig(
            source=source,
            transforms=[transform],
            sinks={"output": output_sink, "errors": error_sink},
        )
        return source, transform, output_sink, error_sink, config

    def test_counter_values_exact(self) -> None:
        """Assert exact counter values for the characterization pipeline.

        Note: _execute_run() returns RUNNING status (the public run() wrapper
        sets COMPLETED after finalize_run()). This is the current behavior.
        """
        _source, _transform, _output_sink, _error_sink, config = self._build_pipeline()
        db = LandscapeDB.in_memory()
        orchestrator = Orchestrator(db)

        graph = build_production_graph(config)
        recorder, run_id, payload_store = _begin_test_run(db)

        result = orchestrator._execute_run(
            recorder=recorder,
            run_id=run_id,
            config=config,
            graph=graph,
            payload_store=payload_store,
        )

        # _execute_run returns RUNNING — run() wrapper sets COMPLETED
        assert result.status == RunStatus.RUNNING
        assert result.rows_processed == 5
        assert result.rows_quarantined == 2
        assert result.rows_succeeded == 3
        assert result.rows_failed == 0
        assert result.rows_routed == 0
        assert result.rows_forked == 0

    def test_sink_contents(self) -> None:
        """Assert sink contents match expected routing."""
        _source, _transform, output_sink, error_sink, config = self._build_pipeline()
        db = LandscapeDB.in_memory()
        orchestrator = Orchestrator(db)

        graph = build_production_graph(config)
        recorder, run_id, payload_store = _begin_test_run(db)

        orchestrator._execute_run(
            recorder=recorder,
            run_id=run_id,
            config=config,
            graph=graph,
            payload_store=payload_store,
        )

        # Output sink gets 3 valid rows (doubled)
        assert len(output_sink.results) == 3
        # Error sink gets 2 quarantined rows
        assert len(error_sink.results) == 2

    def test_operation_id_not_leaked_to_transforms(self) -> None:
        """Assert transforms never see a non-None operation_id.

        Uses patch.object spy pattern from the design doc. The source_load
        operation sets operation_id, but it must be cleared before transforms
        execute. If extraction breaks the operation_id lifecycle, this catches it.
        """
        _source, transform, _output_sink, _error_sink, config = self._build_pipeline()
        db = LandscapeDB.in_memory()
        orchestrator = Orchestrator(db)

        graph = build_production_graph(config)
        recorder, run_id, payload_store = _begin_test_run(db)

        captured_operation_ids: list[str | None] = []
        original_process = transform.process

        def spy_process(row: PipelineRow, ctx: Any) -> TransformResult:
            captured_operation_ids.append(ctx.operation_id)
            return original_process(row, ctx)

        with patch.object(transform, "process", side_effect=spy_process):
            orchestrator._execute_run(
                recorder=recorder,
                run_id=run_id,
                config=config,
                graph=graph,
                payload_store=payload_store,
            )

        # All 3 valid rows should have been processed
        assert len(captured_operation_ids) == 3
        # None of them should have seen a non-None operation_id
        assert all(op_id is None for op_id in captured_operation_ids), (
            f"operation_id leaked into transform execution: {captured_operation_ids}"
        )

    def test_field_resolution_recorded_despite_first_quarantine(self) -> None:
        """Assert field resolution is recorded even when first row is quarantined.

        Field resolution must come from the first VALID row, not be skipped
        when the first row is quarantined. Stored as source_field_resolution_json
        on the runs table.
        """
        _source, _transform, _output_sink, _error_sink, config = self._build_pipeline()
        db = LandscapeDB.in_memory()
        orchestrator = Orchestrator(db)

        graph = build_production_graph(config)
        recorder, run_id, payload_store = _begin_test_run(db)

        orchestrator._execute_run(
            recorder=recorder,
            run_id=run_id,
            config=config,
            graph=graph,
            payload_store=payload_store,
        )

        # Check that field resolution was recorded on the runs table
        with db._engine.connect() as conn:
            result = conn.execute(
                text("SELECT source_field_resolution_json FROM runs WHERE run_id = :run_id"),
                {"run_id": run_id},
            )
            row = result.fetchone()
        assert row is not None, "Run not found in DB"
        assert row[0] is not None, "source_field_resolution_json should be set (first valid row provides field resolution)"

    def test_audit_record_counts(self) -> None:
        """Assert Landscape audit records are complete.

        After the run:
        - nodes table should have entries for source, transform, output sink, errors sink
        - routing_events should have DIVERT entries for quarantined rows
        """
        _source, _transform, _output_sink, _error_sink, config = self._build_pipeline()
        db = LandscapeDB.in_memory()
        orchestrator = Orchestrator(db)

        graph = build_production_graph(config)
        recorder, run_id, payload_store = _begin_test_run(db)

        orchestrator._execute_run(
            recorder=recorder,
            run_id=run_id,
            config=config,
            graph=graph,
            payload_store=payload_store,
        )

        with db._engine.connect() as conn:
            # Nodes registered
            node_count = conn.execute(
                text("SELECT COUNT(*) FROM nodes WHERE run_id = :run_id"),
                {"run_id": run_id},
            ).scalar()
            # At minimum: source + transform + 2 sinks = 4
            assert node_count >= 4, f"Expected >= 4 nodes, got {node_count}"

            # Routing events for quarantined rows (DIVERT mode)
            divert_count = conn.execute(
                text(
                    "SELECT COUNT(*) FROM routing_events re "
                    "JOIN node_states ns ON re.state_id = ns.state_id "
                    "WHERE ns.run_id = :run_id AND re.mode = :mode"
                ),
                {"run_id": run_id, "mode": "divert"},
            ).scalar()
            assert divert_count == 2, f"Expected 2 DIVERT routing events, got {divert_count}"

    def test_current_graph_not_cleared_on_error(self) -> None:
        """Assert _current_graph is NOT cleared when _execute_run() raises.

        Currently, _current_graph = None is OUTSIDE the finally block in
        _execute_run(), so errors leave it set. This characterizes the current
        behavior — if a future extraction moves cleanup into the finally block,
        this test should be updated to expect None.
        """
        db = LandscapeDB.in_memory()
        orchestrator = Orchestrator(db)

        class ErrorTransform(_TestTransformBase):
            name = "error_transform"
            input_schema = _TestSchema
            output_schema = _TestSchema

            def process(self, row: PipelineRow, ctx: Any) -> TransformResult:
                raise RuntimeError("deliberate error for characterization test")

        source = as_source(ListSource([{"value": 1}]))
        transform = as_transform(ErrorTransform())
        sink = as_sink(CollectSink("output"))

        config = PipelineConfig(
            source=source,
            transforms=[transform],
            sinks={"output": sink},
        )

        graph = build_production_graph(config)
        recorder, run_id, payload_store = _begin_test_run(db)

        with pytest.raises(RuntimeError, match="deliberate error"):
            orchestrator._execute_run(
                recorder=recorder,
                run_id=run_id,
                config=config,
                graph=graph,
                payload_store=payload_store,
            )

        # Current behavior: _current_graph is NOT cleared on error
        # (the assignment is after the finally block, not inside it)
        assert orchestrator._current_graph is not None


# ---------------------------------------------------------------------------
# Characterization test: Resume path
# ---------------------------------------------------------------------------


class TestT18CharacterizationResumePath:
    """Resume-specific characterization tests.

    These verify the behavioral divergences between _execute_run() and
    _process_resumed_rows() documented in the design.
    """

    def test_source_on_start_not_called_during_resume(self) -> None:
        """Assert source.on_start() is NOT called during resume.

        The resume path uses include_source_on_start=False because the source
        was fully consumed in the original run. Transform/sink on_start MUST
        still fire.

        Strategy: First do a full _execute_run() to populate DB with nodes/edges,
        then call _process_resumed_rows() with empty rows on the same run.
        """
        db = LandscapeDB.in_memory()
        orchestrator = Orchestrator(db)

        on_start_calls: dict[str, int] = {"source": 0, "transform": 0, "sink": 0}

        class TrackingSource(_TestSourceBase):
            name = "tracking_source"
            output_schema = _TestSchema

            def on_start(self, ctx: Any) -> None:
                on_start_calls["source"] += 1

            def load(self, ctx: Any) -> Any:
                # Yield one row so the original run has data to process
                yield make_source_row({"value": 1})

        class TrackingTransform(_TestTransformBase):
            name = "tracking_transform"
            input_schema = _TestSchema
            output_schema = _TestSchema

            def on_start(self, ctx: Any) -> None:
                on_start_calls["transform"] += 1

            def process(self, row: PipelineRow, ctx: Any) -> TransformResult:
                return TransformResult.success(
                    make_pipeline_row(row.to_dict()),
                    success_reason={"action": "identity"},
                )

        source = as_source(TrackingSource())
        transform = as_transform(TrackingTransform())
        output_sink = as_sink(CollectSink("output"))

        config = PipelineConfig(
            source=source,
            transforms=[transform],
            sinks={"output": output_sink},
        )

        graph = build_production_graph(config)
        recorder, run_id, payload_store = _begin_test_run(db)

        # First: run the full pipeline to populate DB with nodes, edges, etc.
        orchestrator._execute_run(
            recorder=recorder,
            run_id=run_id,
            config=config,
            graph=graph,
            payload_store=payload_store,
        )

        # Reset counters — we only care about resume behavior
        on_start_calls["source"] = 0
        on_start_calls["transform"] = 0
        on_start_calls["sink"] = 0

        # Create a minimal schema contract for resume
        schema_contract = SchemaContract(
            mode="OBSERVED",
            fields=(
                FieldContract(
                    normalized_name="value",
                    original_name="value",
                    python_type=int,
                    required=False,
                    source="inferred",
                ),
            ),
            locked=True,
        )

        # Spy on sink on_start using patch.object
        original_sink_on_start = output_sink.on_start

        def tracking_sink_on_start(ctx: Any) -> None:
            on_start_calls["sink"] += 1
            original_sink_on_start(ctx)

        # Call _process_resumed_rows directly with empty rows
        with patch.object(output_sink, "on_start", side_effect=tracking_sink_on_start):
            result = orchestrator._process_resumed_rows(
                recorder=recorder,
                run_id=run_id,
                config=config,
                graph=graph,
                unprocessed_rows=[],
                restored_aggregation_state={},
                payload_store=payload_store,
                schema_contract=schema_contract,
            )

        # _process_resumed_rows also returns RUNNING (same as _execute_run)
        assert result.status == RunStatus.RUNNING
        assert on_start_calls["source"] == 0, "Source on_start should NOT be called during resume"
        assert on_start_calls["transform"] == 1, "Transform on_start should be called during resume"
        assert on_start_calls["sink"] == 1, "Sink on_start should be called during resume"
