# tests/unit/cli/test_cli.py
"""Tests for ELSPETH CLI basics.

Migrated from tests/cli/test_cli.py.
Tests that require LandscapeDB, Orchestrator, or real file I/O with
verify_audit_trail are deferred to integration tier.
"""

from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

runner = CliRunner()


class TestCLIBasics:
    """Test basic CLI functionality."""

    def test_cli_exists(self) -> None:
        """CLI app can be imported."""
        from elspeth.cli import app

        assert app is not None

    def test_version_flag(self) -> None:
        """--version shows version info."""
        from elspeth.cli import app

        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "elspeth" in result.stdout.lower()

    def test_help_flag(self) -> None:
        """--help shows available commands."""
        from elspeth.cli import app

        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "run" in result.stdout
        assert "explain" in result.stdout
        assert "validate" in result.stdout
        assert "plugins" in result.stdout
        assert "resume" in result.stdout
        assert "purge" in result.stdout


class TestTildeExpansion:
    """Tests that CLI path options expand ~ to home directory.

    Regression tests for:
    - docs/bugs/closed/P2-2026-01-20-cli-paths-no-tilde-expansion.md
    """

    def test_run_expands_tilde_in_settings_path(self, tmp_path: Path) -> None:
        """run command expands ~ in --settings path.

        Creates a file in a temp dir, then constructs a path using ~ that
        resolves to the same location, verifying expansion works.
        """
        from elspeth.cli import app

        # Create a settings file
        settings_content = """
source:
  plugin: csv
  options:
    path: input.csv
    on_validation_failure: discard
    on_success: default
sinks:
  default:
    plugin: json
    options:
      path: output.json
"""
        settings_file = tmp_path / "settings.yaml"
        settings_file.write_text(settings_content)

        # Mock expanduser to return our temp path
        # This simulates ~ expanding to our test directory
        def mock_expanduser(self: Path) -> Path:
            if str(self).startswith("~"):
                return tmp_path / str(self)[2:]  # Replace ~/x with tmp_path/x
            return self

        with patch.object(Path, "expanduser", mock_expanduser):
            result = runner.invoke(app, ["run", "-s", "~/settings.yaml"])

        # Should find the file (even if validation fails for other reasons)
        # The key is that it doesn't say "file not found" for the tilde path
        assert "Settings file not found: ~/settings.yaml" not in result.output

    def test_validate_expands_tilde_in_settings_path(self, tmp_path: Path) -> None:
        """validate command expands ~ in --settings path."""
        from elspeth.cli import app

        settings_content = """
source:
  plugin: csv
  options:
    path: input.csv
    on_validation_failure: discard
    on_success: default
sinks:
  default:
    plugin: json
    options:
      path: output.json
"""
        settings_file = tmp_path / "settings.yaml"
        settings_file.write_text(settings_content)

        def mock_expanduser(self: Path) -> Path:
            if str(self).startswith("~"):
                return tmp_path / str(self)[2:]
            return self

        with patch.object(Path, "expanduser", mock_expanduser):
            result = runner.invoke(app, ["validate", "-s", "~/settings.yaml"])

        # Should find the file
        assert "Settings file not found: ~/settings.yaml" not in result.output


class TestBuildResumeGraphs:
    """Test _build_resume_graphs accepts connection-valued on_success.

    Regression test for 6v1d: resume mode must accept connection names (e.g.
    'source_out') not just sink names as source.on_success. The previous
    implementation rejected connection-valued on_success with a typer.Exit(1).
    """

    def test_connection_valued_on_success_accepted(self, plugin_manager) -> None:
        """_build_resume_graphs succeeds when source.on_success is a connection name."""
        from elspeth.cli import _build_resume_graphs
        from elspeth.cli_helpers import instantiate_plugins_from_config
        from elspeth.core.config import (
            ElspethSettings,
            SinkSettings,
            SourceSettings,
            TransformSettings,
        )

        config = ElspethSettings(
            source=SourceSettings(
                plugin="csv",
                on_success="source_out",
                options={
                    "path": "test.csv",
                    "on_validation_failure": "discard",
                    "schema": {"mode": "observed"},
                },
            ),
            transforms=[
                TransformSettings(
                    name="processor",
                    plugin="passthrough",
                    input="source_out",
                    on_success="output",
                    options={"schema": {"mode": "observed"}},
                ),
            ],
            sinks={
                "output": SinkSettings(
                    plugin="json",
                    options={"path": "output.json", "schema": {"mode": "observed"}},
                ),
            },
        )

        plugins = instantiate_plugins_from_config(config)
        validation_graph, execution_graph = _build_resume_graphs(config, plugins)

        # Both graphs should build successfully
        assert validation_graph.node_count > 0
        assert execution_graph.node_count > 0

    def test_sink_valued_on_success_still_accepted(self, plugin_manager) -> None:
        """_build_resume_graphs still works when source.on_success is a sink name."""
        from elspeth.cli import _build_resume_graphs
        from elspeth.cli_helpers import instantiate_plugins_from_config
        from elspeth.core.config import ElspethSettings, SinkSettings, SourceSettings

        config = ElspethSettings(
            source=SourceSettings(
                plugin="csv",
                on_success="output",
                options={
                    "path": "test.csv",
                    "on_validation_failure": "discard",
                    "schema": {"mode": "observed"},
                },
            ),
            sinks={
                "output": SinkSettings(
                    plugin="json",
                    options={"path": "output.json", "schema": {"mode": "observed"}},
                ),
            },
        )

        plugins = instantiate_plugins_from_config(config)
        validation_graph, execution_graph = _build_resume_graphs(config, plugins)

        assert validation_graph.node_count > 0
        assert execution_graph.node_count > 0
