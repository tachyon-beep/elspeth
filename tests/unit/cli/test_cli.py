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
