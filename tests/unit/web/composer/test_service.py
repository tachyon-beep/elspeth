"""Tests for ComposerServiceImpl — LLM tool-use loop with mock LLM."""

from __future__ import annotations

import asyncio
import contextlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from elspeth.web.catalog.protocol import CatalogService
from elspeth.web.catalog.schemas import (
    PluginSchemaInfo,
    PluginSummary,
)
from elspeth.web.composer.protocol import (
    ComposerConvergenceError,
    ComposerResult,
    ComposerServiceError,
    ToolArgumentError,
)
from elspeth.web.composer.service import ComposerServiceImpl
from elspeth.web.composer.state import (
    CompositionState,
    PipelineMetadata,
)
from elspeth.web.composer.tools import ToolResult
from elspeth.web.config import WebSettings


@dataclass
class FakeFunction:
    name: str
    arguments: str


@dataclass
class FakeToolCall:
    id: str
    function: FakeFunction


@dataclass
class FakeMessage:
    content: str | None
    tool_calls: list[FakeToolCall] | None


@dataclass
class FakeChoice:
    message: FakeMessage


@dataclass
class FakeLLMResponse:
    choices: list[FakeChoice]


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
    catalog = MagicMock(spec=CatalogService)
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
) -> FakeLLMResponse:
    """Build a typed fake LiteLLM response.

    Uses typed dataclasses instead of MagicMock so tests fail if production
    code accesses an attribute that doesn't exist on the real response shape.
    """
    fake_tool_calls: list[FakeToolCall] | None = None
    if tool_calls:
        fake_tool_calls = [
            FakeToolCall(
                id=tc["id"],
                function=FakeFunction(
                    name=tc["name"],
                    arguments=json.dumps(tc["arguments"]),
                ),
            )
            for tc in tool_calls
        ]

    message = FakeMessage(content=content, tool_calls=fake_tool_calls)
    return FakeLLMResponse(choices=[FakeChoice(message=message)])


def _make_settings(**overrides: Any) -> WebSettings:
    """Build WebSettings with Pydantic-enforced defaults.

    Use keyword arguments to override specific fields for a test.
    Defaults come from the Pydantic model — no drift possible.

    data_dir defaults to /data (absolute) so test paths like
    /data/blobs/file.csv pass S2 path validation.
    """
    defaults: dict[str, Any] = {
        "data_dir": Path("/data"),
        "composer_max_composition_turns": 15,
        "composer_max_discovery_turns": 10,
        "composer_timeout_seconds": 85.0,
        "composer_rate_limit_per_minute": 10,
    }
    defaults.update(overrides)
    return WebSettings(**defaults)


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
                        "options": {"path": "/data/blobs/data.csv", "schema": {"mode": "observed"}},
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
                        "options": {"path": "/data/blobs/input.csv", "schema": {"mode": "observed"}},
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
    async def test_discovery_budget_exceeded_raises(self) -> None:
        """Discovery-only turns exhaust the discovery budget."""
        catalog = _mock_catalog()
        settings = _make_settings(composer_max_discovery_turns=1)
        service = ComposerServiceImpl(catalog=catalog, settings=settings)
        state = _empty_state()

        # Two different discovery tools to avoid cache hits
        disc1 = _make_llm_response(
            tool_calls=[{"id": "c1", "name": "list_sources", "arguments": {}}],
        )
        disc2 = _make_llm_response(
            tool_calls=[{"id": "c2", "name": "list_transforms", "arguments": {}}],
        )

        with patch.object(service, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = [disc1, disc2]
            with pytest.raises(ComposerConvergenceError) as exc_info:
                await service.compose("Loop forever", [], state)
            assert exc_info.value.budget_exhausted == "discovery"

    @pytest.mark.asyncio
    async def test_composition_budget_exceeded_raises(self) -> None:
        """Mutation turns exhaust the composition budget."""
        catalog = _mock_catalog()
        settings = _make_settings(composer_max_composition_turns=1)
        service = ComposerServiceImpl(catalog=catalog, settings=settings)
        state = _empty_state()

        mut = _make_llm_response(
            tool_calls=[
                {
                    "id": "c1",
                    "name": "set_metadata",
                    "arguments": {"patch": {"name": "test"}},
                }
            ],
        )
        # Bonus call also returns tool calls — convergence error
        mut2 = _make_llm_response(
            tool_calls=[
                {
                    "id": "c2",
                    "name": "set_metadata",
                    "arguments": {"patch": {"name": "test2"}},
                }
            ],
        )

        with patch.object(service, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = [mut, mut2]
            with pytest.raises(ComposerConvergenceError) as exc_info:
                await service.compose("Keep mutating", [], state)
            assert exc_info.value.budget_exhausted == "composition"

    @pytest.mark.asyncio
    async def test_self_correction_on_final_composition_turn_succeeds(self) -> None:
        """B-4D-3: LLM makes mutation on final turn, then text on bonus call."""
        catalog = _mock_catalog()
        settings = _make_settings(composer_max_composition_turns=1)
        service = ComposerServiceImpl(catalog=catalog, settings=settings)
        state = _empty_state()

        mut = _make_llm_response(
            tool_calls=[
                {
                    "id": "c1",
                    "name": "set_metadata",
                    "arguments": {"patch": {"name": "Final"}},
                }
            ],
        )
        text = _make_llm_response(content="Done after final correction.")

        with patch.object(service, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = [mut, text]
            result = await service.compose("Do it", [], state)

        assert result.message == "Done after final correction."
        assert result.state.metadata.name == "Final"

    @pytest.mark.asyncio
    async def test_mixed_turns_charge_correct_budgets(self) -> None:
        """Mixed discovery/mutation turns are classified independently.

        Discovery turns charge discovery budget, mutation turns charge
        composition budget. Neither exhausts the other.
        """
        catalog = _mock_catalog()
        settings = _make_settings(
            composer_max_composition_turns=2,
            composer_max_discovery_turns=2,
        )
        service = ComposerServiceImpl(catalog=catalog, settings=settings)
        state = _empty_state()

        # Turn 1: discovery (list_sources) — discovery counter = 1
        disc = _make_llm_response(
            tool_calls=[{"id": "c1", "name": "list_sources", "arguments": {}}],
        )
        # Turn 2: mutation (set_metadata) — composition counter = 1
        mut = _make_llm_response(
            tool_calls=[
                {
                    "id": "c2",
                    "name": "set_metadata",
                    "arguments": {"patch": {"name": "Works"}},
                }
            ],
        )
        # Turn 3: text response — loop terminates
        text = _make_llm_response(content="Done.")

        with patch.object(service, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = [disc, mut, text]
            result = await service.compose("Build", [], state)

        assert result.message == "Done."
        assert result.state.metadata.name == "Works"


class TestFailedMutationBudgetClassification:
    """Failed mutation tool calls must charge composition budget, not discovery."""

    @pytest.mark.asyncio
    async def test_failed_mutation_charges_composition_budget(self) -> None:
        """A mutation tool that fails with KeyError/TypeError should exhaust
        composition budget, not discovery budget."""
        catalog = _mock_catalog()
        settings = _make_settings(
            composer_max_composition_turns=1,
            composer_max_discovery_turns=10,
        )
        service = ComposerServiceImpl(catalog=catalog, settings=settings)
        state = _empty_state()

        # Turn 1: set_source with missing required key → KeyError
        # This is a mutation tool, so even though it fails, it should
        # charge composition budget (1/1 → exhausted).
        bad_mutation = _make_llm_response(
            tool_calls=[
                {
                    "id": "c1",
                    "name": "set_source",
                    "arguments": {"plugin": "csv"},  # missing on_success
                }
            ],
        )
        # Bonus call (composition exhausted gives one last chance) also
        # returns a tool call → convergence error
        bad_mutation2 = _make_llm_response(
            tool_calls=[
                {
                    "id": "c2",
                    "name": "set_source",
                    "arguments": {"plugin": "csv"},
                }
            ],
        )

        with patch.object(service, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = [bad_mutation, bad_mutation2]
            with pytest.raises(ComposerConvergenceError) as exc_info:
                await service.compose("Setup source", [], state)
            assert exc_info.value.budget_exhausted == "composition"

    @pytest.mark.asyncio
    async def test_failed_mutation_json_parse_charges_composition_budget(self) -> None:
        """Mutation tool with unparseable JSON arguments should still
        charge composition budget."""
        catalog = _mock_catalog()
        settings = _make_settings(
            composer_max_composition_turns=1,
            composer_max_discovery_turns=10,
        )
        service = ComposerServiceImpl(catalog=catalog, settings=settings)
        state = _empty_state()

        # Build a tool call with invalid JSON manually
        call = FakeToolCall(
            id="c1",
            function=FakeFunction(
                name="set_source",
                arguments="{invalid json",
            ),
        )
        msg = FakeMessage(content=None, tool_calls=[call])
        response = FakeLLMResponse(choices=[FakeChoice(message=msg)])

        # Bonus call also fails
        call2 = FakeToolCall(
            id="c2",
            function=FakeFunction(
                name="set_source",
                arguments="{still invalid",
            ),
        )
        msg2 = FakeMessage(content=None, tool_calls=[call2])
        response2 = FakeLLMResponse(choices=[FakeChoice(message=msg2)])

        with patch.object(service, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = [response, response2]
            with pytest.raises(ComposerConvergenceError) as exc_info:
                await service.compose("Setup source", [], state)
            assert exc_info.value.budget_exhausted == "composition"

    @pytest.mark.asyncio
    async def test_failed_discovery_does_not_charge_composition_budget(self) -> None:
        """A failed discovery tool should still charge discovery budget,
        not composition budget."""
        catalog = _mock_catalog()
        settings = _make_settings(
            composer_max_composition_turns=10,
            composer_max_discovery_turns=1,
        )
        service = ComposerServiceImpl(catalog=catalog, settings=settings)
        state = _empty_state()

        # list_sources with invalid JSON → still a discovery turn
        call = FakeToolCall(
            id="c1",
            function=FakeFunction(
                name="list_sources",
                arguments="{bad json",
            ),
        )
        msg = FakeMessage(content=None, tool_calls=[call])
        response = FakeLLMResponse(choices=[FakeChoice(message=msg)])

        # Turn 2: another discovery call
        disc2 = _make_llm_response(
            tool_calls=[{"id": "c2", "name": "list_transforms", "arguments": {}}],
        )

        with patch.object(service, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = [response, disc2]
            with pytest.raises(ComposerConvergenceError) as exc_info:
                await service.compose("Explore", [], state)
            assert exc_info.value.budget_exhausted == "discovery"


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

    @pytest.mark.asyncio
    async def test_wrong_type_tool_arg_returns_error(self) -> None:
        """ToolArgumentError from Tier 3 type guard in tool handler is caught, not crash.

        Tool handlers validate LLM-provided argument types at the Tier 3
        boundary, raising ToolArgumentError for wrong types (e.g. int where
        str expected). The compose loop catches this typed exception and
        feeds the error back to the LLM so it can retry with a corrected
        argument.
        """
        catalog = _mock_catalog()
        settings = _make_settings()
        service = ComposerServiceImpl(catalog=catalog, settings=settings)
        state = _empty_state()

        # Turn 1: tool call that triggers ToolArgumentError from Tier 3 type guard
        bad_call = _make_llm_response(
            tool_calls=[
                {
                    "id": "call_bad",
                    "name": "set_source",
                    "arguments": {"plugin": "csv", "on_success": "out"},
                }
            ],
        )
        # Turn 2: LLM self-corrects
        text = _make_llm_response(content="Fixed.")

        with (
            patch(
                "elspeth.web.composer.service.execute_tool",
                side_effect=ToolArgumentError("content must be a string, got int"),
            ),
            patch.object(service, "_call_llm", new_callable=AsyncMock) as mock_llm,
        ):
            mock_llm.side_effect = [bad_call, text]
            result = await service.compose("Setup", [], state)

        assert result.message == "Fixed."

    @pytest.mark.asyncio
    async def test_malformed_set_pipeline_nested_required_field_returns_error(self) -> None:
        """Nested required fields in set_pipeline stay recoverable tool errors."""
        catalog = _mock_catalog()
        settings = _make_settings()
        service = ComposerServiceImpl(catalog=catalog, settings=settings)
        state = _empty_state()

        bad_call = _make_llm_response(
            tool_calls=[
                {
                    "id": "call_bad",
                    "name": "set_pipeline",
                    "arguments": {
                        "source": {
                            "on_success": "source_out",
                            "options": {"path": "/data/in.csv", "schema": {"mode": "observed"}},
                        },
                        "nodes": [
                            {
                                "id": "t1",
                                "node_type": "transform",
                                "plugin": "uppercase",
                                "input": "source_out",
                                "on_success": "main",
                                "options": {},
                            }
                        ],
                        "edges": [
                            {
                                "id": "e1",
                                "from_node": "source",
                                "to_node": "t1",
                                "edge_type": "on_success",
                            }
                        ],
                        "outputs": [
                            {
                                "sink_name": "main",
                                "plugin": "csv",
                                "options": {"path": "/data/out.csv", "schema": {"mode": "observed"}},
                            }
                        ],
                    },
                }
            ],
        )
        text = _make_llm_response(content="Recovered.")

        with patch.object(service, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = [bad_call, text]
            result = await service.compose("Setup", [], state)

        assert result.message == "Recovered."
        tool_msg = mock_llm.call_args_list[1][0][0][-1]
        error_content = json.loads(tool_msg["content"])
        assert "source.plugin" in error_content["error"]
        assert "missing required" in error_content["error"].lower()

    @pytest.mark.asyncio
    async def test_internal_key_error_is_not_swallowed(self) -> None:
        """KeyError from tool handler internals must crash, not be sent to LLM.

        Previously, KeyError from missing LLM arguments and KeyError from
        internal bugs were both caught and fed back to the LLM. Internal
        bugs should crash immediately — the LLM cannot self-correct our code.
        """
        catalog = _mock_catalog()
        settings = _make_settings()
        service = ComposerServiceImpl(catalog=catalog, settings=settings)
        state = _empty_state()

        # Provide all required arguments so pre-validation passes,
        # but patch execute_tool to raise a KeyError from "internal logic"
        valid_call = _make_llm_response(
            tool_calls=[
                {
                    "id": "c1",
                    "name": "set_source",
                    "arguments": {
                        "plugin": "csv",
                        "on_success": "out",
                        "options": {},
                        "on_validation_failure": "quarantine",
                    },
                }
            ],
        )

        with (
            patch.object(service, "_call_llm", new_callable=AsyncMock) as mock_llm,
            patch(
                "elspeth.web.composer.service.execute_tool",
                side_effect=KeyError("internal_state_key"),
            ),
        ):
            mock_llm.return_value = valid_call
            with pytest.raises(KeyError, match="internal_state_key"):
                await service.compose("Setup", [], state)

    @pytest.mark.asyncio
    async def test_missing_args_error_message_lists_keys(self) -> None:
        """Missing required arguments should produce a clear error listing the keys."""
        catalog = _mock_catalog()
        settings = _make_settings()
        service = ComposerServiceImpl(catalog=catalog, settings=settings)
        state = _empty_state()

        # set_source requires plugin, on_success, options, on_validation_failure
        bad_call = _make_llm_response(
            tool_calls=[
                {
                    "id": "c1",
                    "name": "set_source",
                    "arguments": {"plugin": "csv"},  # missing 3 required args
                }
            ],
        )
        text = _make_llm_response(content="Ok.")

        with patch.object(service, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = [bad_call, text]
            await service.compose("Setup", [], state)

        # Verify the error message sent back to the LLM mentions the missing keys
        tool_msg = mock_llm.call_args_list[1][0][0][-1]  # last message in second call
        error_content = json.loads(tool_msg["content"])
        assert "on_success" in error_content["error"]
        assert "missing required" in error_content["error"].lower()


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
                        "options": {"path": "/data/blobs/input.csv", "schema": {"mode": "observed"}},
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


class TestDiscoveryCache:
    """Tests for the discovery cache (F1)."""

    @pytest.mark.asyncio
    async def test_cacheable_tool_returns_cached_result(self) -> None:
        """Repeated cacheable discovery calls return cached results
        without incrementing any budget counter."""
        catalog = _mock_catalog()
        settings = _make_settings(composer_max_discovery_turns=2)
        service = ComposerServiceImpl(catalog=catalog, settings=settings)
        state = _empty_state()

        # Turn 1: list_sources (first call — executes, charges discovery: 1/2)
        # Turn 2: list_sources AGAIN (cache hit — no budget charge)
        # Turn 3: text
        disc1 = _make_llm_response(
            tool_calls=[{"id": "c1", "name": "list_sources", "arguments": {}}],
        )
        disc2 = _make_llm_response(
            tool_calls=[{"id": "c2", "name": "list_sources", "arguments": {}}],
        )
        text = _make_llm_response(content="Found sources.")

        with patch.object(service, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = [disc1, disc2, text]
            result = await service.compose("List sources", [], state)

        # Should NOT have raised — second list_sources was a cache hit
        assert result.message == "Found sources."
        # Catalog list_sources is called once by build_messages (prompt
        # context) and once by execute_tool (first discovery call).
        # The second discovery call is a cache hit — no catalog call.
        # Total: 2, not 3.
        assert catalog.list_sources.call_count == 2

    @pytest.mark.asyncio
    async def test_cache_key_includes_arguments(self) -> None:
        """Different arguments = different cache entries = both execute."""
        catalog = _mock_catalog()
        settings = _make_settings()
        service = ComposerServiceImpl(catalog=catalog, settings=settings)
        state = _empty_state()

        schema1 = _make_llm_response(
            tool_calls=[
                {
                    "id": "c1",
                    "name": "get_plugin_schema",
                    "arguments": {"plugin_type": "source", "name": "csv"},
                }
            ],
        )
        schema2 = _make_llm_response(
            tool_calls=[
                {
                    "id": "c2",
                    "name": "get_plugin_schema",
                    "arguments": {"plugin_type": "source", "name": "json"},
                }
            ],
        )
        text = _make_llm_response(content="Got schemas.")

        with patch.object(service, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = [schema1, schema2, text]
            await service.compose("Get schemas", [], state)

        # Both calls should have executed (different arguments)
        assert catalog.get_schema.call_count == 2

    @pytest.mark.asyncio
    async def test_mutation_tools_never_cached(self) -> None:
        """Mutation tool results are never cached — always execute."""
        catalog = _mock_catalog()
        settings = _make_settings()
        service = ComposerServiceImpl(catalog=catalog, settings=settings)
        state = _empty_state()

        mut1 = _make_llm_response(
            tool_calls=[
                {
                    "id": "c1",
                    "name": "set_metadata",
                    "arguments": {"patch": {"name": "X"}},
                }
            ],
        )
        mut2 = _make_llm_response(
            tool_calls=[
                {
                    "id": "c2",
                    "name": "set_metadata",
                    "arguments": {"patch": {"name": "Y"}},
                }
            ],
        )
        text = _make_llm_response(content="Done.")

        with patch.object(service, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = [mut1, mut2, text]
            result = await service.compose("Update metadata", [], state)

        assert result.state.metadata.name == "Y"


class TestComposeTimeout:
    """Tests for the server-side compose timeout (F1)."""

    @pytest.mark.asyncio
    async def test_timeout_raises_convergence_error(self) -> None:
        """Exceeding composer_timeout_seconds raises ComposerConvergenceError
        with budget_exhausted='timeout'."""
        import asyncio

        catalog = _mock_catalog()
        settings = _make_settings(composer_timeout_seconds=0.1)
        service = ComposerServiceImpl(catalog=catalog, settings=settings)
        state = _empty_state()

        async def slow_llm(*args: Any, **kwargs: Any) -> Any:
            await asyncio.sleep(1.0)
            return _make_llm_response(content="Too late.")

        with patch.object(service, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = slow_llm
            with pytest.raises(ComposerConvergenceError) as exc_info:
                await service.compose("Slow pipeline", [], state)
            assert exc_info.value.budget_exhausted == "timeout"

    @pytest.mark.asyncio
    async def test_mutation_tool_state_preserved_on_timeout(self) -> None:
        """Mutation tools that complete before timeout must have their
        state reflected in partial_state.

        Regression test for the cancel-safety concern: with cooperative
        timeout, the deadline is checked AFTER tool execution completes,
        so side effects and state publication are never split. The
        partial_state must include the mutation that completed.
        """
        import time

        catalog = _mock_catalog()
        # Very tight timeout — tool execution will consume most of it
        settings = _make_settings(composer_timeout_seconds=0.5)
        service = ComposerServiceImpl(catalog=catalog, settings=settings)
        state = _empty_state()

        call_count = 0

        def _slow_mutation_tool(
            _tool_name: str,
            _arguments: dict[str, Any],
            current_state: CompositionState,
            _catalog: Any,
            **kwargs: Any,
        ) -> ToolResult:
            # Simulate a blob mutation that takes time
            time.sleep(0.2)
            from elspeth.web.composer.state import SourceSpec

            new_state = current_state.with_source(
                SourceSpec(
                    plugin="csv",
                    on_success="out",
                    options={"path": "/data/blobs/f.csv", "schema": {"mode": "observed"}},
                    on_validation_failure="quarantine",
                )
            )
            return ToolResult(
                success=True,
                updated_state=new_state,
                validation=new_state.validate(),
                affected_nodes=("source",),
                data=None,
            )

        async def slow_then_timeout_llm(*args: Any, **kwargs: Any) -> Any:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call: return tool call (fast)
                return _make_llm_response(
                    tool_calls=[
                        {
                            "id": "c1",
                            "name": "set_source",
                            "arguments": {
                                "plugin": "csv",
                                "on_success": "out",
                                "options": {"path": "/data/blobs/f.csv", "schema": {"mode": "observed"}},
                                "on_validation_failure": "quarantine",
                            },
                        }
                    ],
                )
            # Second call: will exceed remaining deadline
            await asyncio.sleep(5.0)
            return _make_llm_response(content="Too late.")

        with (
            patch.object(service, "_call_llm", new_callable=AsyncMock) as mock_llm,
            patch(
                "elspeth.web.composer.service.execute_tool",
                side_effect=_slow_mutation_tool,
            ),
        ):
            mock_llm.side_effect = slow_then_timeout_llm
            with pytest.raises(ComposerConvergenceError) as exc_info:
                await service.compose("Build pipeline", [], state)

        assert exc_info.value.budget_exhausted == "timeout"
        # The mutation tool completed BEFORE the timeout fired on the
        # second LLM call.  With cooperative timeout, partial_state must
        # reflect the completed mutation.
        assert exc_info.value.partial_state is not None, (
            "partial_state is None — mutation tool's state was lost on timeout. "
            "This is the cancel-safety regression: side effects committed but "
            "state was not published."
        )
        assert exc_info.value.partial_state.source is not None
        assert exc_info.value.partial_state.source.plugin == "csv"


class TestPartialStatePreservation:
    """Tests for partial state preservation on convergence failure (F2)."""

    @pytest.mark.asyncio
    async def test_convergence_includes_partial_state_when_mutated(self) -> None:
        """When mutations occurred before convergence failure,
        partial_state is attached to the exception."""
        catalog = _mock_catalog()
        settings = _make_settings(composer_max_composition_turns=1)
        service = ComposerServiceImpl(catalog=catalog, settings=settings)
        state = _empty_state()

        # Turn 1: mutation (set_source) — composition budget exhausted (1/1)
        mut = _make_llm_response(
            tool_calls=[
                {
                    "id": "c1",
                    "name": "set_source",
                    "arguments": {
                        "plugin": "csv",
                        "on_success": "t1",
                        "options": {"path": "/data/blobs/input.csv", "schema": {"mode": "observed"}},
                        "on_validation_failure": "quarantine",
                    },
                }
            ],
        )
        # Bonus call also returns tool calls — convergence error
        mut2 = _make_llm_response(
            tool_calls=[
                {
                    "id": "c2",
                    "name": "set_metadata",
                    "arguments": {"patch": {"name": "nope"}},
                }
            ],
        )

        with patch.object(service, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = [mut, mut2]
            with pytest.raises(ComposerConvergenceError) as exc_info:
                await service.compose("Build pipeline", [], state)

            assert exc_info.value.partial_state is not None
            assert exc_info.value.partial_state.source is not None
            assert exc_info.value.partial_state.source.plugin == "csv"
            assert exc_info.value.partial_state.version == 2

    @pytest.mark.asyncio
    async def test_convergence_no_partial_state_when_no_mutations(self) -> None:
        """When no mutations occurred, partial_state is None."""
        catalog = _mock_catalog()
        settings = _make_settings(composer_max_discovery_turns=1)
        service = ComposerServiceImpl(catalog=catalog, settings=settings)
        state = _empty_state()

        disc1 = _make_llm_response(
            tool_calls=[{"id": "c1", "name": "list_sources", "arguments": {}}],
        )
        disc2 = _make_llm_response(
            tool_calls=[{"id": "c2", "name": "list_transforms", "arguments": {}}],
        )

        with patch.object(service, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = [disc1, disc2]
            with pytest.raises(ComposerConvergenceError) as exc_info:
                await service.compose("Just looking", [], state)

            assert exc_info.value.partial_state is None


class TestEmptyChoicesValidation:
    """Tier 3 boundary: LiteLLM can return empty choices."""

    @pytest.mark.asyncio
    async def test_empty_choices_raises_service_error(self) -> None:
        """LiteLLM returning empty choices must raise ComposerServiceError.

        Empty choices can occur on content-filter blocks, rate-limit
        responses, or malformed upstream responses.  Without validation,
        this causes an IndexError at response.choices[0].message.
        """
        catalog = _mock_catalog()
        settings = _make_settings()
        service = ComposerServiceImpl(catalog=catalog, settings=settings)
        state = _empty_state()

        # Patch litellm.acompletion (not _call_llm) so the validation
        # inside _call_llm is exercised through the production code path.
        empty_response = FakeLLMResponse(choices=[])
        with (
            patch(
                "elspeth.web.composer.service.litellm.acompletion",
                new_callable=AsyncMock,
                return_value=empty_response,
            ),
            pytest.raises(ComposerServiceError, match="empty choices"),
        ):
            await service.compose("Hello", [], state)

    @pytest.mark.asyncio
    async def test_empty_choices_on_bonus_turn_raises_service_error(self) -> None:
        """Empty choices on the bonus turn (budget exhaustion) also raises.

        The bonus turn at composition budget exhaustion goes through the
        same _call_llm() path, so the validation protects both sites.
        """
        catalog = _mock_catalog()
        # Budget of 1 composition turn — first mutation exhausts it,
        # then the bonus _call_llm returns empty choices.
        settings = _make_settings(composer_max_composition_turns=1)
        service = ComposerServiceImpl(catalog=catalog, settings=settings)
        state = _empty_state()

        # First call: valid response with a mutation tool call
        mutation_call = _make_llm_response(
            tool_calls=[
                {
                    "id": "c1",
                    "name": "set_source",
                    "arguments": {
                        "plugin": "csv",
                        "on_success": "out",
                        "options": {},
                        "on_validation_failure": "quarantine",
                    },
                }
            ],
        )
        # Second call (bonus turn): empty choices
        empty_response = FakeLLMResponse(choices=[])

        with (
            patch(
                "elspeth.web.composer.service.litellm.acompletion",
                new_callable=AsyncMock,
                side_effect=[mutation_call, empty_response],
            ) as mock_acomp,
            pytest.raises(ComposerServiceError, match="empty choices"),
        ):
            await service.compose("Setup CSV", [], state)

        # Confirm both LLM calls happened — the error is from the bonus
        # turn (second call), not from a tool handler fault on the first.
        assert mock_acomp.call_count == 2


class TestPluginBugCrashesFromToolExecution:
    """Plugin-internal TypeError/ValueError/UnicodeError must crash.

    The compose loop catches ONLY ToolArgumentError around execute_tool.
    Any other TypeError/ValueError/UnicodeError is a plugin bug — per
    CLAUDE.md, silently laundering a plugin bug as an LLM-argument error
    is worse than crashing, because the audit trail records a confident
    but wrong Tier-3 story.

    Mirrors test_internal_key_error_is_not_swallowed.
    """

    @pytest.mark.asyncio
    async def test_plugin_value_error_is_not_swallowed(self) -> None:
        catalog = _mock_catalog()
        settings = _make_settings()
        service = ComposerServiceImpl(catalog=catalog, settings=settings)
        state = _empty_state()

        valid_call = _make_llm_response(
            tool_calls=[
                {
                    "id": "c1",
                    "name": "set_source",
                    "arguments": {
                        "plugin": "csv",
                        "on_success": "out",
                        "options": {},
                        "on_validation_failure": "quarantine",
                    },
                }
            ],
        )

        with (
            patch.object(service, "_call_llm", new_callable=AsyncMock) as mock_llm,
            patch(
                "elspeth.web.composer.service.execute_tool",
                side_effect=ValueError("invalid expression syntax — plugin bug"),
            ),
        ):
            mock_llm.return_value = valid_call
            with pytest.raises(ValueError, match="plugin bug"):
                await service.compose("Setup", [], state)

    @pytest.mark.asyncio
    async def test_plugin_type_error_is_not_swallowed(self) -> None:
        catalog = _mock_catalog()
        settings = _make_settings()
        service = ComposerServiceImpl(catalog=catalog, settings=settings)
        state = _empty_state()

        valid_call = _make_llm_response(
            tool_calls=[
                {
                    "id": "c1",
                    "name": "set_source",
                    "arguments": {
                        "plugin": "csv",
                        "on_success": "out",
                        "options": {},
                        "on_validation_failure": "quarantine",
                    },
                }
            ],
        )

        with (
            patch.object(service, "_call_llm", new_callable=AsyncMock) as mock_llm,
            patch(
                "elspeth.web.composer.service.execute_tool",
                side_effect=TypeError("NoneType + int — plugin bug"),
            ),
        ):
            mock_llm.return_value = valid_call
            with pytest.raises(TypeError, match="plugin bug"):
                await service.compose("Setup", [], state)

    @pytest.mark.asyncio
    async def test_plugin_unicode_error_is_not_swallowed(self) -> None:
        catalog = _mock_catalog()
        settings = _make_settings()
        service = ComposerServiceImpl(catalog=catalog, settings=settings)
        state = _empty_state()

        valid_call = _make_llm_response(
            tool_calls=[
                {
                    "id": "c1",
                    "name": "set_source",
                    "arguments": {
                        "plugin": "csv",
                        "on_success": "out",
                        "options": {},
                        "on_validation_failure": "quarantine",
                    },
                }
            ],
        )

        with (
            patch.object(service, "_call_llm", new_callable=AsyncMock) as mock_llm,
            patch(
                "elspeth.web.composer.service.execute_tool",
                side_effect=UnicodeDecodeError("utf-8", b"\xff", 0, 1, "plugin bug"),
            ),
        ):
            mock_llm.return_value = valid_call
            with pytest.raises(UnicodeDecodeError):
                await service.compose("Setup", [], state)

    @pytest.mark.asyncio
    async def test_tool_argument_error_is_caught_and_fed_to_llm(self) -> None:
        """Positive case: ToolArgumentError IS caught, error fed back for LLM retry."""
        catalog = _mock_catalog()
        settings = _make_settings()
        service = ComposerServiceImpl(catalog=catalog, settings=settings)
        state = _empty_state()

        valid_call = _make_llm_response(
            tool_calls=[
                {
                    "id": "c1",
                    "name": "set_source",
                    "arguments": {
                        "plugin": "csv",
                        "on_success": "out",
                        "options": {},
                        "on_validation_failure": "quarantine",
                    },
                }
            ],
        )
        text = _make_llm_response(content="Got it, trying again.")

        with (
            patch.object(service, "_call_llm", new_callable=AsyncMock) as mock_llm,
            patch(
                "elspeth.web.composer.service.execute_tool",
                side_effect=ToolArgumentError("plugin expected str, got int"),
            ),
        ):
            mock_llm.side_effect = [valid_call, text]
            result = await service.compose("Setup", [], state)

        assert isinstance(result, ComposerResult)
        second_call_messages = mock_llm.call_args_list[1].args[0]
        tool_messages = [m for m in second_call_messages if m.get("role") == "tool"]
        assert len(tool_messages) == 1
        error_payload = json.loads(tool_messages[0]["content"])
        assert "plugin expected str, got int" in error_payload["error"]

    @pytest.mark.asyncio
    async def test_tool_argument_error_subclass_cannot_leak_cause_to_llm(self) -> None:
        """Defense-in-depth: if a subclass overrides __str__ to embed the
        __cause__ chain, the LLM-echo path must still use args[0] only.

        Simulates a future regression where a helpful-looking subclass does
        `def __str__(self): return f"{self.args[0]}: caused by {self.__cause__}"`.
        A DB URL or file path leaked through __cause__ would then reach the
        LLM API. The compose loop MUST short-circuit __str__ and emit
        args[0] verbatim, isolating the cause chain to __cause__ (audit-only).
        """

        class LeakyToolArgumentError(ToolArgumentError):
            def __str__(self) -> str:
                return f"{self.args[0]}: caused by {self.__cause__}"

        catalog = _mock_catalog()
        settings = _make_settings()
        service = ComposerServiceImpl(catalog=catalog, settings=settings)
        state = _empty_state()

        secret_path = "/etc/elspeth/secrets/bootstrap.key"
        secret_cause = ValueError(f"bad path: {secret_path}")
        leaky = LeakyToolArgumentError("content must be a string, got int")
        leaky.__cause__ = secret_cause

        valid_call = _make_llm_response(
            tool_calls=[
                {
                    "id": "c1",
                    "name": "set_source",
                    "arguments": {
                        "plugin": "csv",
                        "on_success": "out",
                        "options": {},
                        "on_validation_failure": "quarantine",
                    },
                }
            ],
        )
        text = _make_llm_response(content="Got it.")

        with (
            patch.object(service, "_call_llm", new_callable=AsyncMock) as mock_llm,
            patch(
                "elspeth.web.composer.service.execute_tool",
                side_effect=leaky,
            ),
        ):
            mock_llm.side_effect = [valid_call, text]
            await service.compose("Setup", [], state)

        second_call_messages = mock_llm.call_args_list[1].args[0]
        tool_messages = [m for m in second_call_messages if m.get("role") == "tool"]
        assert len(tool_messages) == 1
        error_payload = json.loads(tool_messages[0]["content"])
        assert "content must be a string, got int" in error_payload["error"]
        # The crucial assertion: the cause-chain content NEVER appears.
        assert secret_path not in error_payload["error"]
        assert "caused by" not in error_payload["error"]


class TestPluginCrashSessionPersistence:
    """Plugin-bug crash must leave a durable session-row breadcrumb.

    "No silent drops" for session records: a plugin crash that leaves
    the session in no recorded terminal state is as bad for audit
    integrity as the laundering behaviour this plan eliminates.

    Given the current sessions_table schema (no status / crashed_at /
    last_exc_class columns), the breadcrumb is a bump of updated_at.
    This test asserts that bump, plus the invariant that NO exception
    message leaks into any column. The follow-up filigree issue tracks
    the schema migration that adds richer crash markers.
    """

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path: Path) -> None:
        from datetime import UTC, datetime
        from uuid import uuid4

        from sqlalchemy.pool import StaticPool

        from elspeth.web.sessions.engine import create_session_engine
        from elspeth.web.sessions.migrations import run_migrations
        from elspeth.web.sessions.models import sessions_table

        self.engine = create_session_engine(
            "sqlite:///:memory:",
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
        run_migrations(self.engine)

        self.session_id = str(uuid4())
        self.data_dir = tmp_path
        # Seed the sessions row with a DELIBERATELY OLD updated_at so the
        # crash-path bump is unambiguously distinguishable from the seed.
        self.seeded_at = datetime(2020, 1, 1, tzinfo=UTC)
        with self.engine.begin() as conn:
            conn.execute(
                sessions_table.insert().values(
                    id=self.session_id,
                    user_id="test-user",
                    auth_provider_type="local",
                    title="Test",
                    created_at=self.seeded_at,
                    updated_at=self.seeded_at,
                )
            )

    @pytest.mark.asyncio
    async def test_plugin_crash_bumps_session_updated_at(self) -> None:
        from elspeth.web.sessions.models import sessions_table

        catalog = _mock_catalog()
        settings = _make_settings(data_dir=self.data_dir)
        service = ComposerServiceImpl(
            catalog=catalog,
            settings=settings,
            session_engine=self.engine,
        )
        state = _empty_state()

        valid_call = _make_llm_response(
            tool_calls=[
                {
                    "id": "c1",
                    "name": "set_source",
                    "arguments": {
                        "plugin": "csv",
                        "on_success": "out",
                        "options": {},
                        "on_validation_failure": "quarantine",
                    },
                }
            ],
        )

        with (
            patch.object(service, "_call_llm", new_callable=AsyncMock) as mock_llm,
            patch(
                "elspeth.web.composer.service.execute_tool",
                side_effect=ValueError("plugin bug: /etc/secrets/bootstrap.key is bad"),
            ),
        ):
            mock_llm.return_value = valid_call
            with pytest.raises(ValueError, match="plugin bug"):
                await service.compose("Setup", [], state, session_id=self.session_id)

        # Assertion 1: session row was touched on the crash path.
        with self.engine.begin() as conn:
            row = conn.execute(sessions_table.select().where(sessions_table.c.id == self.session_id)).one()

        # SQLite DateTime(timezone=True) strips tzinfo on read — normalize
        # both sides of the comparison to the same tz-naive representation.
        row_updated_at = row.updated_at
        if row_updated_at.tzinfo is None:
            seed_for_compare = self.seeded_at.replace(tzinfo=None)
        else:
            seed_for_compare = self.seeded_at
        assert row_updated_at > seed_for_compare, "crash path must bump updated_at as audit breadcrumb"

        # Assertion 2: NO column holds the exception message. Stringify
        # the entire row and verify secret fragments / class hints are
        # absent. This is the load-bearing audit-integrity invariant —
        # if a future refactor adds a 'last_error' column, the assertion
        # will catch any attempt to persist the raw message.
        row_text = " | ".join(str(v) for v in row._mapping.values())
        assert "plugin bug" not in row_text
        assert "/etc/secrets" not in row_text
        assert "ValueError" not in row_text

    @pytest.mark.asyncio
    async def test_persist_crashed_session_failure_does_not_mask_plugin_bug(
        self,
    ) -> None:
        """If _persist_crashed_session itself raises, slog.error fires and
        the original plugin-bug exception still propagates unchanged.

        Two invariants asserted:
        1. The ORIGINAL ValueError reaches the caller (not the RuntimeError
           from the persistence failure).
        2. slog.error is called with the `composer_crash_persistence_failed`
           event — guarantees that an accidental removal of Step 4a-pre's
           structlog import would be caught (without this assertion, a
           regression where slog.error silently fails as NameError would
           pass the test because the original exception still propagates).
        """
        from structlog.testing import capture_logs

        catalog = _mock_catalog()
        settings = _make_settings(data_dir=self.data_dir)
        service = ComposerServiceImpl(
            catalog=catalog,
            settings=settings,
            session_engine=self.engine,
        )
        state = _empty_state()

        valid_call = _make_llm_response(
            tool_calls=[
                {
                    "id": "c1",
                    "name": "set_source",
                    "arguments": {
                        "plugin": "csv",
                        "on_success": "out",
                        "options": {},
                        "on_validation_failure": "quarantine",
                    },
                }
            ],
        )

        with (
            patch.object(service, "_call_llm", new_callable=AsyncMock) as mock_llm,
            patch(
                "elspeth.web.composer.service.execute_tool",
                side_effect=ValueError("original plugin bug"),
            ),
            patch.object(
                service,
                "_persist_crashed_session",
                side_effect=RuntimeError("persistence failed"),
            ),
            capture_logs() as cap_logs,
        ):
            mock_llm.return_value = valid_call
            with pytest.raises(ValueError, match="original plugin bug"):
                await service.compose("Setup", [], state, session_id=self.session_id)

        # The crash-persistence-failure slog.error MUST fire. This closes
        # the regression risk where Step 4a-pre's structlog import is
        # accidentally removed — the method would then raise NameError
        # inside the except, masking the original ValueError.
        persistence_failure_events = [entry for entry in cap_logs if entry.get("event") == "composer_crash_persistence_failed"]
        assert len(persistence_failure_events) == 1, cap_logs
        event = persistence_failure_events[0]
        assert event["session_id"] == self.session_id
        assert event["original_exc_class"] == "ValueError"
        # Exception message MUST NOT appear in structured fields — only
        # in exc_info (stderr traceback).
        assert "original plugin bug" not in str(event)

    @pytest.mark.asyncio
    async def test_persist_crashed_session_real_path_slog_emission(self) -> None:
        """Smoke test for Step 4a-pre: exercise the real _persist_crashed_session
        path (no patching of the private method).  If structlog is not
        imported in service.py, this test will surface the NameError that
        `test_persist_crashed_session_failure_does_not_mask_plugin_bug`
        misses (because that test patches the method itself).

        The real _persist_crashed_session should succeed here (the sessions
        engine is live), so we assert the crash propagates without any
        persistence-failure slog event.
        """
        from structlog.testing import capture_logs

        catalog = _mock_catalog()
        settings = _make_settings(data_dir=self.data_dir)
        service = ComposerServiceImpl(
            catalog=catalog,
            settings=settings,
            session_engine=self.engine,
        )
        state = _empty_state()

        valid_call = _make_llm_response(
            tool_calls=[
                {
                    "id": "c1",
                    "name": "set_source",
                    "arguments": {
                        "plugin": "csv",
                        "on_success": "out",
                        "options": {},
                        "on_validation_failure": "quarantine",
                    },
                }
            ],
        )

        with (
            patch.object(service, "_call_llm", new_callable=AsyncMock) as mock_llm,
            patch(
                "elspeth.web.composer.service.execute_tool",
                side_effect=ValueError("plugin bug"),
            ),
            capture_logs() as cap_logs,
        ):
            mock_llm.return_value = valid_call
            with pytest.raises(ValueError, match="plugin bug"):
                await service.compose("Setup", [], state, session_id=self.session_id)

        # No persistence-failure event — the real path succeeded.
        persistence_failure_events = [entry for entry in cap_logs if entry.get("event") == "composer_crash_persistence_failed"]
        assert persistence_failure_events == [], cap_logs


class TestToolExecutionThreadOffloading:
    """execute_tool() must run in a worker thread, not the event loop thread.

    Tests capture actual thread identity rather than checking whether
    asyncio.to_thread was called — testing the behavioral property
    (event loop not blocked) regardless of the offloading mechanism.
    """

    @staticmethod
    async def _assert_tool_runs_off_event_loop(
        tool_call_response: FakeLLMResponse,
        text_response: FakeLLMResponse,
        user_message: str,
    ) -> None:
        """Shared helper: verify a tool call executes in a worker thread."""
        import threading

        catalog = _mock_catalog()
        settings = _make_settings()
        service = ComposerServiceImpl(catalog=catalog, settings=settings)
        state = _empty_state()

        event_loop_thread = threading.current_thread()
        tool_execution_thread: threading.Thread | None = None

        def _capture_thread(
            _tool_name: str,
            _arguments: dict[str, Any],
            current_state: CompositionState,
            _catalog: Any,
            **kwargs: Any,
        ) -> ToolResult:
            nonlocal tool_execution_thread
            tool_execution_thread = threading.current_thread()
            return ToolResult(
                success=True,
                updated_state=current_state,
                validation=current_state.validate(),
                affected_nodes=(),
                data={"sources": []},
            )

        with (
            patch.object(service, "_call_llm", new_callable=AsyncMock) as mock_llm,
            patch(
                "elspeth.web.composer.service.execute_tool",
                side_effect=_capture_thread,
            ),
        ):
            mock_llm.side_effect = [tool_call_response, text_response]
            await service.compose(user_message, [], state)

        assert tool_execution_thread is not None, "execute_tool was never called"
        assert tool_execution_thread is not event_loop_thread, (
            "execute_tool ran on the event loop thread — must be offloaded to a worker thread to avoid blocking"
        )

    @pytest.mark.asyncio
    async def test_discovery_tool_runs_off_event_loop_thread(self) -> None:
        """Discovery tools run in a worker thread (read-only I/O)."""
        await self._assert_tool_runs_off_event_loop(
            tool_call_response=_make_llm_response(
                tool_calls=[{"id": "c1", "name": "list_sources", "arguments": {}}],
            ),
            text_response=_make_llm_response(content="Here are the sources."),
            user_message="List sources",
        )

    @pytest.mark.asyncio
    async def test_mutation_tool_runs_off_event_loop_thread(self) -> None:
        """Mutation tools run in a worker thread (blob/secret I/O).

        Previously only discovery tools were offloaded; mutation tools
        ran synchronously on the event loop, blocking all concurrent
        requests in the single-process server.
        """
        await self._assert_tool_runs_off_event_loop(
            tool_call_response=_make_llm_response(
                tool_calls=[
                    {
                        "id": "c1",
                        "name": "set_source",
                        "arguments": {
                            "plugin": "csv",
                            "on_success": "out",
                            "options": {"path": "/data/blobs/f.csv", "schema": {"mode": "observed"}},
                            "on_validation_failure": "quarantine",
                        },
                    }
                ],
            ),
            text_response=_make_llm_response(content="Source configured."),
            user_message="Set CSV source",
        )

    @pytest.mark.asyncio
    async def test_event_loop_not_blocked_during_tool_execution(self) -> None:
        """Heartbeat regression: compose() must not block the event loop.

        Runs compose() alongside an async heartbeat coroutine. If the
        heartbeat fires on schedule (not delayed by blocking tool work),
        the event loop was free during tool execution.
        """
        import time

        catalog = _mock_catalog()
        settings = _make_settings()
        service = ComposerServiceImpl(catalog=catalog, settings=settings)
        state = _empty_state()

        # Blocking duration must be much larger than the gap threshold
        # to avoid false positives on slow/shared CI runners where OS
        # scheduler jitter can delay asyncio.sleep wakeups by 50-100ms.
        tool_block_seconds = 1.0
        heartbeat_interval = 0.05

        def _blocking_tool(
            _tool_name: str,
            _arguments: dict[str, Any],
            current_state: CompositionState,
            _catalog: Any,
            **kwargs: Any,
        ) -> ToolResult:
            time.sleep(tool_block_seconds)
            return ToolResult(
                success=True,
                updated_state=current_state,
                validation=current_state.validate(),
                affected_nodes=("source",),
                data=None,
            )

        heartbeat_times: list[float] = []

        async def heartbeat() -> None:
            while True:
                heartbeat_times.append(time.monotonic())
                await asyncio.sleep(heartbeat_interval)

        # Use a mutation tool — the original bug was specifically about
        # mutation tools running synchronously on the event loop.
        tool_call = _make_llm_response(
            tool_calls=[
                {
                    "id": "c1",
                    "name": "set_source",
                    "arguments": {
                        "plugin": "csv",
                        "on_success": "out",
                        "options": {"path": "/data/blobs/f.csv", "schema": {"mode": "observed"}},
                        "on_validation_failure": "quarantine",
                    },
                }
            ],
        )
        text = _make_llm_response(content="Done.")

        with (
            patch.object(service, "_call_llm", new_callable=AsyncMock) as mock_llm,
            patch(
                "elspeth.web.composer.service.execute_tool",
                side_effect=_blocking_tool,
            ),
        ):
            mock_llm.side_effect = [tool_call, text]
            hb_task = asyncio.create_task(heartbeat())
            try:
                await service.compose("List sources", [], state)
            finally:
                hb_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await hb_task

        # With 1.0s block and 50ms interval we expect ~20 heartbeats.
        # Require at least 4 to catch partial stalls, not just total seizure.
        min_expected = int(tool_block_seconds / heartbeat_interval) - 2
        assert len(heartbeat_times) >= min(min_expected, 4), (
            f"Only {len(heartbeat_times)} heartbeat(s) fired during {tool_block_seconds}s tool execution — event loop was likely blocked"
        )

        # Check that no heartbeat interval exceeds a generous threshold.
        # If the event loop were blocked, one interval would be ≈ tool_block_seconds.
        # The 5x multiplier (250ms) gives wide margin for OS scheduler jitter
        # on shared CI runners while still catching a 1.0s event loop block.
        max_allowed_gap = heartbeat_interval * 5  # 250ms threshold vs 1.0s block (4x safety)
        for i in range(1, len(heartbeat_times)):
            gap = heartbeat_times[i] - heartbeat_times[i - 1]
            assert gap < max_allowed_gap, (
                f"Heartbeat gap {gap:.3f}s exceeds {max_allowed_gap:.3f}s — event loop was blocked (tool takes {tool_block_seconds}s)"
            )


class TestToolArgumentError:
    """ToolArgumentError is a composer-domain exception for Tier-3 boundary failures.

    It signals that a tool handler received arguments of the wrong type or
    with semantically invalid values that could not be coerced. The compose
    loop catches this and feeds the message back to the LLM for retry. Any
    OTHER exception escaping execute_tool is a plugin bug and must crash.
    """

    def test_inherits_from_exception_directly_not_composer_service_error(self) -> None:
        """ToolArgumentError must NOT inherit from ComposerServiceError.

        If it did, the route-level `except ComposerServiceError` block at
        routes.py:390 would silently absorb any escaped ToolArgumentError
        as a 502, recreating the silent-laundering channel this plan closes.
        Inheriting from Exception directly ensures an escaped
        ToolArgumentError (a compose-loop bug) surfaces loudly via FastAPI's
        default handler rather than being masked.
        """
        assert issubclass(ToolArgumentError, Exception)
        assert not issubclass(ToolArgumentError, ComposerServiceError)

    def test_message_preserved(self) -> None:
        """Constructor accepts a message string; str() returns it unchanged."""
        exc = ToolArgumentError("content must be a string, got int")
        assert str(exc) == "content must be a string, got int"

    def test_supports_exception_chaining(self) -> None:
        """raise ToolArgumentError(...) from exc must preserve __cause__.

        Audit-grade error reporting depends on the cause chain surviving
        asyncio.to_thread re-raise and the service-level catch.
        """
        original = ValueError("bad input")
        try:
            try:
                raise original
            except ValueError as exc:
                raise ToolArgumentError("wrapped") from exc
        except ToolArgumentError as wrapped:
            assert wrapped.__cause__ is original


class TestToolArgumentErrorAcrossThreadBoundary:
    """End-to-end: ToolArgumentError raised inside the worker thread is caught
    correctly by the service-level catch, with message preserved.

    Closes the sleepy-assertion gap in the mocked service-level tests
    (which raise synchronously on the mock and never exercise the real
    asyncio.to_thread re-raise path).
    """

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path: Path) -> None:
        from datetime import UTC, datetime
        from uuid import uuid4

        from sqlalchemy.pool import StaticPool

        from elspeth.web.sessions.engine import create_session_engine
        from elspeth.web.sessions.migrations import run_migrations
        from elspeth.web.sessions.models import sessions_table

        self.engine = create_session_engine(
            "sqlite:///:memory:",
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
        run_migrations(self.engine)

        self.session_id = str(uuid4())
        self.data_dir = tmp_path
        now = datetime.now(UTC)
        with self.engine.begin() as conn:
            conn.execute(
                sessions_table.insert().values(
                    id=self.session_id,
                    user_id="test-user",
                    auth_provider_type="local",
                    title="Test",
                    created_at=now,
                    updated_at=now,
                )
            )

    @pytest.mark.asyncio
    async def test_real_create_blob_type_guard_feeds_error_to_llm(self) -> None:
        catalog = _mock_catalog()
        settings = _make_settings(data_dir=self.data_dir)
        service = ComposerServiceImpl(
            catalog=catalog,
            settings=settings,
            session_engine=self.engine,
        )
        state = _empty_state()

        bad_call = _make_llm_response(
            tool_calls=[
                {
                    "id": "call_bad",
                    "name": "create_blob",
                    "arguments": {
                        "filename": "x.txt",
                        "mime_type": "text/plain",
                        "content": 42,  # wrong type
                    },
                }
            ],
        )
        text = _make_llm_response(content="Fixed.")

        with patch.object(service, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = [bad_call, text]
            result = await service.compose("Setup", [], state, session_id=self.session_id)

        assert result.message == "Fixed."
        second_call_messages = mock_llm.call_args_list[1].args[0]
        tool_messages = [m for m in second_call_messages if m.get("role") == "tool"]
        assert len(tool_messages) == 1
        error_content = json.loads(tool_messages[0]["content"])
        assert "content must be a string" in error_content["error"]
