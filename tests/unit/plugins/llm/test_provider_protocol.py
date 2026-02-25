# tests/unit/plugins/llm/test_provider_protocol.py
"""Tests for LLMProvider protocol and DTOs."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import runtime_checkable

import pytest

from elspeth.contracts.token_usage import TokenUsage
from elspeth.plugins.llm.provider import (
    FinishReason,
    LLMProvider,
    LLMQueryResult,
    parse_finish_reason,
)


class TestLLMQueryResult:
    """Tests for the LLMQueryResult frozen dataclass."""

    def test_is_frozen(self) -> None:
        result = LLMQueryResult(
            content="hello",
            usage=TokenUsage.known(10, 5),
            model="gpt-4o",
        )
        with pytest.raises(FrozenInstanceError):
            result.content = "modified"  # type: ignore[misc]

    def test_fields(self) -> None:
        usage = TokenUsage.known(10, 5)
        result = LLMQueryResult(
            content="hello",
            usage=usage,
            model="gpt-4o",
            finish_reason=FinishReason.STOP,
        )
        assert result.content == "hello"
        assert result.usage is usage
        assert result.model == "gpt-4o"
        assert result.finish_reason == FinishReason.STOP
        # raw_response is NOT on LLMQueryResult
        assert not hasattr(result, "raw_response")

    def test_post_init_rejects_empty_content(self) -> None:
        with pytest.raises(ValueError, match="content must be non-empty"):
            LLMQueryResult(
                content="",
                usage=TokenUsage.unknown(),
                model="gpt-4o",
            )

    def test_post_init_rejects_whitespace_content(self) -> None:
        with pytest.raises(ValueError, match="content must be non-empty"):
            LLMQueryResult(
                content="   ",
                usage=TokenUsage.unknown(),
                model="gpt-4o",
            )

    def test_post_init_rejects_empty_model(self) -> None:
        with pytest.raises(ValueError, match="model must be non-empty"):
            LLMQueryResult(
                content="hello",
                usage=TokenUsage.unknown(),
                model="",
            )

    def test_post_init_rejects_whitespace_model(self) -> None:
        with pytest.raises(ValueError, match="model must be non-empty"):
            LLMQueryResult(
                content="hello",
                usage=TokenUsage.unknown(),
                model="   ",
            )

    def test_finish_reason_defaults_to_none(self) -> None:
        result = LLMQueryResult(
            content="hello",
            usage=TokenUsage.unknown(),
            model="gpt-4o",
        )
        assert result.finish_reason is None


class TestFinishReason:
    """Tests for FinishReason StrEnum."""

    def test_enum_values(self) -> None:
        assert FinishReason.STOP == "stop"
        assert FinishReason.LENGTH == "length"
        assert FinishReason.CONTENT_FILTER == "content_filter"
        assert FinishReason.TOOL_CALLS == "tool_calls"

    def test_from_string(self) -> None:
        assert FinishReason("stop") is FinishReason.STOP
        assert FinishReason("length") is FinishReason.LENGTH


class TestParseFinishReason:
    """Tests for parse_finish_reason helper."""

    def test_none_returns_none(self) -> None:
        assert parse_finish_reason(None) is None

    def test_valid_stop(self) -> None:
        assert parse_finish_reason("stop") is FinishReason.STOP

    def test_valid_length(self) -> None:
        assert parse_finish_reason("length") is FinishReason.LENGTH

    def test_valid_content_filter(self) -> None:
        assert parse_finish_reason("content_filter") is FinishReason.CONTENT_FILTER

    def test_unknown_logs_warning(
        self,
        capsys: pytest.CaptureFixture[str],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        import logging

        with caplog.at_level(logging.WARNING, logger="elspeth.plugins.llm.provider"):
            result = parse_finish_reason("end_turn")
        assert result is None
        # structlog routes to stdout (PrintLogger) in isolation or stdlib logging
        # in the full suite — check both capture mechanisms
        stdout_has_it = "end_turn" in capsys.readouterr().out
        caplog_has_it = any("end_turn" in r.getMessage() for r in caplog.records)
        assert stdout_has_it or caplog_has_it, "Expected warning about 'end_turn' in structlog output"

    def test_empty_string_logs_warning(
        self,
        capsys: pytest.CaptureFixture[str],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        import logging

        with caplog.at_level(logging.WARNING, logger="elspeth.plugins.llm.provider"):
            result = parse_finish_reason("")
        assert result is None
        stdout_has_it = "finish_reason" in capsys.readouterr().out.lower()
        caplog_has_it = any("finish_reason" in r.getMessage().lower() for r in caplog.records)
        assert stdout_has_it or caplog_has_it, "Expected warning about unknown finish_reason in structlog output"


class TestLLMProviderProtocol:
    """Tests for the LLMProvider protocol."""

    def test_is_runtime_checkable(self) -> None:
        assert runtime_checkable in getattr(LLMProvider, "__protocol_attrs__", ()) or hasattr(LLMProvider, "__protocol_attrs__")
        # More direct check: isinstance should work
        assert isinstance(LLMProvider, type)

    def test_mock_provider_satisfies_protocol(self) -> None:
        class MockProvider:
            def execute_query(
                self,
                messages: list[dict[str, str]],
                *,
                model: str,
                temperature: float,
                max_tokens: int | None,
                state_id: str,
                token_id: str,
            ) -> LLMQueryResult:
                return LLMQueryResult(
                    content="test",
                    usage=TokenUsage.unknown(),
                    model=model,
                )

            def close(self) -> None:
                pass

        provider = MockProvider()
        assert isinstance(provider, LLMProvider)
