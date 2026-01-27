# tests/engine/test_orchestrator_fork_coalesce.py
"""Tests for Orchestrator fork and coalesce functionality.

All test plugins inherit from base classes (BaseTransform, BaseGate)
because the processor uses isinstance() for type-safe plugin detection.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

from elspeth.cli_helpers import instantiate_plugins_from_config
from elspeth.contracts import SourceRow
from elspeth.plugins.base import BaseTransform
from tests.conftest import (
    _TestSchema,
    _TestSinkBase,
    _TestSourceBase,
    as_sink,
    as_source,
    as_transform,
)
from tests.engine.orchestrator_test_helpers import build_test_graph

if TYPE_CHECKING:
    from elspeth.contracts.results import TransformResult


class TestOrchestratorForkExecution:
    """Test orchestrator handles fork results correctly.

    NOTE: Full fork testing at orchestrator level is blocked by ExecutionGraph
    using DiGraph instead of MultiDiGraph (can't store multiple edges between
    same nodes). See WP-07 notes. Fork logic is tested at processor level in
    test_processor.py::TestRowProcessorWorkQueue.
    """

    def test_orchestrator_handles_list_results_from_processor(self) -> None:
        """Orchestrator correctly iterates over list[RowResult] from processor.

        This tests the basic plumbing (list handling, counting) without forks.
        Fork-specific behavior is tested at processor level.
        """
        import hashlib

        from elspeth.core.landscape import LandscapeDB
        from elspeth.engine.artifacts import ArtifactDescriptor
        from elspeth.engine.orchestrator import Orchestrator, PipelineConfig
        from elspeth.plugins.results import TransformResult

        db = LandscapeDB.in_memory()

        class RowSchema(_TestSchema):
            value: int

        class ListSource(_TestSourceBase):
            name = "list_source"
            output_schema = RowSchema

            def on_start(self, ctx: Any) -> None:
                pass

            def on_complete(self, ctx: Any) -> None:
                pass

            def load(self, ctx: Any) -> Iterator[SourceRow]:
                yield SourceRow.valid({"value": 1})
                yield SourceRow.valid({"value": 2})
                yield SourceRow.valid({"value": 3})

            def close(self) -> None:
                pass

        class PassthroughTransform(BaseTransform):
            name = "passthrough"
            input_schema = RowSchema
            output_schema = RowSchema

            def __init__(self) -> None:
                super().__init__({"schema": {"fields": "dynamic"}})

            def process(self, row: Any, ctx: Any) -> TransformResult:
                return TransformResult.success(row)

        class CollectSink(_TestSinkBase):
            name = "collect_sink"

            def __init__(self) -> None:
                self.results: list[Any] = []

            def on_start(self, ctx: Any) -> None:
                pass

            def on_complete(self, ctx: Any) -> None:
                pass

            def write(self, rows: Any, ctx: Any) -> ArtifactDescriptor:
                self.results.extend(rows)
                content = str(rows).encode()
                return ArtifactDescriptor(
                    artifact_type="file",
                    path_or_uri="memory://test",
                    content_hash=hashlib.sha256(content).hexdigest(),
                    size_bytes=len(content),
                )

            def close(self) -> None:
                pass

        source = ListSource()
        transform = PassthroughTransform()
        sink = CollectSink()

        config = PipelineConfig(
            source=as_source(source),
            transforms=[as_transform(transform)],
            sinks={"default": as_sink(sink)},
        )

        graph = build_test_graph(config)

        orchestrator = Orchestrator(db)
        run_result = orchestrator.run(config, graph=graph)

        assert run_result.status == "completed"
        # 3 rows from source
        assert run_result.rows_processed == 3
        # All 3 reach COMPLETED (no forks)
        assert run_result.rows_succeeded == 3
        # All 3 written to sink
        assert len(sink.results) == 3


class TestCoalesceWiring:
    """Test that coalesce is wired into orchestrator."""

    def test_orchestrator_creates_coalesce_executor_when_config_present(
        self,
        plugin_manager,
    ) -> None:
        """When settings.coalesce is non-empty, CoalesceExecutor should be created."""
        from unittest.mock import MagicMock, patch

        from elspeth.core.config import (
            CoalesceSettings,
            ElspethSettings,
            GateSettings,
            SinkSettings,
            SourceSettings,
        )
        from elspeth.core.dag import ExecutionGraph
        from elspeth.core.landscape import LandscapeDB
        from elspeth.engine.orchestrator import Orchestrator, PipelineConfig

        settings = ElspethSettings(
            source=SourceSettings(
                plugin="csv",
                options={
                    "path": "test.csv",
                    "on_validation_failure": "discard",
                    "schema": {"fields": "dynamic"},
                },
            ),
            sinks={"output": SinkSettings(plugin="csv", options={"path": "out.csv", "schema": {"fields": "dynamic"}})},
            default_sink="output",
            gates=[
                GateSettings(
                    name="forker",
                    condition="True",
                    routes={"true": "fork", "false": "continue"},
                    fork_to=["path_a", "path_b"],
                ),
            ],
            coalesce=[
                CoalesceSettings(
                    name="merge_results",
                    branches=["path_a", "path_b"],
                    policy="require_all",
                    merge="union",
                ),
            ],
        )

        # Mock source/sink to avoid file access
        mock_source = MagicMock()
        mock_source.name = "csv"
        mock_source._on_validation_failure = "discard"
        mock_source.load.return_value = iter([])
        mock_source.plugin_version = "1.0.0"
        schema_mock = MagicMock()

        schema_mock.model_json_schema.return_value = {"type": "object"}

        mock_source.output_schema = schema_mock
        mock_source.determinism = "deterministic"
        mock_source.output_schema = _TestSchema

        mock_sink = MagicMock()
        mock_sink.name = "csv"
        mock_sink.plugin_version = "1.0.0"
        schema_mock = MagicMock()

        schema_mock.model_json_schema.return_value = {"type": "object"}

        mock_sink.input_schema = schema_mock
        mock_sink.determinism = "deterministic"
        mock_sink.input_schema = _TestSchema

        config = PipelineConfig(
            source=mock_source,
            transforms=[],
            sinks={"output": mock_sink},
            gates=settings.gates,
        )

        db = LandscapeDB.in_memory()
        orchestrator = Orchestrator(db=db)

        # Build the graph from settings (which includes coalesce)
        plugins = instantiate_plugins_from_config(settings)

        graph = ExecutionGraph.from_plugin_instances(
            source=plugins["source"],
            transforms=plugins["transforms"],
            sinks=plugins["sinks"],
            aggregations=plugins["aggregations"],
            gates=list(settings.gates),
            default_sink=settings.default_sink,
            coalesce_settings=settings.coalesce,
        )

        # Patch RowProcessor to capture its args
        with patch("elspeth.engine.orchestrator.RowProcessor") as mock_processor:
            mock_processor.return_value.process_row.return_value = []
            mock_processor.return_value.token_manager = MagicMock()

            orchestrator.run(config, graph=graph, settings=settings)

            # RowProcessor should have been called with coalesce_executor
            call_kwargs = mock_processor.call_args.kwargs
            assert "coalesce_executor" in call_kwargs
            assert call_kwargs["coalesce_executor"] is not None
            assert "coalesce_node_ids" in call_kwargs
            assert call_kwargs["coalesce_node_ids"] is not None
            # Verify the coalesce_node_ids contains our registered coalesce
            assert "merge_results" in call_kwargs["coalesce_node_ids"]

    def test_orchestrator_handles_coalesced_outcome(self, plugin_manager) -> None:
        """COALESCED outcome should route merged token to output sink."""
        from unittest.mock import MagicMock, patch

        from elspeth.contracts import RowOutcome, TokenInfo
        from elspeth.contracts.results import RowResult
        from elspeth.core.config import (
            CoalesceSettings,
            ElspethSettings,
            GateSettings,
            SinkSettings,
            SourceSettings,
        )
        from elspeth.core.dag import ExecutionGraph
        from elspeth.core.landscape import LandscapeDB
        from elspeth.engine.artifacts import ArtifactDescriptor
        from elspeth.engine.orchestrator import Orchestrator, PipelineConfig

        db = LandscapeDB.in_memory()

        mock_source = MagicMock()
        mock_source.name = "csv"
        mock_source._on_validation_failure = "discard"
        mock_source.load.return_value = iter([MagicMock(is_quarantined=False, row={"value": 1})])
        mock_source.plugin_version = "1.0.0"
        schema_mock = MagicMock()

        schema_mock.model_json_schema.return_value = {"type": "object"}

        mock_source.output_schema = schema_mock
        mock_source.determinism = "deterministic"
        mock_source.output_schema = _TestSchema

        mock_sink = MagicMock()
        mock_sink.name = "csv"
        mock_sink.plugin_version = "1.0.0"
        schema_mock = MagicMock()

        schema_mock.model_json_schema.return_value = {"type": "object"}

        mock_sink.input_schema = schema_mock
        mock_sink.determinism = "deterministic"
        mock_sink.input_schema = _TestSchema
        mock_sink.write.return_value = ArtifactDescriptor.for_file(path="memory", size_bytes=0, content_hash="abc123")

        # Settings with coalesce (needed to enable coalesce path in orchestrator)
        settings = ElspethSettings(
            source=SourceSettings(
                plugin="csv",
                options={
                    "path": "test.csv",
                    "on_validation_failure": "discard",
                    "schema": {"fields": "dynamic"},
                },
            ),
            sinks={"output": SinkSettings(plugin="csv", options={"path": "out.csv", "schema": {"fields": "dynamic"}})},
            default_sink="output",
            gates=[
                GateSettings(
                    name="forker",
                    condition="True",
                    routes={"true": "fork", "false": "continue"},
                    fork_to=["path_a", "path_b"],
                ),
            ],
            coalesce=[
                CoalesceSettings(
                    name="merge_results",
                    branches=["path_a", "path_b"],
                    policy="require_all",
                    merge="union",
                ),
            ],
        )

        config = PipelineConfig(
            source=mock_source,
            transforms=[],
            sinks={"output": mock_sink},
            gates=settings.gates,
        )

        plugins = instantiate_plugins_from_config(settings)

        graph = ExecutionGraph.from_plugin_instances(
            source=plugins["source"],
            transforms=plugins["transforms"],
            sinks=plugins["sinks"],
            aggregations=plugins["aggregations"],
            gates=list(settings.gates),
            default_sink=settings.default_sink,
            coalesce_settings=settings.coalesce,
        )

        orchestrator = Orchestrator(db=db)

        # Mock RowProcessor to return COALESCED outcome
        merged_token = TokenInfo(
            row_id="row_1",
            token_id="merged_token_1",
            row_data={"merged": True},
            branch_name=None,
        )
        coalesced_result = RowResult(
            token=merged_token,
            final_data={"merged": True},
            outcome=RowOutcome.COALESCED,
        )

        with (
            patch("elspeth.engine.orchestrator.RowProcessor") as mock_processor_cls,
            patch("elspeth.engine.executors.SinkExecutor") as mock_sink_executor_cls,
        ):
            mock_processor = MagicMock()
            mock_processor.process_row.return_value = [coalesced_result]
            mock_processor.token_manager.create_initial_token.return_value = MagicMock(row_id="row_1", token_id="t1", row_data={"value": 1})
            mock_processor_cls.return_value = mock_processor

            # Mock SinkExecutor to avoid foreign key constraint errors
            mock_sink_executor = MagicMock()
            mock_sink_executor_cls.return_value = mock_sink_executor

            result = orchestrator.run(config, graph=graph, settings=settings)

            # COALESCED should count toward rows_coalesced
            assert result.rows_coalesced == 1

            # Verify the merged token was added to pending_tokens and passed to sink
            # SinkExecutor.write should have been called with the merged token
            assert mock_sink_executor.write.called
            write_call = mock_sink_executor.write.call_args
            tokens_written = write_call.kwargs.get("tokens") or write_call.args[1]
            assert len(tokens_written) == 1
            assert tokens_written[0].token_id == "merged_token_1"

    def test_orchestrator_calls_flush_pending_at_end(self, plugin_manager) -> None:
        """flush_pending should be called on coalesce executor at end of source."""
        from unittest.mock import MagicMock, patch

        from elspeth.core.config import (
            CoalesceSettings,
            ElspethSettings,
            GateSettings,
            SinkSettings,
            SourceSettings,
        )
        from elspeth.core.dag import ExecutionGraph
        from elspeth.core.landscape import LandscapeDB
        from elspeth.engine.orchestrator import Orchestrator, PipelineConfig

        settings = ElspethSettings(
            source=SourceSettings(
                plugin="csv",
                options={
                    "path": "test.csv",
                    "on_validation_failure": "discard",
                    "schema": {"fields": "dynamic"},
                },
            ),
            sinks={"output": SinkSettings(plugin="csv", options={"path": "out.csv", "schema": {"fields": "dynamic"}})},
            default_sink="output",
            gates=[
                GateSettings(
                    name="forker",
                    condition="True",
                    routes={"true": "fork", "false": "continue"},
                    fork_to=["path_a", "path_b"],
                ),
            ],
            coalesce=[
                CoalesceSettings(
                    name="merge_results",
                    branches=["path_a", "path_b"],
                    policy="require_all",
                    merge="union",
                ),
            ],
        )

        mock_source = MagicMock()
        mock_source.name = "csv"
        mock_source._on_validation_failure = "discard"
        mock_source.load.return_value = iter([])  # Empty - immediate end
        mock_source.plugin_version = "1.0.0"
        schema_mock = MagicMock()

        schema_mock.model_json_schema.return_value = {"type": "object"}

        mock_source.output_schema = schema_mock
        mock_source.determinism = "deterministic"
        mock_source.output_schema = _TestSchema

        mock_sink = MagicMock()
        mock_sink.name = "csv"
        mock_sink.plugin_version = "1.0.0"
        schema_mock = MagicMock()

        schema_mock.model_json_schema.return_value = {"type": "object"}

        mock_sink.input_schema = schema_mock
        mock_sink.determinism = "deterministic"
        mock_sink.input_schema = _TestSchema

        config = PipelineConfig(
            source=mock_source,
            transforms=[],
            sinks={"output": mock_sink},
            gates=settings.gates,
        )

        db = LandscapeDB.in_memory()
        orchestrator = Orchestrator(db=db)
        plugins = instantiate_plugins_from_config(settings)

        graph = ExecutionGraph.from_plugin_instances(
            source=plugins["source"],
            transforms=plugins["transforms"],
            sinks=plugins["sinks"],
            aggregations=plugins["aggregations"],
            gates=list(settings.gates),
            default_sink=settings.default_sink,
            coalesce_settings=settings.coalesce,
        )

        with patch("elspeth.engine.coalesce_executor.CoalesceExecutor") as mock_executor_cls:
            mock_executor = MagicMock()
            mock_executor.flush_pending.return_value = []
            mock_executor_cls.return_value = mock_executor

            orchestrator.run(config, graph=graph, settings=settings)

            # flush_pending should have been called
            mock_executor.flush_pending.assert_called_once()

    def test_orchestrator_flush_pending_routes_merged_tokens_to_sink(self, plugin_manager) -> None:
        """Merged tokens from flush_pending should be routed to output sink."""
        from unittest.mock import MagicMock, patch

        from elspeth.contracts import TokenInfo
        from elspeth.core.config import (
            CoalesceSettings,
            ElspethSettings,
            GateSettings,
            SinkSettings,
            SourceSettings,
        )
        from elspeth.core.dag import ExecutionGraph
        from elspeth.core.landscape import LandscapeDB
        from elspeth.engine.artifacts import ArtifactDescriptor
        from elspeth.engine.coalesce_executor import CoalesceOutcome
        from elspeth.engine.orchestrator import Orchestrator, PipelineConfig

        settings = ElspethSettings(
            source=SourceSettings(
                plugin="csv",
                options={
                    "path": "test.csv",
                    "on_validation_failure": "discard",
                    "schema": {"fields": "dynamic"},
                },
            ),
            sinks={"output": SinkSettings(plugin="csv", options={"path": "out.csv", "schema": {"fields": "dynamic"}})},
            default_sink="output",
            gates=[
                GateSettings(
                    name="forker",
                    condition="True",
                    routes={"true": "fork", "false": "continue"},
                    fork_to=["path_a", "path_b"],
                ),
            ],
            coalesce=[
                CoalesceSettings(
                    name="merge_results",
                    branches=["path_a", "path_b"],
                    policy="best_effort",  # best_effort merges whatever arrived
                    merge="union",
                    timeout_seconds=10.0,  # Required for best_effort
                ),
            ],
        )

        mock_source = MagicMock()
        mock_source.name = "csv"
        mock_source._on_validation_failure = "discard"
        mock_source.load.return_value = iter([])  # Empty - immediate end
        mock_source.plugin_version = "1.0.0"
        schema_mock = MagicMock()

        schema_mock.model_json_schema.return_value = {"type": "object"}

        mock_source.output_schema = schema_mock
        mock_source.determinism = "deterministic"
        mock_source.output_schema = _TestSchema

        mock_sink = MagicMock()
        mock_sink.name = "csv"
        mock_sink.plugin_version = "1.0.0"
        schema_mock = MagicMock()

        schema_mock.model_json_schema.return_value = {"type": "object"}

        mock_sink.input_schema = schema_mock
        mock_sink.determinism = "deterministic"
        mock_sink.input_schema = _TestSchema
        mock_sink.write.return_value = ArtifactDescriptor.for_file(path="memory", size_bytes=0, content_hash="abc123")

        config = PipelineConfig(
            source=mock_source,
            transforms=[],
            sinks={"output": mock_sink},
            gates=settings.gates,
        )

        db = LandscapeDB.in_memory()
        orchestrator = Orchestrator(db=db)
        plugins = instantiate_plugins_from_config(settings)

        graph = ExecutionGraph.from_plugin_instances(
            source=plugins["source"],
            transforms=plugins["transforms"],
            sinks=plugins["sinks"],
            aggregations=plugins["aggregations"],
            gates=list(settings.gates),
            default_sink=settings.default_sink,
            coalesce_settings=settings.coalesce,
        )

        # Create a merged token that flush_pending will return
        merged_token = TokenInfo(
            row_id="row_1",
            token_id="flushed_merged_token",
            row_data={"merged_at_flush": True},
            branch_name=None,
        )

        with (
            patch("elspeth.engine.coalesce_executor.CoalesceExecutor") as mock_executor_cls,
            patch("elspeth.engine.executors.SinkExecutor") as mock_sink_executor_cls,
        ):
            mock_executor = MagicMock()
            # flush_pending returns a merged token
            mock_executor.flush_pending.return_value = [
                CoalesceOutcome(
                    held=False,
                    merged_token=merged_token,
                    consumed_tokens=[],
                    coalesce_metadata={"policy": "best_effort"},
                )
            ]
            mock_executor_cls.return_value = mock_executor

            mock_sink_executor = MagicMock()
            mock_sink_executor_cls.return_value = mock_sink_executor

            result = orchestrator.run(config, graph=graph, settings=settings)

            # flush_pending should have been called
            mock_executor.flush_pending.assert_called_once()

            # The merged token from flush should count toward rows_coalesced
            assert result.rows_coalesced == 1

            # The merged token should be written to the sink
            assert mock_sink_executor.write.called
            write_call = mock_sink_executor.write.call_args
            tokens_written = write_call.kwargs.get("tokens") or write_call.args[1]
            assert len(tokens_written) == 1
            assert tokens_written[0].token_id == "flushed_merged_token"

    def test_orchestrator_flush_pending_handles_failures(self, plugin_manager) -> None:
        """Failed coalesce outcomes from flush_pending should not crash."""
        from unittest.mock import MagicMock, patch

        from elspeth.core.config import (
            CoalesceSettings,
            ElspethSettings,
            GateSettings,
            SinkSettings,
            SourceSettings,
        )
        from elspeth.core.dag import ExecutionGraph
        from elspeth.core.landscape import LandscapeDB
        from elspeth.engine.coalesce_executor import CoalesceOutcome
        from elspeth.engine.orchestrator import Orchestrator, PipelineConfig

        settings = ElspethSettings(
            source=SourceSettings(
                plugin="csv",
                options={
                    "path": "test.csv",
                    "on_validation_failure": "discard",
                    "schema": {"fields": "dynamic"},
                },
            ),
            sinks={"output": SinkSettings(plugin="csv", options={"path": "out.csv", "schema": {"fields": "dynamic"}})},
            default_sink="output",
            gates=[
                GateSettings(
                    name="forker",
                    condition="True",
                    routes={"true": "fork", "false": "continue"},
                    fork_to=["path_a", "path_b"],
                ),
            ],
            coalesce=[
                CoalesceSettings(
                    name="merge_results",
                    branches=["path_a", "path_b"],
                    policy="require_all",  # Will fail if not all branches arrive
                    merge="union",
                ),
            ],
        )

        mock_source = MagicMock()
        mock_source.name = "csv"
        mock_source._on_validation_failure = "discard"
        mock_source.load.return_value = iter([])  # Empty - immediate end
        mock_source.plugin_version = "1.0.0"
        schema_mock = MagicMock()

        schema_mock.model_json_schema.return_value = {"type": "object"}

        mock_source.output_schema = schema_mock
        mock_source.determinism = "deterministic"
        mock_source.output_schema = _TestSchema

        mock_sink = MagicMock()
        mock_sink.name = "csv"
        mock_sink.plugin_version = "1.0.0"
        schema_mock = MagicMock()

        schema_mock.model_json_schema.return_value = {"type": "object"}

        mock_sink.input_schema = schema_mock
        mock_sink.determinism = "deterministic"
        mock_sink.input_schema = _TestSchema

        config = PipelineConfig(
            source=mock_source,
            transforms=[],
            sinks={"output": mock_sink},
            gates=settings.gates,
        )

        db = LandscapeDB.in_memory()
        orchestrator = Orchestrator(db=db)
        plugins = instantiate_plugins_from_config(settings)

        graph = ExecutionGraph.from_plugin_instances(
            source=plugins["source"],
            transforms=plugins["transforms"],
            sinks=plugins["sinks"],
            aggregations=plugins["aggregations"],
            gates=list(settings.gates),
            default_sink=settings.default_sink,
            coalesce_settings=settings.coalesce,
        )

        with patch("elspeth.engine.coalesce_executor.CoalesceExecutor") as mock_executor_cls:
            mock_executor = MagicMock()
            # flush_pending returns a failure outcome (incomplete branches)
            mock_executor.flush_pending.return_value = [
                CoalesceOutcome(
                    held=False,
                    merged_token=None,  # No merged token on failure
                    failure_reason="incomplete_branches",
                    coalesce_metadata={
                        "policy": "require_all",
                        "expected_branches": ["path_a", "path_b"],
                        "branches_arrived": ["path_a"],
                    },
                )
            ]
            mock_executor_cls.return_value = mock_executor

            # Should not raise - failures are recorded but don't crash
            result = orchestrator.run(config, graph=graph, settings=settings)

            # flush_pending should have been called
            mock_executor.flush_pending.assert_called_once()

            # No merged tokens means no rows_coalesced increment
            assert result.rows_coalesced == 0

    def test_orchestrator_computes_coalesce_step_map(self, plugin_manager) -> None:
        """Orchestrator should compute step positions for each coalesce point."""
        from unittest.mock import MagicMock, patch

        from elspeth.core.config import (
            CoalesceSettings,
            ElspethSettings,
            GateSettings,
            SinkSettings,
            SourceSettings,
            TransformSettings,
        )
        from elspeth.core.dag import ExecutionGraph
        from elspeth.core.landscape import LandscapeDB
        from elspeth.engine.orchestrator import Orchestrator, PipelineConfig

        settings = ElspethSettings(
            source=SourceSettings(
                plugin="csv",
                options={
                    "path": "test.csv",
                    "on_validation_failure": "discard",
                    "schema": {"fields": "dynamic"},
                },
            ),
            sinks={"output": SinkSettings(plugin="csv", options={"path": "out.csv", "schema": {"fields": "dynamic"}})},
            default_sink="output",
            transforms=[
                TransformSettings(plugin="passthrough", options={"schema": {"fields": "dynamic"}}),  # Step 0
                TransformSettings(plugin="passthrough", options={"schema": {"fields": "dynamic"}}),  # Step 1
            ],
            gates=[
                GateSettings(
                    name="forker",  # Step 2
                    condition="True",
                    routes={"true": "fork", "false": "continue"},
                    fork_to=["path_a", "path_b"],
                ),
            ],
            coalesce=[
                CoalesceSettings(
                    name="merge_results",  # Step 3
                    branches=["path_a", "path_b"],
                    policy="require_all",
                    merge="union",
                ),
            ],
        )

        mock_source = MagicMock()
        mock_source.name = "csv"
        mock_source._on_validation_failure = "discard"
        mock_source.load.return_value = iter([])
        mock_source.plugin_version = "1.0.0"
        schema_mock = MagicMock()

        schema_mock.model_json_schema.return_value = {"type": "object"}

        mock_source.output_schema = schema_mock
        mock_source.determinism = "deterministic"
        mock_source.output_schema = _TestSchema

        mock_sink = MagicMock()
        mock_sink.name = "csv"
        mock_sink.plugin_version = "1.0.0"
        schema_mock = MagicMock()

        schema_mock.model_json_schema.return_value = {"type": "object"}

        mock_sink.input_schema = schema_mock
        mock_sink.determinism = "deterministic"
        mock_sink.input_schema = _TestSchema

        mock_transform = MagicMock()
        mock_transform.name = "passthrough"
        mock_transform.plugin_version = "1.0.0"
        mock_transform.determinism = "deterministic"
        mock_transform.is_batch_aware = False

        config = PipelineConfig(
            source=mock_source,
            transforms=[mock_transform, mock_transform],
            sinks={"output": mock_sink},
            gates=settings.gates,
        )

        db = LandscapeDB.in_memory()
        orchestrator = Orchestrator(db=db)

        # Build the graph from settings (which includes coalesce)
        plugins = instantiate_plugins_from_config(settings)

        graph = ExecutionGraph.from_plugin_instances(
            source=plugins["source"],
            transforms=plugins["transforms"],
            sinks=plugins["sinks"],
            aggregations=plugins["aggregations"],
            gates=list(settings.gates),
            default_sink=settings.default_sink,
            coalesce_settings=settings.coalesce,
        )

        with patch("elspeth.engine.orchestrator.RowProcessor") as mock_processor_cls:
            mock_processor = MagicMock()
            mock_processor.process_row.return_value = []
            mock_processor_cls.return_value = mock_processor

            orchestrator.run(config, graph=graph, settings=settings)

            # Check coalesce_step_map was passed
            call_kwargs = mock_processor_cls.call_args.kwargs
            assert "coalesce_step_map" in call_kwargs
            # 2 transforms + 1 gate = step 3 for coalesce
            assert call_kwargs["coalesce_step_map"]["merge_results"] == 3
