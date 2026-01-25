"""Tests for elspeth explain command.

Validates explain command exit codes, output format, and error messages.
"""

import json

from typer.testing import CliRunner

from elspeth.cli import app

runner = CliRunner()


class TestExplainCommand:
    """Tests for explain command."""

    def test_explain_requires_run_id(self) -> None:
        """explain requires --run option and exits with specific error."""
        result = runner.invoke(app, ["explain"])
        # Typer exits with code 2 for missing required options
        assert result.exit_code == 2, f"Expected exit code 2 for missing --run, got {result.exit_code}"
        # Error message should mention the missing option (output includes stderr)
        output = result.output.lower()
        assert "missing option" in output or "--run" in output, f"Expected error about missing --run option, got: {output}"

    def test_explain_no_tui_mode_exits_with_code_2(self) -> None:
        """explain --no-tui exits with code 2 (not implemented)."""
        result = runner.invoke(app, ["explain", "--run", "test-run", "--no-tui"])
        assert result.exit_code == 2, f"Expected exit code 2 for --no-tui, got {result.exit_code}"

    def test_explain_no_tui_writes_message(self) -> None:
        """explain --no-tui writes specific message about not being implemented."""
        result = runner.invoke(app, ["explain", "--run", "test-run", "--no-tui"])
        # Message includes stderr in output (CliRunner mixes by default)
        output = result.output.lower()
        assert "not yet implemented" in output, f"Expected 'not yet implemented' in output, got: {output}"
        assert "phase 4" in output, f"Expected 'phase 4' mention in output, got: {output}"

    def test_explain_json_output_exits_with_code_2(self) -> None:
        """explain --json exits with code 2 (not implemented)."""
        result = runner.invoke(app, ["explain", "--run", "test-run", "--json"])
        assert result.exit_code == 2, f"Expected exit code 2 for --json, got {result.exit_code}"

    def test_explain_json_output_is_valid_json(self) -> None:
        """explain --json outputs valid, parseable JSON."""
        result = runner.invoke(app, ["explain", "--run", "test-run", "--json"])
        output = result.output.strip()
        # Must be valid JSON
        try:
            data = json.loads(output)
        except json.JSONDecodeError as e:
            raise AssertionError(f"Output is not valid JSON: {e}\nOutput: {output}") from e
        # Must be a dict (not a list)
        assert isinstance(data, dict), f"Expected JSON object, got {type(data).__name__}"

    def test_explain_json_output_has_contract_fields(self) -> None:
        """explain --json output contains expected contract fields."""
        result = runner.invoke(app, ["explain", "--run", "test-run", "--json"])
        data = json.loads(result.output)
        # Required fields per src/elspeth/cli.py:312-316
        assert data["run_id"] == "test-run", f"Expected run_id='test-run', got {data.get('run_id')}"
        assert data["status"] == "not_implemented", f"Expected status='not_implemented', got {data.get('status')}"
        assert "message" in data, "Expected 'message' field in JSON output"

    def test_explain_json_with_row_option(self) -> None:
        """explain --json preserves --row option in output."""
        result = runner.invoke(app, ["explain", "--run", "test-run", "--row", "42", "--json"])
        data = json.loads(result.output)
        assert data["row"] == "42", f"Expected row='42', got {data.get('row')}"

    def test_explain_json_with_token_option(self) -> None:
        """explain --json preserves --token option in output."""
        result = runner.invoke(app, ["explain", "--run", "test-run", "--token", "tok-abc", "--json"])
        data = json.loads(result.output)
        assert data["token"] == "tok-abc", f"Expected token='tok-abc', got {data.get('token')}"
