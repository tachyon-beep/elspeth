"""Tests for ComposerServiceImpl — LLM tool-use loop with mock LLM."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from elspeth.web.catalog.schemas import (
    PluginSchemaInfo,
    PluginSummary,
)
from elspeth.web.composer.protocol import ComposerConvergenceError, ComposerResult
from elspeth.web.composer.service import ComposerServiceImpl
from elspeth.web.composer.state import (
    CompositionState,
    PipelineMetadata,
)


def _empty_state() -> CompositionState:
    return CompositionState(
        source=None,
        nodes=(),
        edges=(),
        outputs=(),
        metadata=PipelineMetadata(),
        version=1,
    )


def _mock_catalog() -> MagicMock:
    """Mock CatalogService with real PluginSummary/PluginSchemaInfo instances.

    AC #16: Tests must use real PluginSummary and PluginSchemaInfo instances,
    not plain dicts. Mock return types must match the CatalogService protocol.
    """
    catalog = MagicMock()
    catalog.list_sources.return_value = [
        PluginSummary(
            name="csv",
            description="CSV source",
            plugin_type="source",
            config_fields=[],
        ),
    ]
    catalog.list_transforms.return_value = [
        PluginSummary(
            name="uppercase",
            description="Uppercase",
            plugin_type="transform",
            config_fields=[],
        ),
    ]
    catalog.list_sinks.return_value = [
        PluginSummary(
            name="csv",
            description="CSV sink",
            plugin_type="sink",
            config_fields=[],
        ),
    ]
    catalog.get_schema.return_value = PluginSchemaInfo(
        name="csv",
        plugin_type="source",
        description="CSV source",
        json_schema={"title": "Config", "properties": {}},
    )
    return catalog


def _make_llm_response(
    content: str | None = None,
    tool_calls: list[dict[str, Any]] | None = None,
) -> MagicMock:
    """Build a mock LiteLLM response."""
    response = MagicMock()
    choice = MagicMock()
    message = MagicMock()

    message.content = content
    message.tool_calls = None

    if tool_calls:
        mock_tool_calls = []
        for tc in tool_calls:
            mock_tc = MagicMock()
            mock_tc.id = tc["id"]
            mock_tc.function.name = tc["name"]
            mock_tc.function.arguments = json.dumps(tc["arguments"])
            mock_tool_calls.append(mock_tc)
        message.tool_calls = mock_tool_calls

    choice.message = message
    response.choices = [choice]
    return response


def _make_settings() -> MagicMock:
    settings = MagicMock()
    settings.composer_model = "gpt-4o"
    settings.composer_max_turns = 20
    settings.composer_timeout_seconds = 120.0
    settings.data_dir = Path("/data")
    return settings


class TestComposerTextOnlyResponse:
    @pytest.mark.asyncio
    async def test_text_only_returns_immediately(self) -> None:
        """LLM responds with text only — no tool calls, loop terminates."""
        catalog = _mock_catalog()
        settings = _make_settings()
        service = ComposerServiceImpl(
            catalog=catalog,
            settings=settings,
        )
        state = _empty_state()

        llm_response = _make_llm_response(content="I'll help you build a pipeline!")

        with patch.object(service, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = llm_response
            result = await service.compose("Build me a CSV pipeline", [], state)

        assert isinstance(result, ComposerResult)
        assert result.message == "I'll help you build a pipeline!"
        assert result.state.version == 1  # unchanged


class TestComposerSingleToolCall:
    @pytest.mark.asyncio
    async def test_single_tool_call_then_text(self) -> None:
        """LLM makes one tool call, then responds with text."""
        catalog = _mock_catalog()
        settings = _make_settings()
        service = ComposerServiceImpl(catalog=catalog, settings=settings)
        state = _empty_state()

        # Turn 1: tool call to set_source
        tool_response = _make_llm_response(
            content=None,
            tool_calls=[
                {
                    "id": "call_1",
                    "name": "set_source",
                    "arguments": {
                        "plugin": "csv",
                        "on_success": "t1",
                        "options": {"path": "/data/uploads/data.csv"},
                        "on_validation_failure": "quarantine",
                    },
                }
            ],
        )
        # Turn 2: text response
        text_response = _make_llm_response(content="I've set up a CSV source.")

        with patch.object(service, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = [tool_response, text_response]
            result = await service.compose("Use CSV as source", [], state)

        assert result.message == "I've set up a CSV source."
        assert result.state.source is not None
        assert result.state.source.plugin == "csv"
        assert result.state.version == 2


class TestComposerMultiTurnToolCalls:
    @pytest.mark.asyncio
    async def test_multi_turn_state_accumulates(self) -> None:
        """Multiple tool calls across turns — state accumulates."""
        catalog = _mock_catalog()
        settings = _make_settings()
        service = ComposerServiceImpl(catalog=catalog, settings=settings)
        state = _empty_state()

        # Turn 1: set_source
        turn1 = _make_llm_response(
            tool_calls=[
                {
                    "id": "call_1",
                    "name": "set_source",
                    "arguments": {
                        "plugin": "csv",
                        "on_success": "t1",
                        "options": {},
                        "on_validation_failure": "quarantine",
                    },
                }
            ],
        )
        # Turn 2: set_metadata
        turn2 = _make_llm_response(
            tool_calls=[
                {
                    "id": "call_2",
                    "name": "set_metadata",
                    "arguments": {"patch": {"name": "My Pipeline"}},
                }
            ],
        )
        # Turn 3: text
        turn3 = _make_llm_response(content="Pipeline configured.")

        with patch.object(service, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = [turn1, turn2, turn3]
            result = await service.compose("Build a pipeline", [], state)

        assert result.state.source is not None
        assert result.state.metadata.name == "My Pipeline"
        assert result.state.version == 3  # two mutations


class TestComposerConvergence:
    @pytest.mark.asyncio
    async def test_max_turns_exceeded_raises(self) -> None:
        """Loop exceeding max_turns raises ComposerConvergenceError."""
        catalog = _mock_catalog()
        settings = _make_settings()
        settings.composer_max_turns = 2  # very low limit
        service = ComposerServiceImpl(catalog=catalog, settings=settings)
        state = _empty_state()

        # Every turn makes a tool call — never produces text
        tool_response = _make_llm_response(
            tool_calls=[
                {
                    "id": "call_loop",
                    "name": "get_current_state",
                    "arguments": {},
                }
            ],
        )

        with patch.object(service, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = tool_response
            with pytest.raises(ComposerConvergenceError) as exc_info:
                await service.compose("Loop forever", [], state)
            assert exc_info.value.max_turns == 2

    @pytest.mark.asyncio
    async def test_self_correction_on_final_turn_succeeds(self) -> None:
        """B-4D-3: LLM makes tool calls on final turn, then text on bonus call."""
        catalog = _mock_catalog()
        settings = _make_settings()
        settings.composer_max_turns = 2
        service = ComposerServiceImpl(catalog=catalog, settings=settings)
        state = _empty_state()

        # Turns 1-2: tool calls (exhausts max_turns)
        tool_response = _make_llm_response(
            tool_calls=[
                {
                    "id": "call_tool",
                    "name": "get_current_state",
                    "arguments": {},
                }
            ],
        )
        # Bonus call after loop: text response (self-correction succeeds)
        text_response = _make_llm_response(content="Done after final correction.")

        with patch.object(service, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = [tool_response, tool_response, text_response]
            result = await service.compose("Do it", [], state)

        assert result.message == "Done after final correction."
        # 3 LLM calls: 2 in loop + 1 bonus
        assert mock_llm.call_count == 3

    @pytest.mark.asyncio
    async def test_bonus_call_still_wants_tools_raises(self) -> None:
        """B-4D-3: If bonus call still returns tool calls, raise convergence."""
        catalog = _mock_catalog()
        settings = _make_settings()
        settings.composer_max_turns = 1
        service = ComposerServiceImpl(catalog=catalog, settings=settings)
        state = _empty_state()

        tool_response = _make_llm_response(
            tool_calls=[
                {
                    "id": "call_tool",
                    "name": "get_current_state",
                    "arguments": {},
                }
            ],
        )

        with patch.object(service, "_call_llm", new_callable=AsyncMock) as mock_llm:
            # 1 in loop + 1 bonus = both return tool calls
            mock_llm.return_value = tool_response
            with pytest.raises(ComposerConvergenceError):
                await service.compose("Loop", [], state)
            # 2 calls: 1 in loop + 1 bonus
            assert mock_llm.call_count == 2


class TestComposerErrorHandling:
    @pytest.mark.asyncio
    async def test_unknown_tool_returns_error_to_llm(self) -> None:
        """Unknown tool name returns error message, LLM can retry."""
        catalog = _mock_catalog()
        settings = _make_settings()
        service = ComposerServiceImpl(catalog=catalog, settings=settings)
        state = _empty_state()

        # Turn 1: invalid tool
        bad_call = _make_llm_response(
            tool_calls=[
                {
                    "id": "call_bad",
                    "name": "nonexistent_tool",
                    "arguments": {},
                }
            ],
        )
        # Turn 2: text response (self-corrected)
        text = _make_llm_response(content="Sorry, let me try again.")

        with patch.object(service, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = [bad_call, text]
            result = await service.compose("Do something", [], state)

        assert result.message == "Sorry, let me try again."
        # State unchanged — the bad tool call didn't modify anything
        assert result.state.version == 1

    @pytest.mark.asyncio
    async def test_malformed_arguments_returns_error(self) -> None:
        """Malformed tool arguments return error, not crash."""
        catalog = _mock_catalog()
        settings = _make_settings()
        service = ComposerServiceImpl(catalog=catalog, settings=settings)
        state = _empty_state()

        # Turn 1: set_source with missing required field
        bad_call = _make_llm_response(
            tool_calls=[
                {
                    "id": "call_bad",
                    "name": "set_source",
                    "arguments": {"plugin": "csv"},  # missing on_success
                }
            ],
        )
        # Turn 2: text
        text = _make_llm_response(content="Fixed.")

        with patch.object(service, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = [bad_call, text]
            result = await service.compose("Setup", [], state)

        assert result.message == "Fixed."


class TestBuildMessages:
    @pytest.mark.asyncio
    async def test_build_messages_returns_new_list(self) -> None:
        """_build_messages must return a new list on every call."""
        catalog = _mock_catalog()
        settings = _make_settings()
        service = ComposerServiceImpl(catalog=catalog, settings=settings)
        state = _empty_state()

        msgs1 = service._build_messages([], state, "Hello")
        msgs2 = service._build_messages([], state, "Hello")

        assert msgs1 is not msgs2  # different list objects
        assert msgs1 == msgs2  # same content


class TestComposerMultipleToolCallsPerTurn:
    @pytest.mark.asyncio
    async def test_multiple_tool_calls_in_single_turn(self) -> None:
        """LLM returns multiple tool calls in one response — all executed."""
        catalog = _mock_catalog()
        settings = _make_settings()
        service = ComposerServiceImpl(catalog=catalog, settings=settings)
        state = _empty_state()

        # Turn 1: two tool calls in one response
        multi_call = _make_llm_response(
            tool_calls=[
                {
                    "id": "call_1",
                    "name": "set_source",
                    "arguments": {
                        "plugin": "csv",
                        "on_success": "t1",
                        "options": {},
                        "on_validation_failure": "quarantine",
                    },
                },
                {
                    "id": "call_2",
                    "name": "set_metadata",
                    "arguments": {"patch": {"name": "Dual Call Pipeline"}},
                },
            ],
        )
        # Turn 2: text
        text = _make_llm_response(content="Done.")

        with patch.object(service, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = [multi_call, text]
            result = await service.compose("Setup", [], state)

        assert result.state.source is not None
        assert result.state.metadata.name == "Dual Call Pipeline"
        assert result.state.version == 3  # two mutations
