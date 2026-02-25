# tests/unit/plugins/llm/test_validation.py
"""Tests for shared LLM validation helpers.

Covers:
- render_template_safe: Template rendering with structured error handling
- check_truncation: Response truncation detection
- strip_markdown_fences: Markdown code block stripping
"""

from __future__ import annotations

from elspeth.plugins.llm.templates import PromptTemplate, RenderedPrompt
from elspeth.plugins.llm.validation import (
    check_truncation,
    render_template_safe,
    strip_markdown_fences,
)

# ── render_template_safe tests ─────────────────────────────────────


class TestRenderTemplateSafe:
    """Tests for safe template rendering with structured errors."""

    def test_render_template_safe_success(self) -> None:
        template = PromptTemplate('Classify: {{ row["text"] }}')
        result = render_template_safe(template, {"text": "hello world"})
        assert isinstance(result, RenderedPrompt)
        assert result.prompt == "Classify: hello world"

    def test_render_template_safe_template_error_returns_error_reason(self) -> None:
        # StrictUndefined means undefined vars raise TemplateError
        template = PromptTemplate("Classify: {{ nonexistent_var }}")
        result = render_template_safe(template, {"text": "hello"})
        assert isinstance(result, dict)
        assert result["reason"] == "template_rendering_failed"
        assert "error" in result

    def test_render_template_safe_includes_template_hash(self) -> None:
        template = PromptTemplate("{{ nonexistent }}")
        result = render_template_safe(template, {})
        assert isinstance(result, dict)
        assert "template_hash" in result

    def test_render_template_safe_includes_template_source_when_present(self) -> None:
        template = PromptTemplate(
            "{{ missing }}",
            template_source="/path/to/template.j2",
        )
        result = render_template_safe(template, {})
        assert isinstance(result, dict)
        assert result.get("template_file_path") == "/path/to/template.j2"

    def test_render_template_safe_includes_query_name_when_provided(self) -> None:
        template = PromptTemplate("{{ missing }}")
        result = render_template_safe(template, {}, query_name="sentiment")
        assert isinstance(result, dict)
        assert result["query"] == "sentiment"

    def test_render_template_safe_forwards_contract(self) -> None:
        """Verify the contract parameter is forwarded to render_with_metadata."""
        from unittest.mock import MagicMock, patch

        template = PromptTemplate('{{ row["text"] }}')
        sentinel_contract = MagicMock()

        mock_rendered = RenderedPrompt(
            prompt="hello",
            template_hash="abc",
            variables_hash="def",
            rendered_hash="ghi",
        )

        with patch.object(template, "render_with_metadata", return_value=mock_rendered) as mock_render:
            result = render_template_safe(
                template,
                {"text": "hello"},
                contract=sentinel_contract,
            )

        assert isinstance(result, RenderedPrompt)
        mock_render.assert_called_once_with({"text": "hello"}, contract=sentinel_contract)


# ── check_truncation tests ────────────────────────────────────────


class TestCheckTruncation:
    """Tests for response truncation detection."""

    def test_check_truncation_finish_reason_length_returns_error(self) -> None:
        result = check_truncation(
            finish_reason="length",
            completion_tokens=100,
            prompt_tokens=50,
            max_tokens=100,
        )
        assert result is not None
        assert result["reason"] == "response_truncated"

    def test_check_truncation_finish_reason_stop_returns_none(self) -> None:
        result = check_truncation(
            finish_reason="stop",
            completion_tokens=50,
            prompt_tokens=50,
            max_tokens=100,
        )
        assert result is None

    def test_check_truncation_finish_reason_enum_length_returns_error(self) -> None:
        """Verify FinishReason.LENGTH works (StrEnum == str)."""
        from enum import StrEnum

        class TestFinishReason(StrEnum):
            LENGTH = "length"

        result = check_truncation(
            finish_reason=TestFinishReason.LENGTH,
            completion_tokens=100,
            prompt_tokens=50,
            max_tokens=100,
        )
        assert result is not None
        assert result["reason"] == "response_truncated"

    def test_check_truncation_token_heuristic_returns_error(self) -> None:
        result = check_truncation(
            finish_reason=None,
            completion_tokens=100,
            prompt_tokens=50,
            max_tokens=100,
        )
        assert result is not None
        assert result["reason"] == "response_truncated"

    def test_check_truncation_no_finish_reason_no_tokens_returns_none(self) -> None:
        result = check_truncation(
            finish_reason=None,
            completion_tokens=None,
            prompt_tokens=None,
            max_tokens=100,
        )
        assert result is None

    def test_check_truncation_includes_preview_when_content_provided(self) -> None:
        result = check_truncation(
            finish_reason="length",
            completion_tokens=100,
            prompt_tokens=50,
            max_tokens=100,
            content_preview="The response was...",
        )
        assert result is not None
        assert result["raw_response_preview"] == "The response was..."

    def test_check_truncation_preview_truncated_to_500_chars(self) -> None:
        """Verify content_preview is truncated to 500 characters."""
        long_preview = "x" * 800
        result = check_truncation(
            finish_reason="length",
            completion_tokens=100,
            prompt_tokens=50,
            max_tokens=100,
            content_preview=long_preview,
        )
        assert result is not None
        assert len(result["raw_response_preview"]) == 500
        assert result["raw_response_preview"] == "x" * 500

    def test_check_truncation_max_tokens_zero_returns_none(self) -> None:
        """max_tokens=0 should NOT spuriously trigger truncation."""
        result = check_truncation(
            finish_reason=None,
            completion_tokens=0,
            prompt_tokens=50,
            max_tokens=0,
        )
        assert result is None

    def test_check_truncation_includes_query_name(self) -> None:
        result = check_truncation(
            finish_reason="length",
            completion_tokens=100,
            prompt_tokens=50,
            max_tokens=100,
            query_name="sentiment",
        )
        assert result is not None
        assert result["query"] == "sentiment"


# ── strip_markdown_fences tests ───────────────────────────────────


class TestStripMarkdownFences:
    """Tests for markdown code block fence removal."""

    def test_strip_markdown_fences_removes_triple_backtick(self) -> None:
        content = '```\n{"key": "value"}\n```'
        result = strip_markdown_fences(content)
        assert result == '{"key": "value"}'

    def test_strip_markdown_fences_removes_language_tag(self) -> None:
        content = '```json\n{"key": "value"}\n```'
        result = strip_markdown_fences(content)
        assert result == '{"key": "value"}'

    def test_strip_markdown_fences_noop_when_no_fences(self) -> None:
        content = '{"key": "value"}'
        result = strip_markdown_fences(content)
        assert result == '{"key": "value"}'

    def test_strip_markdown_fences_trailing_whitespace_after_closing_fence(self) -> None:
        """Verify "```json\\n{}\\n``` " (trailing space) handled."""
        content = '```json\n{"key": "value"}\n```  '
        result = strip_markdown_fences(content)
        assert result == '{"key": "value"}'

    def test_strip_markdown_fences_no_closing_fence(self) -> None:
        """Content after opening fence is still returned when no closing fence."""
        content = '```json\n{"key": "value"}'
        result = strip_markdown_fences(content)
        assert result == '{"key": "value"}'

    def test_strip_markdown_fences_no_newline_after_opening(self) -> None:
        """Opening fence with no body (no newline) returns as-is."""
        content = "```json"
        result = strip_markdown_fences(content)
        # No newline found, so entire content after the ``` start is the "language tag"
        # Since there's no content after, it returns as-is (stripped)
        assert result == "```json"

    def test_strip_markdown_fences_preserves_inner_content(self) -> None:
        content = '```\n{\n  "a": 1,\n  "b": 2\n}\n```'
        result = strip_markdown_fences(content)
        assert result == '{\n  "a": 1,\n  "b": 2\n}'
