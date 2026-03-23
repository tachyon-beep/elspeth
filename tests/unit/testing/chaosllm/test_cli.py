"""Tests for ChaosLLM CLI entry points."""

from unittest.mock import AsyncMock, patch

from errorworks.llm.cli import mcp_app
from typer.testing import CliRunner

runner = CliRunner()


def test_mcp_main_calls_run_server(tmp_path):
    """MCP CLI must call run_server(), not the nonexistent serve().

    Regression test for T27: the CLI was calling mcp_server.serve(database)
    which raises AttributeError because the function is run_server().
    """
    db_file = tmp_path / "test-metrics.db"
    db_file.write_bytes(b"")  # Create empty file so path validation passes

    mock_run_server = AsyncMock()

    with patch(
        "errorworks.llm_mcp.server.run_server",
        mock_run_server,
    ):
        result = runner.invoke(mcp_app, ["--database", str(db_file)])

    assert result.exit_code == 0, f"CLI exited with error: {result.output}"
    mock_run_server.assert_called_once_with(str(db_file))
