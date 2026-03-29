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

from elspeth.web.composer.prompts import build_messages
from elspeth.web.composer.protocol import (
    ComposerConvergenceError,
    ComposerResult,
)
from elspeth.web.composer.state import CompositionState
from elspeth.web.composer.tools import (
    CatalogServiceProtocol,
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
        self._data_dir = str(settings.data_dir)

    async def compose(
        self,
        message: str,
        messages: list[dict[str, Any]],
        state: CompositionState,
    ) -> ComposerResult:
        """Run the LLM composition loop.

        Args:
            message: The user's chat message.
            messages: Chat history as plain dicts (pre-converted from
                ChatMessageRecord by route handler; seam contract B).
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
            llm_messages.append(
                {
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
                }
            )

            # Execute each tool call
            for tool_call in assistant_message.tool_calls:
                tool_name = tool_call.function.name
                try:
                    arguments = json.loads(tool_call.function.arguments)
                except (json.JSONDecodeError, TypeError) as exc:
                    # Malformed arguments — return error to LLM
                    llm_messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": json.dumps(
                                {
                                    "error": f"Invalid JSON in arguments: {exc}",
                                }
                            ),
                        }
                    )
                    continue

                # execute_tool() is system code, but the arguments dict
                # comes from LLM output (Tier 3). Missing/wrong-type keys
                # in LLM-provided arguments are expected failures — return
                # the error to the LLM so it can self-correct. Bugs in
                # execute_tool's own logic will raise other exceptions and
                # crash as intended (Amendment 2).
                try:
                    result = execute_tool(
                        tool_name,
                        arguments,
                        state,
                        self._catalog,
                        data_dir=self._data_dir,
                    )
                except (KeyError, TypeError) as exc:
                    llm_messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": json.dumps(
                                {
                                    "error": f"Tool '{tool_name}' failed: {exc}",
                                }
                            ),
                        }
                    )
                    continue
                # Update state if mutation succeeded
                state = result.updated_state
                # Return tool result to LLM
                llm_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(result.to_dict()),
                    }
                )

        # B-4D-3 fix: After exhausting max_turns with tool calls on the
        # final iteration, give the LLM one last chance to see the tool
        # results and produce a text response. Without this, a correction
        # made on the final turn is applied to state but the LLM never
        # sees the confirmation — the user gets a convergence error even
        # though the state may be valid.
        response = await self._call_llm(llm_messages, tools)
        assistant_message = response.choices[0].message
        if not assistant_message.tool_calls:
            return ComposerResult(
                message=assistant_message.content or "",
                state=state,
            )

        raise ComposerConvergenceError(self._max_turns)

    def _build_messages(
        self,
        chat_history: list[dict[str, Any]],
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
