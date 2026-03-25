"""Tests for dependency + gate phases in bootstrap_and_run()."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from elspeth.contracts.errors import CommencementGateFailedError


class TestBootstrapDependencyDispatch:
    """Test that bootstrap_and_run() calls dependency resolution when configured."""

    def test_skips_dependencies_when_not_configured(self) -> None:
        """When depends_on is empty, dependency resolver is never called."""
        mock_config = MagicMock()
        mock_config.depends_on = []
        mock_config.commencement_gates = []
        mock_config.gates = []
        mock_config.coalesce = []
        mock_config.landscape.export.enabled = False
        mock_config.payload_store.backend = "filesystem"

        with (
            patch("elspeth.core.config.load_settings", return_value=mock_config),
            patch("elspeth.cli_helpers.instantiate_plugins_from_config") as mock_plugins,
            patch("elspeth.core.dag.ExecutionGraph") as mock_graph_cls,
            patch("elspeth.core.landscape.LandscapeDB"),
            patch("elspeth.core.payload_store.FilesystemPayloadStore"),
            patch("elspeth.cli._orchestrator_context") as mock_orch_ctx,
            patch("elspeth.engine.dependency_resolver.detect_cycles") as mock_detect,
            patch("elspeth.engine.dependency_resolver.resolve_dependencies") as mock_resolve,
        ):
            mock_plugins.return_value = MagicMock()
            mock_graph = MagicMock()
            mock_graph_cls.from_plugin_instances.return_value = mock_graph

            mock_run_result = MagicMock()
            mock_ctx = MagicMock()
            mock_ctx.orchestrator.run.return_value = mock_run_result
            mock_orch_ctx.return_value.__enter__ = MagicMock(return_value=mock_ctx)
            mock_orch_ctx.return_value.__exit__ = MagicMock(return_value=False)

            from elspeth.engine.bootstrap import bootstrap_and_run

            bootstrap_and_run(Path("/fake/pipeline.yaml"))

        mock_detect.assert_not_called()
        mock_resolve.assert_not_called()


class TestBootstrapCommencementGateDispatch:
    """Test that bootstrap_and_run() evaluates gates when configured."""

    def test_skips_gates_when_not_configured(self) -> None:
        """When commencement_gates is empty, gate evaluator is never called."""
        mock_config = MagicMock()
        mock_config.depends_on = []
        mock_config.commencement_gates = []
        mock_config.gates = []
        mock_config.coalesce = []
        mock_config.landscape.export.enabled = False
        mock_config.payload_store.backend = "filesystem"

        with (
            patch("elspeth.core.config.load_settings", return_value=mock_config),
            patch("elspeth.cli_helpers.instantiate_plugins_from_config") as mock_plugins,
            patch("elspeth.core.dag.ExecutionGraph") as mock_graph_cls,
            patch("elspeth.core.landscape.LandscapeDB"),
            patch("elspeth.core.payload_store.FilesystemPayloadStore"),
            patch("elspeth.cli._orchestrator_context") as mock_orch_ctx,
            patch("elspeth.engine.commencement.evaluate_commencement_gates") as mock_eval_gates,
        ):
            mock_plugins.return_value = MagicMock()
            mock_graph = MagicMock()
            mock_graph_cls.from_plugin_instances.return_value = mock_graph

            mock_run_result = MagicMock()
            mock_ctx = MagicMock()
            mock_ctx.orchestrator.run.return_value = mock_run_result
            mock_orch_ctx.return_value.__enter__ = MagicMock(return_value=mock_ctx)
            mock_orch_ctx.return_value.__exit__ = MagicMock(return_value=False)

            from elspeth.engine.bootstrap import bootstrap_and_run

            bootstrap_and_run(Path("/fake/pipeline.yaml"))

        mock_eval_gates.assert_not_called()

    def test_gate_failure_propagates(self) -> None:
        """When a gate fails, CommencementGateFailedError propagates through bootstrap."""
        mock_config = MagicMock()
        mock_config.depends_on = []
        mock_config.commencement_gates = [MagicMock()]  # Non-empty triggers gate eval
        mock_config.collection_probes = []
        mock_config.gates = []
        mock_config.coalesce = []
        mock_config.landscape.export.enabled = False

        with (
            patch("elspeth.core.config.load_settings", return_value=mock_config),
            patch("elspeth.cli_helpers.instantiate_plugins_from_config") as mock_plugins,
            patch("elspeth.core.dag.ExecutionGraph") as mock_graph_cls,
            patch(
                "elspeth.engine.commencement.evaluate_commencement_gates",
                side_effect=CommencementGateFailedError(
                    gate_name="test_gate",
                    condition="False",
                    reason="test failure",
                    context_snapshot={},
                ),
            ),
            patch("elspeth.plugins.infrastructure.probe_factory.build_collection_probes", return_value=[]),
        ):
            mock_plugins.return_value = MagicMock()
            mock_graph = MagicMock()
            mock_graph_cls.from_plugin_instances.return_value = mock_graph

            from elspeth.engine.bootstrap import bootstrap_and_run

            with pytest.raises(CommencementGateFailedError, match="test_gate"):
                bootstrap_and_run(Path("/fake/pipeline.yaml"))
