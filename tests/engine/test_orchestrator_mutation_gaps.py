# tests/engine/test_orchestrator_mutation_gaps.py
"""Tests specifically targeting mutation testing gaps in orchestrator.py.

These tests were written to kill surviving mutants found during mutation testing.
Each test targets specific lines where mutations survived, indicating weak coverage.

Mutation testing run: 2026-01-23 (partial, 59% complete)
Survivors in orchestrator.py: 48 unique lines
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

import pytest

from elspeth.contracts import Determinism, RunStatus, SourceRow
from elspeth.engine.orchestrator import PipelineConfig, RouteValidationError, RunResult
from tests.conftest import (
    _TestSchema,
    _TestSinkBase,
    _TestSourceBase,
    as_sink,
    as_source,
)

if TYPE_CHECKING:
    from elspeth.contracts.results import TransformResult
    from elspeth.plugins.context import PluginContext


# =============================================================================
# Tests for RunResult dataclass defaults (lines 81-86)
# Mutations: changing default values (0 -> 1, 0 -> None, etc.)
# =============================================================================


class TestRunResultDefaults:
    """Verify RunResult dataclass has correct default values.

    These tests catch mutations that change default field values.

    P3 Fix: rows_routed is required (not defaulted), so we only test
    fields that actually have defaults (rows_quarantined through rows_buffered).
    """

    def test_rows_quarantined_defaults_to_zero(self) -> None:
        """Line 93: rows_quarantined must default to 0."""
        # Create RunResult WITHOUT rows_quarantined - should default to 0
        result = RunResult(
            run_id="test-run",
            status=RunStatus.COMPLETED,
            rows_processed=10,
            rows_succeeded=10,
            rows_failed=0,
            rows_routed=5,  # Required field, must provide
        )
        # rows_quarantined has a default - verify it's 0
        assert result.rows_quarantined == 0
        assert isinstance(result.rows_quarantined, int)

    def test_rows_forked_defaults_to_zero(self) -> None:
        """Line 94: rows_forked must default to 0."""
        result = RunResult(
            run_id="test-run",
            status=RunStatus.COMPLETED,
            rows_processed=10,
            rows_succeeded=10,
            rows_failed=0,
            rows_routed=5,
        )
        assert result.rows_forked == 0
        assert isinstance(result.rows_forked, int)

    def test_rows_coalesced_defaults_to_zero(self) -> None:
        """Line 95: rows_coalesced must default to 0."""
        result = RunResult(
            run_id="test-run",
            status=RunStatus.COMPLETED,
            rows_processed=10,
            rows_succeeded=10,
            rows_failed=0,
            rows_routed=5,
        )
        assert result.rows_coalesced == 0
        assert isinstance(result.rows_coalesced, int)

    def test_rows_expanded_defaults_to_zero(self) -> None:
        """Line 96: rows_expanded must default to 0."""
        result = RunResult(
            run_id="test-run",
            status=RunStatus.COMPLETED,
            rows_processed=10,
            rows_succeeded=10,
            rows_failed=0,
            rows_routed=5,
        )
        assert result.rows_expanded == 0
        assert isinstance(result.rows_expanded, int)

    def test_rows_buffered_defaults_to_zero(self) -> None:
        """Line 97: rows_buffered must default to 0."""
        result = RunResult(
            run_id="test-run",
            status=RunStatus.COMPLETED,
            rows_processed=10,
            rows_succeeded=10,
            rows_failed=0,
            rows_routed=5,
        )
        assert result.rows_buffered == 0
        assert isinstance(result.rows_buffered, int)

    def test_rows_routed_is_required(self) -> None:
        """P3 Fix: rows_routed has no default - verify it's required.

        Previous test was tautological (passed explicit 0). This test
        verifies the field is actually required by checking TypeError.
        """
        with pytest.raises(TypeError, match="rows_routed"):
            RunResult(  # type: ignore[call-arg]
                run_id="test-run",
                status=RunStatus.COMPLETED,
                rows_processed=10,
                rows_succeeded=10,
                rows_failed=0,
                # rows_routed omitted - should fail
            )


# =============================================================================
# Tests for PipelineConfig dataclass defaults (lines 67-68)
# Mutations: changing default_factory to wrong type
# =============================================================================


class TestPipelineConfigDefaults:
    """Verify PipelineConfig dataclass has correct default values."""

    @pytest.fixture
    def minimal_source(self) -> _TestSourceBase:
        """Create minimal source for PipelineConfig."""

        class MinimalSource(_TestSourceBase):
            name = "minimal_source"
            output_schema = _TestSchema

            def load(self, ctx: Any) -> Iterator[SourceRow]:
                yield SourceRow.valid({"x": 1})

        return MinimalSource()

    @pytest.fixture
    def minimal_sink(self) -> _TestSinkBase:
        """Create minimal sink for PipelineConfig."""

        class MinimalSink(_TestSinkBase):
            name = "minimal_sink"
            input_schema = _TestSchema

            def write_batch(self, rows: list[dict[str, Any]], ctx: Any) -> Any:
                pass

        return MinimalSink()

    def test_gates_defaults_to_empty_list(self, minimal_source: _TestSourceBase, minimal_sink: _TestSinkBase) -> None:
        """Line 67: gates must default to empty list, not dict or None."""
        config = PipelineConfig(
            source=as_source(minimal_source),
            transforms=[],
            sinks={"output": as_sink(minimal_sink)},
        )
        # If mutation changed default_factory=list to default_factory=dict, this fails
        assert config.gates == []
        assert isinstance(config.gates, list)

    def test_aggregation_settings_defaults_to_empty_dict(self, minimal_source: _TestSourceBase, minimal_sink: _TestSinkBase) -> None:
        """Line 68: aggregation_settings must default to empty dict."""
        config = PipelineConfig(
            source=as_source(minimal_source),
            transforms=[],
            sinks={"output": as_sink(minimal_sink)},
        )
        assert config.aggregation_settings == {}
        assert isinstance(config.aggregation_settings, dict)

    def test_coalesce_settings_defaults_to_empty_list(self, minimal_source: _TestSourceBase, minimal_sink: _TestSinkBase) -> None:
        """Line 69: coalesce_settings must default to empty list."""
        config = PipelineConfig(
            source=as_source(minimal_source),
            transforms=[],
            sinks={"output": as_sink(minimal_sink)},
        )
        assert config.coalesce_settings == []
        assert isinstance(config.coalesce_settings, list)


# =============================================================================
# Tests for route validation edge cases (lines 245, 249, 255-258)
# Mutations: changing "continue"/"fork" checks, error message content
# =============================================================================


class TestRouteValidationEdgeCases:
    """Test route validation handles special cases correctly."""

    @pytest.fixture
    def orchestrator(self) -> Any:
        """Create orchestrator with in-memory DB."""
        from elspeth.core.landscape import LandscapeDB
        from elspeth.engine.orchestrator import Orchestrator

        db = LandscapeDB.in_memory()
        return Orchestrator(db)

    def test_continue_destination_is_not_validated_as_sink(self, orchestrator: Any) -> None:
        """Line 245: 'continue' destination should skip sink validation."""
        # Route map with 'continue' destination
        route_resolution_map = {
            ("gate_1", "default"): "continue",  # Should be skipped
        }
        available_sinks = {"output"}  # 'continue' is not in sinks, but shouldn't error

        # Should not raise - 'continue' is special, not a sink name
        orchestrator._validate_route_destinations(
            route_resolution_map=route_resolution_map,
            available_sinks=available_sinks,
            transform_id_map={},
            transforms=[],
        )

    def test_fork_destination_is_not_validated_as_sink(self, orchestrator: Any) -> None:
        """Line 249: 'fork' destination should skip sink validation."""
        route_resolution_map = {
            ("gate_1", "split"): "fork",  # Should be skipped
        }
        available_sinks = {"output"}

        # Should not raise - 'fork' is special, not a sink name
        orchestrator._validate_route_destinations(
            route_resolution_map=route_resolution_map,
            available_sinks=available_sinks,
            transform_id_map={},
            transforms=[],
        )

    def test_invalid_sink_raises_with_helpful_message(self, orchestrator: Any) -> None:
        """Lines 255-258: Invalid sink destination raises RouteValidationError."""
        route_resolution_map = {
            ("gate_1", "error_route"): "nonexistent_sink",
        }
        available_sinks = {"output", "errors"}

        with pytest.raises(RouteValidationError) as exc_info:
            orchestrator._validate_route_destinations(
                route_resolution_map=route_resolution_map,
                available_sinks=available_sinks,
                transform_id_map={},
                transforms=[],
            )

        # Verify error message contains helpful information
        error_msg = str(exc_info.value)
        assert "nonexistent_sink" in error_msg
        assert "error_route" in error_msg
        assert "errors" in error_msg or "output" in error_msg  # Available sinks listed


# =============================================================================
# Tests for transform error sink validation (lines 290, 294, 299-302)
# Mutations: changing None checks, 'discard' check, error message
# =============================================================================


class TestTransformErrorSinkValidation:
    """Test transform on_error destination validation.

    These tests MUST use actual BaseTransform subclasses (not _TestTransformBase)
    because _validate_transform_error_sinks checks isinstance(transform, BaseTransform)
    before accessing _on_error. _TestTransformBase is protocol-based and skipped.
    """

    @pytest.fixture
    def orchestrator(self) -> Any:
        """Create orchestrator with in-memory DB."""
        from elspeth.core.landscape import LandscapeDB
        from elspeth.engine.orchestrator import Orchestrator

        db = LandscapeDB.in_memory()
        return Orchestrator(db)

    def test_transform_with_none_on_error_is_valid(self, orchestrator: Any) -> None:
        """Line 290: Transform with on_error=None should pass validation."""
        from elspeth.plugins.base import BaseTransform

        class TransformNoErrorRouting(BaseTransform):
            name = "no_error_routing"
            input_schema = _TestSchema
            output_schema = _TestSchema
            _on_error = None  # No error routing

            def process(self, row: dict[str, Any], ctx: PluginContext) -> TransformResult:
                from elspeth.contracts.results import TransformResult

                return TransformResult.success(row)

        transforms = [TransformNoErrorRouting(config={})]
        available_sinks = {"output"}

        # Should not raise
        orchestrator._validate_transform_error_sinks(
            transforms=transforms,
            available_sinks=available_sinks,
            _transform_id_map={0: "transform_0"},
        )

    def test_transform_with_discard_on_error_is_valid(self, orchestrator: Any) -> None:
        """Line 294: Transform with on_error='discard' should pass validation."""
        from elspeth.plugins.base import BaseTransform

        class TransformDiscardErrors(BaseTransform):
            name = "discard_errors"
            input_schema = _TestSchema
            output_schema = _TestSchema
            _on_error = "discard"  # Special value, not a sink

            def process(self, row: dict[str, Any], ctx: PluginContext) -> TransformResult:
                from elspeth.contracts.results import TransformResult

                return TransformResult.success(row)

        transforms = [TransformDiscardErrors(config={})]
        available_sinks = {"output"}  # 'discard' not in sinks, but shouldn't error

        # Should not raise
        orchestrator._validate_transform_error_sinks(
            transforms=transforms,
            available_sinks=available_sinks,
            _transform_id_map={0: "transform_0"},
        )

    def test_transform_with_invalid_on_error_raises(self, orchestrator: Any) -> None:
        """Lines 299-302: Invalid on_error sink raises RouteValidationError."""
        from elspeth.plugins.base import BaseTransform

        class TransformBadErrorSink(BaseTransform):
            name = "bad_error_sink"
            input_schema = _TestSchema
            output_schema = _TestSchema
            _on_error = "nonexistent_error_sink"

            def process(self, row: dict[str, Any], ctx: PluginContext) -> TransformResult:
                from elspeth.contracts.results import TransformResult

                return TransformResult.success(row)

        transforms = [TransformBadErrorSink(config={})]
        available_sinks = {"output", "errors"}

        with pytest.raises(RouteValidationError) as exc_info:
            orchestrator._validate_transform_error_sinks(
                transforms=transforms,
                available_sinks=available_sinks,
                _transform_id_map={0: "transform_0"},
            )

        error_msg = str(exc_info.value)
        assert "bad_error_sink" in error_msg
        assert "nonexistent_error_sink" in error_msg
        assert "discard" in error_msg  # Suggests using discard


# =============================================================================
# Tests for source quarantine validation (lines 337, 344-347)
# Mutations: changing 'discard' check, error message content
# =============================================================================


class TestSourceQuarantineValidation:
    """Test source on_validation_failure destination validation."""

    @pytest.fixture
    def orchestrator(self) -> Any:
        """Create orchestrator with in-memory DB."""
        from elspeth.core.landscape import LandscapeDB
        from elspeth.engine.orchestrator import Orchestrator

        db = LandscapeDB.in_memory()
        return Orchestrator(db)

    def test_source_with_discard_quarantine_is_valid(self, orchestrator: Any) -> None:
        """Line 337: Source with on_validation_failure='discard' should pass."""

        class SourceDiscardInvalid(_TestSourceBase):
            name = "discard_invalid"
            output_schema = _TestSchema
            _on_validation_failure = "discard"

            def load(self, ctx: Any) -> Iterator[SourceRow]:
                yield SourceRow.valid({"x": 1})

        source = SourceDiscardInvalid()
        available_sinks = {"output"}

        # Should not raise
        orchestrator._validate_source_quarantine_destination(
            source=as_source(source),
            available_sinks=available_sinks,
        )

    def test_source_with_invalid_quarantine_raises(self, orchestrator: Any) -> None:
        """Lines 344-347: Invalid quarantine sink raises RouteValidationError."""

        class SourceBadQuarantine(_TestSourceBase):
            name = "bad_quarantine"
            output_schema = _TestSchema
            _on_validation_failure = "nonexistent_quarantine"

            def load(self, ctx: Any) -> Iterator[SourceRow]:
                yield SourceRow.valid({"x": 1})

        source = SourceBadQuarantine()
        available_sinks = {"output", "errors"}

        with pytest.raises(RouteValidationError) as exc_info:
            orchestrator._validate_source_quarantine_destination(
                source=as_source(source),
                available_sinks=available_sinks,
            )

        error_msg = str(exc_info.value)
        assert "bad_quarantine" in error_msg
        assert "nonexistent_quarantine" in error_msg
        assert "discard" in error_msg  # Suggests using discard


# =============================================================================
# Tests for node type metadata (lines 590, 595-596, 599)
# Mutations: changing determinism values, plugin_version
#
# P1 Fix: Previous tests were tautological - just asserted enum constants.
# New tests run orchestrator and query audit database to verify node metadata.
# =============================================================================


class TestNodeTypeMetadata:
    """Test that different node types get correct metadata in audit trail.

    P1 Fix: Actually run orchestrator and query LandscapeRecorder.get_nodes()
    to verify determinism and plugin_version are recorded correctly.
    """

    def test_config_gate_recorded_as_deterministic(self, plugin_manager) -> None:
        """Config gates should be recorded as DETERMINISTIC in audit trail."""
        from elspeth.cli_helpers import instantiate_plugins_from_config
        from elspeth.core.config import (
            DatasourceSettings,
            ElspethSettings,
            GateSettings,
            SinkSettings,
        )
        from elspeth.core.dag import ExecutionGraph
        from elspeth.core.landscape import LandscapeDB
        from elspeth.core.landscape.recorder import LandscapeRecorder
        from elspeth.engine.orchestrator import Orchestrator, PipelineConfig

        db = LandscapeDB.in_memory()

        # Create settings with a config gate
        settings = ElspethSettings(
            datasource=DatasourceSettings(
                plugin="null",
                options={"schema": {"fields": "dynamic"}},
            ),
            sinks={
                "high": SinkSettings(plugin="csv", options={"path": "high.csv", "schema": {"fields": "dynamic"}}),
                "low": SinkSettings(plugin="csv", options={"path": "low.csv", "schema": {"fields": "dynamic"}}),
            },
            output_sink="low",
            gates=[
                GateSettings(
                    name="priority_gate",
                    condition="True",  # Always route to high
                    routes={"true": "high", "false": "low"},  # Boolean routes use lowercase
                ),
            ],
        )

        plugins = instantiate_plugins_from_config(settings)
        graph = ExecutionGraph.from_plugin_instances(
            source=plugins["source"],
            transforms=plugins["transforms"],
            sinks=plugins["sinks"],
            aggregations=plugins["aggregations"],
            gates=list(settings.gates),
            output_sink=settings.output_sink,
        )

        config = PipelineConfig(
            source=plugins["source"],
            transforms=[],
            sinks=plugins["sinks"],
            gates=list(settings.gates),
        )

        orchestrator = Orchestrator(db)
        result = orchestrator.run(config, graph)
        assert result.status == RunStatus.COMPLETED

        # P1 Fix: Query audit trail and verify config gate metadata
        recorder = LandscapeRecorder(db)
        nodes = recorder.get_nodes(result.run_id)

        # Find the config gate node
        gate_nodes = [n for n in nodes if n.node_type.value == "gate"]
        assert len(gate_nodes) == 1, f"Expected 1 gate node, found {len(gate_nodes)}"

        gate_node = gate_nodes[0]
        assert gate_node.determinism == Determinism.DETERMINISTIC, f"Config gate should be DETERMINISTIC, got {gate_node.determinism}"
        assert gate_node.plugin_version is not None, "Gate should have plugin_version recorded"


# =============================================================================
# Tests for checkpoint logic (lines 151, 153)
# Mutations: removing sequence_number increment
# =============================================================================


class TestCheckpointSequencing:
    """Test checkpoint sequence number is properly incremented."""

    def test_sequence_number_increments_on_checkpoint(self) -> None:
        """Lines 151-153: sequence_number must increment for each checkpoint.

        Uses frequency="aggregation_only" so _maybe_checkpoint increments
        the counter without attempting DB insert (avoids FK constraint on run_id).
        The increment at line 152 happens unconditionally when checkpointing is enabled.
        """
        from elspeth.contracts import RoutingMode
        from elspeth.core.checkpoint import CheckpointManager
        from elspeth.core.config import CheckpointSettings
        from elspeth.core.dag import ExecutionGraph
        from elspeth.core.landscape import LandscapeDB
        from elspeth.engine.orchestrator import Orchestrator

        db = LandscapeDB.in_memory()
        checkpoint_manager = CheckpointManager(db)
        # Use aggregation_only: increments counter but doesn't create checkpoint record
        checkpoint_settings = CheckpointSettings(enabled=True, frequency="aggregation_only")

        orchestrator = Orchestrator(
            db,
            checkpoint_manager=checkpoint_manager,
            checkpoint_settings=checkpoint_settings,
        )

        # Build graph matching the nodes used in _maybe_checkpoint calls
        graph = ExecutionGraph()
        graph.add_node("source-1", node_type="source", plugin_name="null", config={})
        graph.add_node("sink-1", node_type="sink", plugin_name="csv", config={})
        graph.add_edge("source-1", "sink-1", label="continue", mode=RoutingMode.MOVE)

        # Set the graph on the orchestrator (normally done in execute())
        orchestrator._current_graph = graph

        # Initial sequence number
        assert orchestrator._sequence_number == 0

        # Calling _maybe_checkpoint should increment sequence_number
        # With aggregation_only, it increments but doesn't hit the DB
        orchestrator._maybe_checkpoint(
            run_id="test-run",
            token_id="token-1",
            node_id="sink-1",
        )

        # Sequence number should have incremented
        assert orchestrator._sequence_number == 1

        # Call again
        orchestrator._maybe_checkpoint(
            run_id="test-run",
            token_id="token-2",
            node_id="sink-1",
        )

        assert orchestrator._sequence_number == 2

    def test_sequence_number_not_incremented_when_disabled(self) -> None:
        """Lines 147-148: sequence_number should NOT increment when disabled."""
        from elspeth.core.config import CheckpointSettings
        from elspeth.core.landscape import LandscapeDB
        from elspeth.engine.orchestrator import Orchestrator

        db = LandscapeDB.in_memory()
        checkpoint_settings = CheckpointSettings(enabled=False)

        orchestrator = Orchestrator(
            db,
            checkpoint_settings=checkpoint_settings,
        )

        assert orchestrator._sequence_number == 0

        orchestrator._maybe_checkpoint(
            run_id="test-run",
            token_id="token-1",
            node_id="sink-1",
        )

        # Should NOT have incremented when checkpointing is disabled
        assert orchestrator._sequence_number == 0

    def test_sequence_number_not_incremented_without_manager(self) -> None:
        """Lines 149-150: sequence_number should NOT increment without manager."""
        from elspeth.core.config import CheckpointSettings
        from elspeth.core.landscape import LandscapeDB
        from elspeth.engine.orchestrator import Orchestrator

        db = LandscapeDB.in_memory()
        # No checkpoint_manager provided
        checkpoint_settings = CheckpointSettings(enabled=True, frequency="aggregation_only")

        orchestrator = Orchestrator(
            db,
            checkpoint_settings=checkpoint_settings,
            # checkpoint_manager deliberately omitted
        )

        assert orchestrator._sequence_number == 0

        orchestrator._maybe_checkpoint(
            run_id="test-run",
            token_id="token-1",
            node_id="sink-1",
        )

        # Should NOT have incremented without a checkpoint manager
        assert orchestrator._sequence_number == 0
