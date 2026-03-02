"""Regression tests for MCP server call_tool error signaling.

Bug fix covered:
- P1-2026-02-14: call_tool returns success (isError=false) for invalid
  args and unknown tools, causing MCP clients to mishandle failures.
"""

from __future__ import annotations

import pytest
from mcp.types import CallToolResult, TextContent

from elspeth.mcp.server import _validate_tool_args


class TestCallToolErrorSignaling:
    """Verify call_tool returns MCP error results for validation failures.

    Regression: P1-2026-02-14 -- call_tool returned plain TextContent for
    invalid arguments and unknown tools. MCP protocol wraps these as
    isError=false (success), so clients could not distinguish errors
    from successful tool results.

    The fix returns CallToolResult with isError=True instead of plain
    TextContent list.
    """

    def test_invalid_args_raises_value_error(self) -> None:
        """Missing required args must produce ValueError from validation."""
        with pytest.raises(ValueError, match="requires 'run_id'"):
            _validate_tool_args("get_run", {})

    def test_unknown_tool_raises_value_error(self) -> None:
        """Unknown tool name must produce ValueError from validation."""
        with pytest.raises(ValueError, match="Unknown tool"):
            _validate_tool_args("totally_fake_tool", {})

    def test_wrong_type_raises_type_error(self) -> None:
        """Wrong argument type must produce TypeError from validation."""
        with pytest.raises(TypeError, match="must be string"):
            _validate_tool_args("get_run", {"run_id": 42})

    def test_call_tool_result_is_importable_from_server(self) -> None:
        """CallToolResult must be importable from server module (used for error signaling)."""
        from elspeth.mcp.server import CallToolResult as ImportedCTR

        assert ImportedCTR is CallToolResult

    def test_error_result_structure(self) -> None:
        """CallToolResult with isError=True can wrap validation error text."""
        result = CallToolResult(
            content=[TextContent(type="text", text="Invalid arguments: 'get_run' requires 'run_id'")],
            isError=True,
        )
        assert result.isError is True
        assert len(result.content) == 1
        first_content = result.content[0]
        assert isinstance(first_content, TextContent)
        assert "Invalid arguments" in first_content.text

    def test_success_result_has_is_error_false(self) -> None:
        """Normal tool results have isError=False by default."""
        result = CallToolResult(
            content=[TextContent(type="text", text='{"run_id": "abc"}')],
        )
        assert result.isError is False
