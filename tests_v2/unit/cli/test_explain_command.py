# tests_v2/unit/cli/test_explain_command.py
"""Tests for elspeth explain command basics.

Migrated from tests/cli/test_explain_command.py.
Tests that require LandscapeDB (JSON mode, text mode with real data)
are deferred to integration tier.
"""

from typer.testing import CliRunner

from elspeth.cli import app

runner = CliRunner()


class TestExplainCommandBasics:
    """Basic CLI tests for explain command."""

    def test_explain_requires_run_id(self) -> None:
        """explain requires --run option and exits with specific error."""
        result = runner.invoke(app, ["explain"])
        # Typer exits with code 2 for missing required options
        assert result.exit_code == 2, f"Expected exit code 2 for missing --run, got {result.exit_code}"
        # Error message should mention the missing option (output includes stderr)
        output = result.output.lower()
        assert "missing option" in output or "--run" in output, f"Expected error about missing --run option, got: {output}"
