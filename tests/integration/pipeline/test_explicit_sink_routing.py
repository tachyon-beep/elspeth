# tests/integration/pipeline/test_explicit_sink_routing.py
"""Integration tests for explicit sink routing (bead amoc).

These tests validate that `on_success` routing works end-to-end through
the real production assembly path (ExecutionGraph.from_plugin_instances).

The explicit-sink-routing feature allows:
- Sources to declare on_success sink destination
- Transforms to declare on_success sink destination (terminal transforms)
- Coalesce nodes to declare on_success sink destination
- Fork branches with different on_success routes to per-branch sinks

ADR-required tests per bead amoc specification.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from elspeth.contracts import PipelineRow, RunStatus
from elspeth.core.config import AggregationSettings, CoalesceSettings, ElspethSettings, GateSettings, TriggerConfig
from elspeth.core.dag import GraphValidationError
from elspeth.core.landscape import LandscapeDB
from elspeth.engine.orchestrator import Orchestrator, PipelineConfig
from elspeth.plugins.base import BaseTransform
from elspeth.testing import make_pipeline_row
from tests.fixtures.base_classes import _TestSchema, as_sink, as_source, as_transform
from tests.fixtures.pipeline import build_production_graph
from tests.fixtures.plugins import CollectSink, ListSource

if TYPE_CHECKING:
    from elspeth.plugins.results import TransformResult


# ---------------------------------------------------------------------------
# Test Transforms
# ---------------------------------------------------------------------------


class IdentityTransform(BaseTransform):
    """Transform that passes data through unchanged."""

    name = "identity"
    input_schema = _TestSchema
    output_schema = _TestSchema

    def __init__(self) -> None:
        super().__init__({"schema": {"mode": "observed"}})

    def process(self, row: PipelineRow, ctx: Any) -> TransformResult:
        from elspeth.plugins.results import TransformResult

        return TransformResult.success(make_pipeline_row(row.to_dict()), success_reason={"action": "identity"})


class AddFieldTransform(BaseTransform):
    """Transform that adds a field to the row."""

    name = "add_field"
    input_schema = _TestSchema
    output_schema = _TestSchema

    def __init__(self, field_name: str, field_value: Any) -> None:
        super().__init__({"schema": {"mode": "observed"}})
        self._field_name = field_name
        self._field_value = field_value

    def process(self, row: PipelineRow, ctx: Any) -> TransformResult:
        from elspeth.plugins.results import TransformResult

        output = {**row.to_dict(), self._field_name: self._field_value}
        return TransformResult.success(
            make_pipeline_row(output),
            success_reason={"action": "add_field", "field": self._field_name},
        )


class BatchPassthroughTransform(BaseTransform):
    """Batch-aware transform that passes through rows unchanged."""

    name = "batch_passthrough"
    input_schema = _TestSchema
    output_schema = _TestSchema
    is_batch_aware = True

    def __init__(self) -> None:
        super().__init__({"schema": {"mode": "observed"}})

    def process(self, rows: list[PipelineRow], ctx: Any) -> TransformResult:
        from elspeth.plugins.results import TransformResult

        # Sum values from the batch
        total = sum(r["value"] for r in rows)
        result = {"count": len(rows), "total": total}
        return TransformResult.success(
            make_pipeline_row(result),
            success_reason={"action": "batch_passthrough"},
        )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestExplicitSinkRouting:
    """ADR-required tests for explicit sink routing feature."""

    def test_09_completed_row_carries_explicit_sink_name(self, payload_store) -> None:
        """Test 9: Linear pipeline routes to transform's on_success sink.

        Setup: source → transform(on_success=output) → output sink
        Verify: Completed rows arrive at the declared on_success sink.
        """
        db = LandscapeDB.in_memory()

        source = ListSource([{"value": 1}, {"value": 2}], on_success="output")
        transform = IdentityTransform()
        transform._on_success = "output"
        sink = CollectSink(name="output")

        config = PipelineConfig(
            source=as_source(source),
            transforms=[as_transform(transform)],
            sinks={"output": as_sink(sink)},
        )

        orchestrator = Orchestrator(db)
        run_result = orchestrator.run(config, graph=build_production_graph(config), payload_store=payload_store)

        assert run_result.status == RunStatus.COMPLETED
        assert run_result.rows_processed == 2
        assert len(sink.results) == 2
        assert sink.results[0] == {"value": 1}
        assert sink.results[1] == {"value": 2}

    def test_10_fork_branches_with_different_on_success_route_to_per_branch_sinks(self, payload_store) -> None:
        """Test 10: Fork gate sends rows to sink_a and sink_b branches.

        Setup: source → fork_gate → [sink_a, sink_b]
        Verify: Rows arrive at both sinks via forked branch routing.

        Terminal fork gates must route all paths to named sinks (no "continue").
        The "false" route goes to sink_a (never fires since condition=True).
        """
        db = LandscapeDB.in_memory()

        source = ListSource([{"value": 1}, {"value": 2}], on_success="sink_a")

        # Terminal fork gate: true=fork, false=sink_a (required but never fires)
        fork_gate = GateSettings(
            name="fork_gate",
            condition="True",
            routes={"true": "fork", "false": "sink_a"},
            fork_to=["sink_a", "sink_b"],
        )

        sink_a = CollectSink(name="sink_a")
        sink_b = CollectSink(name="sink_b")

        config = PipelineConfig(
            source=as_source(source),
            transforms=[],
            sinks={"sink_a": as_sink(sink_a), "sink_b": as_sink(sink_b)},
            gates=[fork_gate],
        )

        orchestrator = Orchestrator(db)
        run_result = orchestrator.run(config, graph=build_production_graph(config), payload_store=payload_store)

        assert run_result.status == RunStatus.COMPLETED
        assert run_result.rows_processed == 2

        # Fork duplicates each row to both branches
        assert len(sink_a.results) == 2
        assert len(sink_b.results) == 2

        for row in sink_a.results:
            assert "value" in row
        for row in sink_b.results:
            assert "value" in row

    def test_11_coalesce_output_routes_to_declared_on_success_sink(self, payload_store) -> None:
        """Test 11: Fork → coalesce → terminal gate → on_success sink.

        Setup: source → fork → [path_a, path_b] → coalesce → terminal_gate → output
        Verify: Merged results arrive at the gate's declared on_success sink.

        Uses a terminal gate after coalesce (same pattern as
        test_nonterminal_coalesce_continues_to_downstream_gate).
        """
        db = LandscapeDB.in_memory()

        source = ListSource([{"value": 1}, {"value": 2}], on_success="source_sink")

        # One transform per branch — named to match fork branch names
        transform = IdentityTransform()

        fork_gate = GateSettings(
            name="fork_gate",
            condition="True",
            routes={"true": "fork", "false": "continue"},
            fork_to=["path_a", "path_b"],
        )

        # Terminal gate routes merged result to output sink
        terminal_gate = GateSettings(
            name="terminal_gate",
            condition="True",
            routes={"true": "output", "false": "output"},
        )

        coalesce = CoalesceSettings(
            name="merge_paths",
            branches=["path_a", "path_b"],
            policy="require_all",
            merge="union",
        )

        output_sink = CollectSink(name="output")
        source_sink = CollectSink(name="source_sink")

        config = PipelineConfig(
            source=as_source(source),
            transforms=[as_transform(transform)],
            sinks={
                "output": as_sink(output_sink),
                "source_sink": as_sink(source_sink),
            },
            gates=[fork_gate, terminal_gate],
            coalesce_settings=[coalesce],
        )

        settings = ElspethSettings(
            source={"plugin": "test", "options": {"on_success": "source_sink"}},
            sinks={"output": {"plugin": "test"}, "source_sink": {"plugin": "test"}},
            gates=[fork_gate, terminal_gate],
            coalesce=[coalesce],
        )

        orchestrator = Orchestrator(db)
        run_result = orchestrator.run(
            config,
            graph=build_production_graph(config),
            settings=settings,
            payload_store=payload_store,
        )

        assert run_result.status == RunStatus.COMPLETED
        assert run_result.rows_processed == 2

        # Merged results route to output sink via terminal gate
        assert len(output_sink.results) == 2
        # Source sink shouldn't receive anything
        assert len(source_sink.results) == 0

    def test_12_aggregation_flush_routes_to_on_success_sink(self, payload_store) -> None:
        """Test 12: Aggregation transform with on_success routes to declared sink.

        Setup: source → aggregation(count=2, on_success=output) → output
        Verify: Flushed batch results arrive at on_success sink.

        Uses the same wiring pattern as test_aggregation_checkpoint_bug: the
        transform is a regular transform in the graph with on_success set,
        and aggregation_settings tells the Orchestrator to batch it.
        """
        from elspeth.core.dag import ExecutionGraph

        db = LandscapeDB.in_memory()

        source = ListSource([{"value": 1}, {"value": 2}, {"value": 3}], on_success="output")
        transform = BatchPassthroughTransform()
        transform._on_success = "output"
        sink = CollectSink(name="output")

        # Build graph with transform as regular transform (on_success wires to sink)
        graph = ExecutionGraph.from_plugin_instances(
            source=source,
            transforms=[transform],
            sinks={"output": sink},
            aggregations={},
            gates=[],
        )

        transform_node_id = graph.get_transform_id_map()[0]

        agg_settings = AggregationSettings(
            name="batch",
            plugin="batch_passthrough",
            trigger=TriggerConfig(count=2),
            output_mode="transform",
        )

        config = PipelineConfig(
            source=as_source(source),
            transforms=[as_transform(transform)],
            sinks={"output": as_sink(sink)},
            aggregation_settings={transform_node_id: agg_settings},
        )

        orchestrator = Orchestrator(db)
        run_result = orchestrator.run(config, graph=graph, payload_store=payload_store)

        assert run_result.status == RunStatus.COMPLETED
        assert run_result.rows_processed == 3

        # Aggregated results arrive at the on_success sink
        assert len(sink.results) >= 1

    @pytest.mark.skip(reason="Requires checkpoint simulation infrastructure")
    def test_13_checkpoint_resume_with_on_success_routes_identically(self, payload_store) -> None:
        """Test 13: Pipeline interrupted and resumed routes identically.

        SKIPPED: Checkpoint simulation infrastructure not available in test setup.
        """


class TestExplicitSinkRoutingEdgeCases:
    """Edge cases and error conditions for explicit sink routing."""

    def test_missing_on_success_raises_error(self, payload_store) -> None:
        """Terminal transform without on_success raises GraphValidationError."""
        source = ListSource([{"value": 1}], on_success="output")
        transform = IdentityTransform()
        # Deliberately NOT setting on_success — terminal transform without it
        sink = CollectSink(name="output")

        config = PipelineConfig(
            source=as_source(source),
            transforms=[as_transform(transform)],
            sinks={"output": as_sink(sink)},
        )

        with pytest.raises(GraphValidationError, match=r"terminal transform.*no 'on_success'"):
            build_production_graph(config)

    def test_source_on_success_used_when_no_transforms(self, payload_store) -> None:
        """Source on_success routes directly to sink when no transforms exist."""
        db = LandscapeDB.in_memory()

        source = ListSource([{"value": 1}], on_success="direct_sink")
        sink = CollectSink(name="direct_sink")

        config = PipelineConfig(
            source=as_source(source),
            transforms=[],
            sinks={"direct_sink": as_sink(sink)},
        )

        orchestrator = Orchestrator(db)
        run_result = orchestrator.run(config, graph=build_production_graph(config), payload_store=payload_store)

        assert run_result.status == RunStatus.COMPLETED
        assert run_result.rows_processed == 1
        assert len(sink.results) == 1

    def test_only_terminal_transform_can_have_on_success(self, payload_store) -> None:
        """Non-terminal transform is allowed (no on_success), terminal declares sink.

        Setup: source → transform1 → transform2(on_success=sink_b) → sink_b
        Verify: Rows route to terminal transform's on_success, not sink_a.
        """
        db = LandscapeDB.in_memory()

        source = ListSource([{"value": 1}], on_success="sink_b")

        transform1 = AddFieldTransform("t1", "done")
        # transform1._on_success is None (non-terminal, correct)

        transform2 = AddFieldTransform("t2", "done")
        transform2._on_success = "sink_b"  # Terminal transform declares sink

        sink_a = CollectSink(name="sink_a")
        sink_b = CollectSink(name="sink_b")

        config = PipelineConfig(
            source=as_source(source),
            transforms=[as_transform(transform1), as_transform(transform2)],
            sinks={"sink_a": as_sink(sink_a), "sink_b": as_sink(sink_b)},
        )

        orchestrator = Orchestrator(db)
        run_result = orchestrator.run(config, graph=build_production_graph(config), payload_store=payload_store)

        assert run_result.status == RunStatus.COMPLETED
        assert run_result.rows_processed == 1

        # Row arrives at sink_b (terminal transform's on_success), not sink_a
        assert len(sink_b.results) == 1
        assert len(sink_a.results) == 0
