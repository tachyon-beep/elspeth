"""ComposerServiceImpl — bounded LLM tool-use loop for pipeline composition.

Uses LiteLLM for provider abstraction. Model configured via
WebSettings.composer_model. Tool calls are executed against
CompositionState + CatalogService.

Dual-counter budget: separate limits for discovery and composition turns.
Discovery cache: cacheable discovery tool results cached per-compose-call
in a local dict variable (not an instance field) to avoid concurrent-request
races.

Layer: L3 (application).
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

import litellm
from litellm.exceptions import BadRequestError as LiteLLMBadRequestError
from sqlalchemy import Engine

from elspeth.web.catalog.protocol import CatalogService
from elspeth.web.composer.prompts import build_messages
from elspeth.web.composer.protocol import (
    ComposerConvergenceError,
    ComposerResult,
    ComposerSettings,
)
from elspeth.web.composer.state import CompositionState, ValidationSummary
from elspeth.web.composer.tools import (
    execute_tool,
    get_tool_definitions,
    is_cacheable_discovery_tool,
    is_discovery_tool,
)


def _build_required_args_index() -> dict[str, list[str]]:
    """Build a lookup of required argument names per tool from tool definitions.

    Used to validate LLM-provided arguments before entering tool handler code,
    so that missing-argument KeyErrors are caught at the boundary (Tier 3) and
    don't mask internal KeyErrors from bugs in tool handler logic.

    All tool definitions are system-owned and MUST have "parameters" and
    "required" keys — direct access will crash on a schema definition bug.
    """
    index: dict[str, list[str]] = {}
    for defn in get_tool_definitions():
        name = defn["name"]
        index[name] = defn["parameters"]["required"]
    return index


_TOOL_REQUIRED_ARGS: dict[str, list[str]] = _build_required_args_index()


@dataclass(frozen=True, slots=True)
class ComposerAvailability:
    """Boot-time availability snapshot for the composer service."""

    available: bool
    model: str
    provider: str | None
    reason: str | None = None
    missing_keys: tuple[str, ...] = ()


class ComposerServiceImpl:
    """LLM-driven pipeline composer with dual-counter budget and discovery caching.

    Runs a bounded tool-use loop with separate budgets for discovery
    and composition turns. Cacheable discovery tool results are cached
    per-compose-call in a local dict (not an instance field) to avoid
    concurrent-request races.

    Budget classification: a turn containing at least one mutation tool
    call charges the composition budget. A turn containing only discovery
    tool calls charges the discovery budget. Cache hits do not charge
    any budget.

    Args:
        catalog: CatalogService for discovery tool delegation.
        settings: ComposerSettings with composer_max_composition_turns,
            composer_max_discovery_turns, composer_timeout_seconds,
            composer_model, data_dir.
    """

    def __init__(
        self,
        catalog: CatalogService,
        settings: ComposerSettings,
        session_engine: Engine | None = None,
        secret_service: Any | None = None,
    ) -> None:
        self._catalog = catalog
        self._model = settings.composer_model
        self._max_composition_turns = settings.composer_max_composition_turns
        self._max_discovery_turns = settings.composer_max_discovery_turns
        self._timeout_seconds = settings.composer_timeout_seconds
        self._data_dir: str = str(settings.data_dir)
        self._session_engine = session_engine
        self._secret_service = secret_service
        self._availability = self._compute_availability()

    def get_availability(self) -> ComposerAvailability:
        """Return the boot-time composer availability snapshot."""
        return self._availability

    async def compose(
        self,
        message: str,
        messages: list[dict[str, Any]],
        state: CompositionState,
        session_id: str | None = None,
        user_id: str | None = None,
    ) -> ComposerResult:
        """Run the LLM composition loop with dual-counter budget.

        Args:
            message: The user's chat message.
            messages: Chat history as plain dicts (pre-converted from
                ChatMessageRecord by route handler; seam contract B).
            state: The current CompositionState.

        Returns:
            ComposerResult with assistant message and updated state.

        Raises:
            ComposerConvergenceError: If a budget is exhausted or
                the timeout is exceeded.
        """
        # Mutable container so _compose_loop can publish its latest
        # state to the outer scope. On TimeoutError, compose() reads
        # this to build partial_state — the local `state` variable
        # inside _compose_loop is unreachable after cancellation.
        state_ref: list[CompositionState] = [state]
        initial_version = state.version
        try:
            return await asyncio.wait_for(
                self._compose_loop(message, messages, state, state_ref, session_id, user_id),
                timeout=self._timeout_seconds,
            )
        except TimeoutError:
            latest = state_ref[0]
            partial = latest if latest.version > initial_version else None
            raise ComposerConvergenceError(
                max_turns=0,
                budget_exhausted="timeout",
                partial_state=partial,
            ) from None

    async def _compose_loop(
        self,
        message: str,
        messages: list[dict[str, Any]],
        state: CompositionState,
        state_ref: list[CompositionState],
        session_id: str | None = None,
        user_id: str | None = None,
    ) -> ComposerResult:
        """Inner composition loop with dual-counter budget tracking.

        Args:
            state_ref: Single-element mutable list. Updated after every
                successful tool execution so the outer compose() can
                read the latest state on timeout.
        """
        initial_version = state.version
        llm_messages = self._build_messages(messages, state, message)
        tools = self._get_litellm_tools()

        composition_turns_used = 0
        discovery_turns_used = 0

        # Discovery cache: local variable scoped to this compose() call.
        # Keyed by (tool_name, canonical_args_json). Each concurrent
        # compose() call gets its own independent cache dict.
        discovery_cache: dict[str, Any] = {}

        # Validation threading: compute once for the initial state, then
        # carry forward from each ToolResult.validation. Avoids redundant
        # validate() calls — CompositionState is immutable so validation
        # is deterministic for a given state object.
        last_validation: ValidationSummary | None = None

        while True:
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

            # Execute each tool call, tracking whether this turn has
            # any mutation calls for budget classification.
            turn_has_mutation = False
            all_cache_hits = True

            for tool_call in assistant_message.tool_calls:
                tool_name = tool_call.function.name
                try:
                    arguments = json.loads(tool_call.function.arguments)
                except (json.JSONDecodeError, TypeError) as exc:
                    # Track mutation intent even when args are unparseable
                    if not is_discovery_tool(tool_name):
                        turn_has_mutation = True
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
                    all_cache_hits = False
                    continue

                # Check discovery cache before executing
                if is_cacheable_discovery_tool(tool_name):
                    cache_key = _make_cache_key(tool_name, arguments)
                    if cache_key in discovery_cache:
                        # Cache hit — return cached result, no budget charge
                        llm_messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": discovery_cache[cache_key],
                            }
                        )
                        continue

                all_cache_hits = False

                # Validate required arguments at the Tier 3 boundary
                # BEFORE entering tool handler code.  This catches LLM
                # argument omissions here; any KeyError that escapes
                # execute_tool() is an internal bug and must crash.
                # Unknown tool names skip validation — execute_tool()
                # handles them with a failure result downstream.
                required = _TOOL_REQUIRED_ARGS[tool_name] if tool_name in _TOOL_REQUIRED_ARGS else []
                missing = [k for k in required if k not in arguments]
                if missing:
                    if not is_discovery_tool(tool_name):
                        turn_has_mutation = True
                    llm_messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": json.dumps(
                                {
                                    "error": (f"Tool '{tool_name}' missing required argument(s): {', '.join(missing)}"),
                                }
                            ),
                        }
                    )
                    continue

                # TypeError is still caught because LLM can provide wrong
                # value types (e.g. string where list expected → tuple()
                # fails).  KeyError is NOT caught — after required-arg
                # validation above, any KeyError is an internal bug.
                try:
                    result = execute_tool(
                        tool_name,
                        arguments,
                        state,
                        self._catalog,
                        data_dir=self._data_dir,
                        session_engine=self._session_engine,
                        session_id=session_id,
                        secret_service=self._secret_service,
                        user_id=user_id,
                        prior_validation=last_validation,
                    )
                except TypeError as exc:
                    if not is_discovery_tool(tool_name):
                        turn_has_mutation = True
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

                state = result.updated_state
                state_ref[0] = state  # Publish for timeout capture
                last_validation = result.validation
                result_json = _serialize_tool_result(result)

                # Cache cacheable discovery results
                if is_cacheable_discovery_tool(tool_name):
                    cache_key = _make_cache_key(tool_name, arguments)
                    discovery_cache[cache_key] = result_json

                llm_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result_json,
                    }
                )

                if not is_discovery_tool(tool_name):
                    turn_has_mutation = True

            # If ALL tool calls in this turn were cache hits, no budget
            # charge — continue to next turn without incrementing.
            if all_cache_hits:
                continue

            # Classify turn and charge the appropriate budget.
            # The current turn has already been executed (tool results
            # are in the message history). We increment first, then
            # check whether the budget is now exhausted. If so, we give
            # the LLM one last chance (B-4D-3) for composition, or
            # raise immediately for discovery (discovery exhaustion
            # doesn't benefit from a bonus call — no state was mutated).
            if turn_has_mutation:
                composition_turns_used += 1
                if composition_turns_used >= self._max_composition_turns:
                    # B-4D-3 fix: give the LLM one last chance to see the
                    # tool results and produce a text response.
                    response = await self._call_llm(llm_messages, tools)
                    assistant_message = response.choices[0].message
                    if not assistant_message.tool_calls:
                        return ComposerResult(
                            message=assistant_message.content or "",
                            state=state,
                        )
                    partial = state if state.version > initial_version else None
                    raise ComposerConvergenceError(
                        max_turns=composition_turns_used + discovery_turns_used,
                        budget_exhausted="composition",
                        partial_state=partial,
                    )
            else:
                discovery_turns_used += 1
                if discovery_turns_used >= self._max_discovery_turns:
                    partial = state if state.version > initial_version else None
                    raise ComposerConvergenceError(
                        max_turns=composition_turns_used + discovery_turns_used,
                        budget_exhausted="discovery",
                        partial_state=partial,
                    )

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
            data_dir=self._data_dir,
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
    ) -> litellm.ModelResponse:
        """Call the LLM via LiteLLM. Separated for test mocking."""
        return await litellm.acompletion(
            model=self._model,
            messages=messages,
            tools=tools,
        )

    def _compute_availability(self) -> ComposerAvailability:
        """Infer whether the configured model has the required env at boot.

        This is a configuration/readiness signal, not a network health check.
        """
        try:
            _, provider, _, _ = litellm.get_llm_provider(model=self._model)
        except LiteLLMBadRequestError:
            # Fallback: infer from "provider/model" prefix. Returns None for
            # unprefixed names — ComposerAvailability.provider is str | None,
            # and this is a boot-time diagnostic, not audit data.
            provider = _infer_provider_from_model_name(self._model)

        try:
            env_status = litellm.validate_environment(model=self._model)
        except LiteLLMBadRequestError as exc:
            return ComposerAvailability(
                available=False,
                model=self._model,
                provider=provider,
                reason=f"Unable to validate composer environment: {exc}",
            )

        missing_keys = tuple(sorted(set(env_status["missing_keys"])))
        if env_status["keys_in_environment"]:
            return ComposerAvailability(
                available=True,
                model=self._model,
                provider=provider,
            )

        if missing_keys:
            missing = ", ".join(missing_keys)
            reason = f"Composer model {self._model} is unavailable: missing {missing}."
        else:
            reason = f"Composer model {self._model} is unavailable: provider environment validation failed."

        return ComposerAvailability(
            available=False,
            model=self._model,
            provider=provider,
            reason=reason,
            missing_keys=missing_keys,
        )


def _infer_provider_from_model_name(model: str) -> str | None:
    """Infer provider from a provider-prefixed model string."""
    if "/" not in model:
        return None
    return model.split("/", 1)[0]


def _pydantic_default(obj: Any) -> Any:
    """JSON serializer fallback for Pydantic models in tool results."""
    try:
        return obj.model_dump()
    except AttributeError:
        raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable") from None


def _serialize_tool_result(result: Any) -> str:
    """Serialize a ToolResult to JSON, handling Pydantic models in data."""
    return json.dumps(result.to_dict(), default=_pydantic_default)


def _make_cache_key(tool_name: str, arguments: dict[str, Any]) -> str:
    """Build a deterministic cache key from tool name + arguments."""
    # Sort keys for determinism. Arguments are simple JSON-serializable
    # dicts from the LLM — no MappingProxyType or frozen containers.
    return f"{tool_name}:{json.dumps(arguments, sort_keys=True)}"
