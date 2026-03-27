"""Tests for dependency + gate phases in bootstrap_and_run() and resolve_preflight()."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from elspeth.contracts.errors import CommencementGateFailedError
from elspeth.core.dependency_config import (
    CommencementGateResult,
    DependencyRunResult,
)


class TestBootstrapDependencyDispatch:
    """Test that bootstrap_and_run() calls dependency resolution when configured."""

    def test_skips_dependencies_when_not_configured(self) -> None:
        """When depends_on is empty, dependency resolver is never called."""
        mock_config = MagicMock()
        mock_config.depends_on = []
        mock_config.commencement_gates = []
        mock_config.collection_probes = []
        mock_config.gates = []
        mock_config.coalesce = []
        mock_config.landscape.export.enabled = False
        mock_config.payload_store.backend = "filesystem"

        with (
            patch("elspeth.cli._load_settings_with_secrets", return_value=(mock_config, [])),
            patch("elspeth.cli_helpers.instantiate_plugins_from_config") as mock_plugins,
            patch("elspeth.core.dag.ExecutionGraph") as mock_graph_cls,
            patch("elspeth.core.landscape.LandscapeDB"),
            patch("elspeth.core.payload_store.FilesystemPayloadStore"),
            patch("elspeth.cli._orchestrator_context") as mock_orch_ctx,
            patch("elspeth.cli._ensure_output_directories", return_value=[]),
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

            from elspeth.cli_helpers import bootstrap_and_run

            bootstrap_and_run(Path("/fake/pipeline.yaml"))

        mock_detect.assert_not_called()
        mock_resolve.assert_not_called()


class TestBootstrapDependencyResultsFlow:
    """Test that dependency results flow into gate context (regression for bug #1)."""

    def test_dependency_results_passed_to_gate_context(self) -> None:
        """Dependency run results must be visible in commencement gate expressions."""
        from elspeth.core.dependency_config import DependencyConfig, DependencyRunResult

        mock_config = MagicMock()
        mock_config.depends_on = [DependencyConfig(name="indexer", settings="./index.yaml")]
        mock_config.commencement_gates = [MagicMock()]
        mock_config.collection_probes = []
        mock_config.gates = []
        mock_config.coalesce = []
        mock_config.landscape.export.enabled = False
        mock_config.payload_store.backend = "filesystem"

        dep_result = DependencyRunResult(
            name="indexer",
            run_id="dep-run-abc",
            settings_hash="sha256:abc",
            duration_ms=1000,
            indexed_at="2026-03-25T12:00:00Z",
        )

        captured_context = {}

        def capture_gate_context(gates: object, context: dict) -> list:
            captured_context.update(context)
            return []

        with (
            patch("elspeth.cli._load_settings_with_secrets", return_value=(mock_config, [])),
            patch("elspeth.cli_helpers.instantiate_plugins_from_config", return_value=MagicMock()),
            patch("elspeth.core.dag.ExecutionGraph") as mock_graph_cls,
            patch("elspeth.core.landscape.LandscapeDB"),
            patch("elspeth.core.payload_store.FilesystemPayloadStore"),
            patch("elspeth.cli._orchestrator_context") as mock_orch_ctx,
            patch("elspeth.cli._ensure_output_directories", return_value=[]),
            patch("elspeth.engine.dependency_resolver.detect_cycles"),
            patch("elspeth.engine.dependency_resolver.resolve_dependencies", return_value=[dep_result]),
            patch("elspeth.engine.commencement.evaluate_commencement_gates", side_effect=capture_gate_context),
        ):
            mock_graph_cls.from_plugin_instances.return_value = MagicMock()
            mock_ctx = MagicMock()
            mock_ctx.orchestrator.run.return_value = MagicMock()
            mock_orch_ctx.return_value.__enter__ = MagicMock(return_value=mock_ctx)
            mock_orch_ctx.return_value.__exit__ = MagicMock(return_value=False)

            from elspeth.cli_helpers import bootstrap_and_run

            bootstrap_and_run(Path("/fake/pipeline.yaml"))

        # Dependency results must be in the gate context — NOT empty
        assert "dependency_runs" in captured_context
        assert "indexer" in captured_context["dependency_runs"]
        assert captured_context["dependency_runs"]["indexer"]["run_id"] == "dep-run-abc"


class TestBootstrapCommencementGateDispatch:
    """Test that bootstrap_and_run() evaluates gates when configured."""

    def test_skips_gates_when_not_configured(self) -> None:
        """When commencement_gates is empty, gate evaluator is never called."""
        mock_config = MagicMock()
        mock_config.depends_on = []
        mock_config.commencement_gates = []
        mock_config.collection_probes = []
        mock_config.gates = []
        mock_config.coalesce = []
        mock_config.landscape.export.enabled = False
        mock_config.payload_store.backend = "filesystem"

        with (
            patch("elspeth.cli._load_settings_with_secrets", return_value=(mock_config, [])),
            patch("elspeth.cli_helpers.instantiate_plugins_from_config") as mock_plugins,
            patch("elspeth.core.dag.ExecutionGraph") as mock_graph_cls,
            patch("elspeth.core.landscape.LandscapeDB"),
            patch("elspeth.core.payload_store.FilesystemPayloadStore"),
            patch("elspeth.cli._orchestrator_context") as mock_orch_ctx,
            patch("elspeth.cli._ensure_output_directories", return_value=[]),
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

            from elspeth.cli_helpers import bootstrap_and_run

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
            patch("elspeth.cli._load_settings_with_secrets", return_value=(mock_config, [])),
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
        ):
            mock_plugins.return_value = MagicMock()
            mock_graph = MagicMock()
            mock_graph_cls.from_plugin_instances.return_value = mock_graph

            from elspeth.cli_helpers import bootstrap_and_run

            with pytest.raises(CommencementGateFailedError, match="test_gate"):
                bootstrap_and_run(Path("/fake/pipeline.yaml"))


class TestResolvePreflightDirect:
    """Direct unit tests for resolve_preflight() (extracted from bootstrap_and_run)."""

    def test_returns_none_when_nothing_configured(self) -> None:
        """Returns None when neither depends_on nor commencement_gates are configured."""
        from elspeth.engine.bootstrap import resolve_preflight

        mock_config = MagicMock()
        mock_config.depends_on = []
        mock_config.commencement_gates = []

        result = resolve_preflight(mock_config, Path("/fake/pipeline.yaml"))
        assert result is None

    def test_calls_dependency_resolver(self) -> None:
        """When depends_on is configured, calls detect_cycles and resolve_dependencies."""
        from elspeth.core.dependency_config import DependencyConfig
        from elspeth.engine.bootstrap import resolve_preflight

        mock_config = MagicMock()
        mock_config.depends_on = [DependencyConfig(name="indexer", settings="./index.yaml")]
        mock_config.commencement_gates = []

        dep_result = DependencyRunResult(
            name="indexer",
            run_id="dep-run-abc",
            settings_hash="sha256:abc",
            duration_ms=1000,
            indexed_at="2026-03-25T12:00:00Z",
        )

        mock_runner = MagicMock()

        with (
            patch("elspeth.engine.dependency_resolver.detect_cycles") as mock_detect,
            patch("elspeth.engine.dependency_resolver.resolve_dependencies", return_value=[dep_result]) as mock_resolve,
        ):
            result = resolve_preflight(mock_config, Path("/fake/pipeline.yaml"), runner=mock_runner)

        mock_detect.assert_called_once_with(Path("/fake/pipeline.yaml"))
        mock_resolve.assert_called_once()
        assert result is not None
        assert len(result.dependency_runs) == 1
        assert result.dependency_runs[0].name == "indexer"

    def test_evaluates_commencement_gates_without_dependencies(self) -> None:
        """When only commencement_gates are configured, gates are evaluated."""
        from elspeth.engine.bootstrap import resolve_preflight

        mock_config = MagicMock()
        mock_config.depends_on = []
        mock_config.commencement_gates = [MagicMock()]

        gate_result = CommencementGateResult(
            name="corpus_ready",
            condition="collections['test']['count'] > 0",
            result=True,
            context_snapshot={"collections": {"test": {"count": 10}}},
        )

        mock_probes: list = []

        with (
            patch("elspeth.engine.commencement.evaluate_commencement_gates", return_value=[gate_result]) as mock_eval,
        ):
            result = resolve_preflight(mock_config, Path("/fake/pipeline.yaml"), probes=mock_probes)

        mock_eval.assert_called_once()
        assert result is not None
        assert len(result.gate_results) == 1
        assert result.gate_results[0].name == "corpus_ready"
        assert result.gate_results[0].result is True

    def test_dependency_results_flow_into_gate_context(self) -> None:
        """When both depends_on and gates are configured, dep results are in gate context."""
        from elspeth.core.dependency_config import DependencyConfig
        from elspeth.engine.bootstrap import resolve_preflight

        mock_config = MagicMock()
        mock_config.depends_on = [DependencyConfig(name="indexer", settings="./index.yaml")]
        mock_config.commencement_gates = [MagicMock()]

        dep_result = DependencyRunResult(
            name="indexer",
            run_id="dep-run-abc",
            settings_hash="sha256:abc",
            duration_ms=1000,
            indexed_at="2026-03-25T12:00:00Z",
        )

        captured_context = {}

        def capture_gate_context(gates: object, context: dict) -> list:
            captured_context.update(context)
            return []

        mock_runner = MagicMock()
        mock_probes: list = []

        with (
            patch("elspeth.engine.dependency_resolver.detect_cycles"),
            patch("elspeth.engine.dependency_resolver.resolve_dependencies", return_value=[dep_result]),
            patch("elspeth.engine.commencement.evaluate_commencement_gates", side_effect=capture_gate_context),
        ):
            resolve_preflight(mock_config, Path("/fake/pipeline.yaml"), probes=mock_probes, runner=mock_runner)

        assert "dependency_runs" in captured_context
        assert "indexer" in captured_context["dependency_runs"]
        assert captured_context["dependency_runs"]["indexer"]["run_id"] == "dep-run-abc"

    def test_gate_failure_propagates(self) -> None:
        """CommencementGateFailedError propagates through resolve_preflight."""
        from elspeth.engine.bootstrap import resolve_preflight

        mock_config = MagicMock()
        mock_config.depends_on = []
        mock_config.commencement_gates = [MagicMock()]

        mock_probes: list = []

        with (
            patch(
                "elspeth.engine.commencement.evaluate_commencement_gates",
                side_effect=CommencementGateFailedError(
                    gate_name="test_gate",
                    condition="False",
                    reason="test failure",
                    context_snapshot={},
                ),
            ),
            pytest.raises(CommencementGateFailedError, match="test_gate"),
        ):
            resolve_preflight(mock_config, Path("/fake/pipeline.yaml"), probes=mock_probes)

    def test_runner_none_with_depends_on_raises_framework_bug(self) -> None:
        """FrameworkBugError when runner=None but depends_on is configured."""
        from elspeth.contracts.errors import FrameworkBugError
        from elspeth.core.dependency_config import DependencyConfig
        from elspeth.engine.bootstrap import resolve_preflight

        mock_config = MagicMock()
        mock_config.depends_on = [DependencyConfig(name="idx", settings="./idx.yaml")]
        mock_config.commencement_gates = []

        with pytest.raises(FrameworkBugError, match="runner is required"):
            resolve_preflight(mock_config, Path("/fake/pipeline.yaml"), runner=None)

    def test_probes_none_with_gates_raises_framework_bug(self) -> None:
        """FrameworkBugError when probes=None but commencement_gates is configured."""
        from elspeth.contracts.errors import FrameworkBugError
        from elspeth.engine.bootstrap import resolve_preflight

        mock_config = MagicMock()
        mock_config.depends_on = []
        mock_config.commencement_gates = [MagicMock()]

        with pytest.raises(FrameworkBugError, match="probes is required"):
            resolve_preflight(mock_config, Path("/fake/pipeline.yaml"), probes=None)

    def test_duplicate_dependency_names_rejected(self) -> None:
        """Duplicate dependency names must raise before building gate context.

        Without this check, the dict comprehension silently overwrites earlier
        entries, so gates would evaluate against incomplete dependency data.
        """
        from elspeth.core.dependency_config import DependencyConfig
        from elspeth.engine.bootstrap import resolve_preflight

        mock_config = MagicMock()
        mock_config.depends_on = [
            DependencyConfig(name="indexer", settings="./a.yaml"),
            DependencyConfig(name="indexer", settings="./b.yaml"),
        ]
        mock_config.commencement_gates = [MagicMock()]

        dep_results = [
            DependencyRunResult(name="indexer", run_id="r1", settings_hash="h1", duration_ms=100, indexed_at="2026-01-01T00:00:00Z"),
            DependencyRunResult(name="indexer", run_id="r2", settings_hash="h2", duration_ms=200, indexed_at="2026-01-01T00:00:00Z"),
        ]

        mock_runner = MagicMock()

        with (
            patch("elspeth.engine.dependency_resolver.detect_cycles"),
            patch("elspeth.engine.dependency_resolver.resolve_dependencies", return_value=dep_results),
            pytest.raises(ValueError, match=r"Duplicate dependency names.*indexer"),
        ):
            resolve_preflight(mock_config, Path("/fake/pipeline.yaml"), runner=mock_runner, probes=[])
