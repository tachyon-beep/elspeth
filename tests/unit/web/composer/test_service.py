"""Tests for ComposerServiceImpl — LLM tool-use loop with mock LLM."""

from __future__ import annotations

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
from elspeth.web.composer.protocol import ComposerConvergenceError, ComposerResult
from elspeth.web.composer.service import ComposerServiceImpl
from elspeth.web.composer.state import (
    CompositionState,
    PipelineMetadata,
)
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
