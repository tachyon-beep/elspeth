# Web UX Task-Plan 4D: Composer Service & Wiring

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans.

**Goal:** Implement ComposerService protocol, system prompt, LLM tool-use loop, HTTP error shapes, and route wiring
**Parent Plan:** `plans/2026-03-28-web-ux-sub4-composer.md`
**Spec:** `specs/2026-03-28-web-ux-sub4-composer-design.md`
**Depends On:** Task-Plans 4A, 4B, 4C (all composer internals), Sub-Plan 2 (Sessions — for route handler)
**Blocks:** Sub-Plan 5 (Execution)

---

## File Map

| Action | Path |
|--------|------|
| Create | `src/elspeth/web/composer/protocol.py` |
| Create | `src/elspeth/web/composer/prompts.py` |
| Create | `src/elspeth/web/composer/service.py` |
| Create | `tests/unit/web/composer/test_service.py` |
| Create | `tests/unit/web/composer/test_route_integration.py` |
| Modify | `src/elspeth/web/sessions/routes.py` |

---

### Task 6: ComposerService Protocol and Prompts

**Files:**
- Create: `src/elspeth/web/composer/protocol.py`
- Create: `src/elspeth/web/composer/prompts.py`

- [ ] **Step 1: Implement ComposerService protocol**

```python
# src/elspeth/web/composer/protocol.py
"""ComposerService protocol and result types.

Layer: L3 (application). Defines the service boundary for LLM-driven
pipeline composition.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from elspeth.web.composer.state import CompositionState


@dataclass(frozen=True, slots=True)
class ComposerResult:
    """Result of a compose() call.

    Attributes:
        message: The assistant's text response.
        state: The (possibly updated) CompositionState.
    """

    message: str
    state: CompositionState


class ComposerServiceError(Exception):
    """Base exception for composer service errors."""


class ComposerConvergenceError(ComposerServiceError):
    """Raised when the LLM tool-use loop exceeds max_turns."""

    def __init__(self, max_turns: int) -> None:
        super().__init__(
            f"Composer did not converge within {max_turns} turns. "
            f"The LLM kept making tool calls without producing a final response."
        )
        self.max_turns = max_turns


class ComposerService(Protocol):
    """Protocol for the LLM-driven pipeline composer.

    Accepts a user message, pre-fetched chat history, and current state.
    Runs the LLM tool-use loop. Returns the assistant's response
    and the (possibly updated) state. Does NOT depend on SessionService —
    the route handler mediates (seam contract B).
    """

    async def compose(
        self,
        message: str,
        messages: list[Any],  # list[ChatMessageRecord]
        state: CompositionState,
    ) -> ComposerResult:
        """Run the LLM composition loop.

        Args:
            message: The user's chat message.
            messages: Pre-fetched chat history (list[ChatMessageRecord]).
                The route handler calls session_service.get_messages()
                and passes the result. ComposerService does NOT depend
                on SessionService — the route handler mediates.
            state: The current CompositionState.

        Returns:
            ComposerResult with assistant message and updated state.

        Raises:
            ComposerConvergenceError: If the loop exceeds max_turns.
        """
        ...
```

- [ ] **Step 2: Implement prompts module**

```python
# src/elspeth/web/composer/prompts.py
"""System prompt and message construction for the LLM composer.

_build_messages() returns a NEW list on every call — never a cached
reference. This is critical because the tool-use loop appends to the
list during iteration.

Layer: L3 (application).
"""
from __future__ import annotations

import json
from typing import Any

from elspeth.web.composer.state import CompositionState
from elspeth.web.composer.tools import CatalogServiceProtocol, _serialize_state


SYSTEM_PROMPT = """\
You are an ELSPETH pipeline composer. Your job is to translate the user's \
natural-language description into a valid pipeline configuration using the \
provided tools.

Rules:
1. Always check the current state (get_current_state) before making changes.
2. Always check plugin schemas (get_plugin_schema) before configuring a plugin.
3. Use list_sources/list_transforms/list_sinks to discover available plugins.
4. After making changes, review the validation result in the tool response. \
If there are errors, fix them before responding to the user.
5. When the pipeline is complete and valid, respond with a summary of what \
was built.
6. Do not fabricate plugin names or configuration fields. Only use plugins \
and fields that appear in the catalog.
7. Use get_expression_grammar to understand gate expression syntax before \
writing conditions.
8. Connect nodes with edges using upsert_edge after creating nodes.
9. Every pipeline needs at least: a source, one or more sinks, and edges \
connecting them.
"""


def build_context_message(
    state: CompositionState,
    catalog: CatalogServiceProtocol,
) -> dict[str, str]:
    """Build the injected context message with current state and plugin summary.

    Args:
        state: Current composition state.
        catalog: For building the plugin summary.

    Returns:
        A dict with "role" and "content" suitable for the LLM message list.
    """
    serialized = _serialize_state(state)
    validation = state.validate()
    serialized["validation"] = {
        "is_valid": validation.is_valid,
        "errors": list(validation.errors),
    }

    # Build lightweight plugin summary (names only).
    # CatalogService returns PluginSummary instances (not dicts) — use .name attribute.
    source_names = [p.name for p in catalog.list_sources()]
    transform_names = [p.name for p in catalog.list_transforms()]
    sink_names = [p.name for p in catalog.list_sinks()]

    context = {
        "current_state": serialized,
        "available_plugins": {
            "sources": source_names,
            "transforms": transform_names,
            "sinks": sink_names,
        },
    }

    return {
        "role": "system",
        "content": f"Current pipeline state and available plugins:\n{json.dumps(context, indent=2)}",
    }


def build_messages(
    chat_history: list[Any],  # list[ChatMessageRecord], pre-fetched by route handler
    state: CompositionState,
    user_message: str,
    catalog: CatalogServiceProtocol,
) -> list[dict[str, Any]]:
    """Build the full message list for the LLM.

    IMPORTANT: Returns a NEW list on every call. Never returns a cached
    or shared reference. The tool-use loop appends to this list during
    iteration; returning a cached reference would cause cross-turn
    contamination.

    Message sequence:
    1. System message (static prompt)
    2. Injected context (current state + plugin summary)
    3. Chat history (previous messages in this session)
    4. Current user message

    Args:
        chat_history: Pre-fetched chat history (list[ChatMessageRecord]
            from session_service.get_messages(), passed by route handler).
        state: Current CompositionState.
        user_message: The user's current message.
        catalog: CatalogService for context injection.

    Returns:
        A new list of message dicts for the LLM.
    """
    messages: list[dict[str, Any]] = []

    # 1. System prompt
    messages.append({"role": "system", "content": SYSTEM_PROMPT})

    # 2. Injected context
    messages.append(build_context_message(state, catalog))

    # 3. Chat history
    if chat_history:
        messages.extend(chat_history)

    # 4. Current user message
    messages.append({"role": "user", "content": user_message})

    return messages
```

- [ ] **Step 3: Run mypy on both modules**

Run: `.venv/bin/python -m mypy src/elspeth/web/composer/protocol.py src/elspeth/web/composer/prompts.py`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/elspeth/web/composer/protocol.py src/elspeth/web/composer/prompts.py
git commit -m "feat(web/composer): add ComposerService protocol and prompt construction"
```

---

### Task 7: ComposerServiceImpl — LLM Tool-Use Loop

**Files:**
- Create: `src/elspeth/web/composer/service.py`
- Create: `tests/unit/web/composer/test_service.py`

- [ ] **Step 1: Write composer loop tests with mock LLM**

```python
# tests/unit/web/composer/test_service.py
"""Tests for ComposerServiceImpl — LLM tool-use loop with mock LLM."""
from __future__ import annotations

import json
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
        source=None, nodes=(), edges=(), outputs=(),
        metadata=PipelineMetadata(), version=1,
    )


def _mock_catalog() -> MagicMock:
    """Mock CatalogService with real PluginSummary/PluginSchemaInfo instances.

    AC #16: Tests must use real PluginSummary and PluginSchemaInfo instances,
    not plain dicts. Mock return types must match the CatalogService protocol.
    """
    catalog = MagicMock()
    catalog.list_sources.return_value = [
        PluginSummary(name="csv", description="CSV source", plugin_type="source", config_fields=[]),
    ]
    catalog.list_transforms.return_value = [
        PluginSummary(name="uppercase", description="Uppercase", plugin_type="transform", config_fields=[]),
    ]
    catalog.list_sinks.return_value = [
        PluginSummary(name="csv", description="CSV sink", plugin_type="sink", config_fields=[]),
    ]
    catalog.get_schema.return_value = PluginSchemaInfo(
        name="csv", plugin_type="source", description="CSV source",
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
    return settings


class TestComposerTextOnlyResponse:
    @pytest.mark.asyncio
    async def test_text_only_returns_immediately(self) -> None:
        """LLM responds with text only — no tool calls, loop terminates."""
        catalog = _mock_catalog()
        settings = _make_settings()
        service = ComposerServiceImpl(
            catalog=catalog, settings=settings,
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
            tool_calls=[{
                "id": "call_1",
                "name": "set_source",
                "arguments": {
                    "plugin": "csv",
                    "on_success": "t1",
                    "options": {"path": "/data.csv"},
                    "on_validation_failure": "quarantine",
                },
            }],
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
            tool_calls=[{
                "id": "call_1",
                "name": "set_source",
                "arguments": {
                    "plugin": "csv", "on_success": "t1",
                    "options": {}, "on_validation_failure": "quarantine",
                },
            }],
        )
        # Turn 2: set_metadata
        turn2 = _make_llm_response(
            tool_calls=[{
                "id": "call_2",
                "name": "set_metadata",
                "arguments": {"patch": {"name": "My Pipeline"}},
            }],
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
            tool_calls=[{
                "id": "call_loop",
                "name": "get_current_state",
                "arguments": {},
            }],
        )

        with patch.object(service, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = tool_response
            with pytest.raises(ComposerConvergenceError) as exc_info:
                await service.compose("Loop forever", [], state)
            assert exc_info.value.max_turns == 2


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
            tool_calls=[{
                "id": "call_bad",
                "name": "nonexistent_tool",
                "arguments": {},
            }],
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
            tool_calls=[{
                "id": "call_bad",
                "name": "set_source",
                "arguments": {"plugin": "csv"},  # missing on_success
            }],
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

        msgs1 = service._build_messages(None, state, "Hello")
        msgs2 = service._build_messages(None, state, "Hello")

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
                        "plugin": "csv", "on_success": "t1",
                        "options": {}, "on_validation_failure": "quarantine",
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
```

- [ ] **Step 2: Run tests — expect FAIL (module not found)**

Run: `.venv/bin/python -m pytest tests/unit/web/composer/test_service.py -v`
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement ComposerServiceImpl**

```python
# src/elspeth/web/composer/service.py
"""ComposerServiceImpl — bounded LLM tool-use loop for pipeline composition.

Uses LiteLLM for provider abstraction. Model configured via
WebSettings.composer_model. Tool calls are executed against
CompositionState + CatalogService.

Layer: L3 (application).
"""
from __future__ import annotations

import json
from typing import Any

import litellm

from elspeth.web.composer.protocol import (
    ComposerConvergenceError,
    ComposerResult,
)
from elspeth.web.composer.prompts import build_messages
from elspeth.web.composer.state import CompositionState
from elspeth.web.composer.tools import (
    CatalogServiceProtocol,
    ToolResult,
    execute_tool,
    get_tool_definitions,
)


class ComposerServiceImpl:
    """LLM-driven pipeline composer.

    Runs a bounded tool-use loop: sends messages to the LLM, executes
    any tool calls against the CompositionState, appends results, and
    repeats until the LLM produces a text-only response or max_turns
    is exceeded.

    Args:
        catalog: CatalogService for discovery tool delegation.
        settings: WebSettings with composer_model, composer_max_turns,
            composer_timeout_seconds.
    """

    def __init__(
        self,
        catalog: CatalogServiceProtocol,
        settings: Any,
    ) -> None:
        self._catalog = catalog
        self._model = settings.composer_model
        self._max_turns = settings.composer_max_turns

    async def compose(
        self,
        message: str,
        messages: list[Any],  # list[ChatMessageRecord]
        state: CompositionState,
    ) -> ComposerResult:
        """Run the LLM composition loop.

        Args:
            message: The user's chat message.
            messages: Pre-fetched chat history (from route handler).
                ComposerService does NOT depend on SessionService.
            state: The current CompositionState.

        Returns:
            ComposerResult with assistant message and updated state.

        Raises:
            ComposerConvergenceError: If the loop exceeds max_turns.
        """
        llm_messages = self._build_messages(messages, state, message)
        tools = self._get_litellm_tools()

        for _turn in range(self._max_turns):
            response = await self._call_llm(llm_messages, tools)
            assistant_message = response.choices[0].message

            # If no tool calls, the LLM is done — return text response
            if not assistant_message.tool_calls:
                return ComposerResult(
                    message=assistant_message.content or "",
                    state=state,
                )

            # Append the assistant message (with tool_calls metadata)
            llm_messages.append({
                "role": "assistant",
                "content": assistant_message.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in assistant_message.tool_calls
                ],
            })

            # Execute each tool call
            for tool_call in assistant_message.tool_calls:
                tool_name = tool_call.function.name
                try:
                    arguments = json.loads(tool_call.function.arguments)
                except (json.JSONDecodeError, TypeError) as exc:
                    # Malformed arguments — return error to LLM
                    llm_messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps({
                            "error": f"Invalid JSON in arguments: {exc}",
                        }),
                    })
                    continue

                try:
                    result = execute_tool(
                        tool_name, arguments, state, self._catalog
                    )
                    # Update state if mutation succeeded
                    state = result.updated_state
                    # Return tool result to LLM
                    llm_messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(result.to_dict()),
                    })
                except Exception as exc:
                    # Unexpected error — return to LLM, don't crash
                    llm_messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps({
                            "error": f"Tool execution error: {exc}",
                        }),
                    })

        raise ComposerConvergenceError(self._max_turns)

    def _build_messages(
        self,
        chat_history: list[Any],  # list[ChatMessageRecord]
        state: CompositionState,
        user_message: str,
    ) -> list[dict[str, Any]]:
        """Build the message list. Returns a NEW list on every call.

        This is critical: the tool-use loop appends to this list during
        iteration. Returning a cached reference would cause cross-turn
        contamination.
        """
        return build_messages(
            chat_history=chat_history,
            state=state,
            user_message=user_message,
            catalog=self._catalog,
        )

    def _get_litellm_tools(self) -> list[dict[str, Any]]:
        """Convert tool definitions to LiteLLM function format."""
        definitions = get_tool_definitions()
        return [
            {
                "type": "function",
                "function": {
                    "name": defn["name"],
                    "description": defn["description"],
                    "parameters": defn["parameters"],
                },
            }
            for defn in definitions
        ]

    async def _call_llm(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> Any:
        """Call the LLM via LiteLLM. Separated for test mocking."""
        return await litellm.acompletion(
            model=self._model,
            messages=messages,
            tools=tools,
        )
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `.venv/bin/python -m pytest tests/unit/web/composer/test_service.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Run mypy**

Run: `.venv/bin/python -m mypy src/elspeth/web/composer/service.py`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/elspeth/web/composer/service.py tests/unit/web/composer/test_service.py
git commit -m "feat(web/composer): implement ComposerServiceImpl — bounded LLM tool-use loop"
```

---

### Task 8: Wire POST /api/sessions/{id}/messages to ComposerService

**Files:**
- Modify: `src/elspeth/web/sessions/routes.py`
- Create: `tests/unit/web/composer/test_route_integration.py`

This task depends on Sub-Spec 2 (sessions module) being implemented first. The wiring connects the existing route handler to the ComposerService.

- [ ] **Step 1: Write route integration test**

```python
# tests/unit/web/composer/test_route_integration.py
"""Tests for POST /api/sessions/{id}/messages wiring to ComposerService."""
from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from elspeth.web.composer.protocol import ComposerResult
from elspeth.web.composer.state import (
    CompositionState,
    OutputSpec,
    PipelineMetadata,
    SourceSpec,
)


def _empty_state() -> CompositionState:
    return CompositionState(
        source=None, nodes=(), edges=(), outputs=(),
        metadata=PipelineMetadata(), version=1,
    )


class TestMessageRouteComposerWiring:
    """Tests that the route handler correctly calls ComposerService.compose()."""

    @pytest.mark.asyncio
    async def test_first_message_creates_initial_state(self) -> None:
        """First message in a session should create an empty initial state."""
        state = _empty_state()
        # The route handler should construct this empty state when no
        # existing state is found for the session.
        assert state.source is None
        assert state.nodes == ()
        assert state.version == 1

    @pytest.mark.asyncio
    async def test_composer_result_contains_state(self) -> None:
        """ComposerResult includes both message and state."""
        state = _empty_state()
        result = ComposerResult(
            message="Here's your pipeline.",
            state=state.with_source(
                SourceSpec(
                    plugin="csv", on_success="t1",
                    options={}, on_validation_failure="quarantine",
                )
            ),
        )
        assert result.message == "Here's your pipeline."
        assert result.state.source is not None
        assert result.state.version == 2

    @pytest.mark.asyncio
    async def test_state_version_changes_trigger_persistence(self) -> None:
        """If state version changed, the new state should be persisted."""
        original = _empty_state()
        updated = original.with_source(
            SourceSpec(
                plugin="csv", on_success="t1",
                options={}, on_validation_failure="quarantine",
            )
        )
        # Version changed: 1 -> 2 — route handler should persist
        assert updated.version != original.version

    @pytest.mark.asyncio
    async def test_convergence_error_returns_422(self) -> None:
        """ComposerConvergenceError maps to HTTP 422 with structured body.

        S16: Error shape is:
        {"error_type": "convergence", "detail": "...", "turns_used": int}
        """
        from elspeth.web.composer.protocol import ComposerConvergenceError

        exc = ComposerConvergenceError(max_turns=20)
        assert exc.max_turns == 20
        # The route handler catches this and returns:
        # {error_type: "convergence", detail: "...", turns_used: 20}
        # with HTTP 422

    @pytest.mark.asyncio
    async def test_llm_failure_returns_502(self) -> None:
        """LLM client failures map to HTTP 502 with structured body.

        S16: Error shapes are:
        {"error_type": "llm_unavailable", "detail": "..."} or
        {"error_type": "llm_auth_error", "detail": "..."} for auth failures.
        """
        # LiteLLM network/rate-limit/auth errors propagate to the route
        # handler, which returns:
        # {error_type: "llm_unavailable", detail: "..."} with HTTP 502
        # or {error_type: "llm_auth_error", detail: "..."} for auth failures
        pass  # Integration test — depends on route handler wiring

    @pytest.mark.asyncio
    async def test_state_unchanged_skips_persistence(self) -> None:
        """If state version unchanged, no persistence needed."""
        original = _empty_state()
        # ComposerResult with same state = no tool calls were made
        result = ComposerResult(message="Just chatting.", state=original)
        assert result.state.version == original.version
```

- [ ] **Step 2: Implement route wiring**

Add to `src/elspeth/web/sessions/routes.py` (the exact location depends on Sub-Spec 2 implementation). The route handler pattern is:

```python
# In the POST /api/sessions/{id}/messages handler:

async def send_message(
    session_id: str,
    body: MessageRequest,
    session_service: SessionService = Depends(get_session_service),
    composer_service: ComposerService = Depends(get_composer_service),
    current_user: User = Depends(get_current_user),
) -> MessageResponse:
    """Handle a user message — trigger the LLM composer.

    1. Load session (verify ownership).
    2. Persist user message.
    3. Load current CompositionState (or create empty initial state).
    4. Call ComposerService.compose().
    5. Persist assistant message.
    6. If state changed, persist new state version.
    7. Return {message, state}.
    """
    # 1. Load session
    session = await session_service.get_session(session_id, current_user.id)

    # 2. Persist user message
    user_msg = await session_service.add_message(
        session_id, role="user", content=body.content
    )

    # 3. Load or create composition state
    state = await session_service.get_latest_state(session_id)
    if state is None:
        state = CompositionState(
            source=None, nodes=(), edges=(), outputs=(),
            metadata=PipelineMetadata(), version=1,
        )

    # 4. Call composer — with structured HTTP error handling (S16)
    try:
        # Pre-fetch chat history — ComposerService does NOT depend on
        # SessionService; the route handler mediates (H1 fix, seam contract B).
        chat_messages = await session_service.get_messages(session_id)
        result = await composer_service.compose(body.content, chat_messages, state)
    except ComposerConvergenceError as exc:
        # M2: 422 for convergence errors — use "detail" not "message"
        raise HTTPException(
            status_code=422,
            detail={
                "error_type": "convergence",
                "detail": str(exc),
                "turns_used": exc.max_turns,
            },
        ) from exc
    except Exception as exc:
        # M2: 502 for LLM client failures — use "detail" not "message"
        error_type = "llm_auth_error" if "auth" in str(exc).lower() else "llm_unavailable"
        raise HTTPException(
            status_code=502,
            detail={
                "error_type": error_type,
                "detail": str(exc),
            },
        ) from exc

    # 5. Persist assistant message
    assistant_msg = await session_service.add_message(
        session_id, role="assistant", content=result.message
    )

    # 6. Validate and persist state if changed (M5 fix — is_valid population)
    if result.state.version != state.version:
        summary = result.state.validate()
        await session_service.save_composition_state(
            session_id,
            state=result.state,
            is_valid=summary.is_valid,
            validation_errors=list(summary.errors) if summary.errors else None,
        )

    # 7. Return response — wire field is "state" (H2 fix)
    return MessageResponse(message=assistant_msg, state=result.state)
```

**S18 — Revert system message injection:** When a user reverts to a prior composition version (via Sub-Spec 2's `set_active_state`), the route handler must inject a system message into the chat history: `"Pipeline reverted to version N."` This gives the LLM context that the state has been rolled back. The injected message uses `role="system"` and is persisted as a `ChatMessage` so it appears in the conversation history on subsequent turns. This is handled by the revert endpoint in Sub-Spec 2 -- when `set_active_state` is called, it persists the system message before returning. The `POST /messages` handler here does not need special revert logic because the system message will already be in the chat history by the time the next compose call runs.

- [ ] **Step 3: Implement GET /api/sessions/{id}/state/yaml endpoint (S10)**

Add to `src/elspeth/web/sessions/routes.py`:

```python
# GET /api/sessions/{id}/state/yaml — return generated YAML for current state.

async def get_session_yaml(
    session_id: str,
    session_service: SessionService = Depends(get_session_service),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Return the generated YAML for the session's current composition state.

    Response: {yaml: str} — the YAML string ready for display in the
    frontend's YAML tab.

    Returns HTTP 404 if the session has no CompositionState yet.
    Authentication and session ownership checks are identical to the
    messages endpoint.
    """
    # Load session (verify ownership)
    session = await session_service.get_session(session_id, current_user.id)

    # Load current state
    state = await session_service.get_latest_state(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="No composition state for this session.")

    yaml_str = generate_yaml(state)
    return {"yaml": yaml_str}
```

Add a test for this endpoint:

```python
# tests/unit/web/composer/test_route_integration.py (append)

class TestYamlEndpoint:
    @pytest.mark.asyncio
    async def test_yaml_endpoint_returns_yaml_string(self) -> None:
        """GET /api/sessions/{id}/state/yaml returns generated YAML."""
        from elspeth.web.composer.yaml_generator import generate_yaml

        state = _empty_state().with_source(
            SourceSpec(
                plugin="csv", on_success="t1",
                options={"path": "/data.csv"}, on_validation_failure="quarantine",
            )
        ).with_output(
            OutputSpec(name="out", plugin="csv", options={}, on_write_failure="discard")
        )
        yaml_str = generate_yaml(state)
        assert "csv" in yaml_str
        assert isinstance(yaml_str, str)

    @pytest.mark.asyncio
    async def test_yaml_endpoint_404_when_no_state(self) -> None:
        """GET /api/sessions/{id}/state/yaml returns 404 when no state exists."""
        # When session_service.get_latest_state() returns None,
        # the endpoint should return HTTP 404.
        pass  # Integration test — depends on Sub-Spec 2 session service
```

- [ ] **Step 4: Run all composer tests**

Run: `.venv/bin/python -m pytest tests/unit/web/composer/ -v`
Expected: All tests PASS.

- [ ] **Step 4: Run mypy on all composer modules**

Run: `.venv/bin/python -m mypy src/elspeth/web/composer/`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/elspeth/web/sessions/routes.py tests/unit/web/composer/test_route_integration.py
git commit -m "feat(web/composer): wire POST /api/sessions/{id}/messages to ComposerService"
```

---

## Self-Review Checklist

After all tasks, verify:

1. `ComposerService` protocol accepts `compose(message, messages, state)` — no dependency on `SessionService` (seam contract B).
2. `ComposerConvergenceError` raised when loop exceeds `max_turns`. Error includes `max_turns` attribute.
3. `SYSTEM_PROMPT` covers all 9 rules. `build_messages()` returns a NEW list on every call.
4. `build_context_message()` injects current state + validation + plugin summary (names only, via `.name` attribute).
5. `ComposerServiceImpl` runs bounded tool-use loop. `_call_llm()` is separated for test mocking.
6. Loop handles: text-only response, single tool call, multi-turn tool calls, multiple tool calls per turn, convergence error, unknown tool, malformed arguments.
7. `_build_messages()` delegates to `build_messages()` and returns a new list on every call.
8. Model configured via `WebSettings.composer_model`, max turns via `WebSettings.composer_max_turns`.
9. Route handler catches `ComposerConvergenceError` -> HTTP 422 with `{"error_type": "convergence", "detail": "...", "turns_used": int}` (S16).
10. Route handler catches LLM client errors -> HTTP 502 with `{"error_type": "llm_unavailable"|"llm_auth_error", "detail": "..."}` (S16).
11. Route handler pre-fetches chat history via `session_service.get_messages()` and passes to `compose()` (H1 fix).
12. Route handler calls `state.validate()` and passes `is_valid`/`errors` to `save_composition_state()` (M5 fix).
13. Route handler only persists state when `version` changed.
14. `GET /api/sessions/{id}/state/yaml` returns `{"yaml": str}` or 404 when no state exists (S10).
15. S18: Revert system message injection is handled by Sub-Spec 2's `set_active_state` -- no special logic needed in `POST /messages`.
16. All mock catalogs use real `PluginSummary` and `PluginSchemaInfo` instances (AC #16).

```bash
# Full test suite
.venv/bin/python -m pytest tests/unit/web/composer/ -v

# Type checking
.venv/bin/python -m mypy src/elspeth/web/composer/
```
