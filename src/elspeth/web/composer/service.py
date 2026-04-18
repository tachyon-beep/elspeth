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
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

import litellm
import structlog
from litellm.exceptions import BadRequestError as LiteLLMBadRequestError
from sqlalchemy import Engine, update
from sqlalchemy.exc import SQLAlchemyError

from elspeth.web.catalog.protocol import CatalogService
from elspeth.web.composer.prompts import build_messages
from elspeth.web.composer.protocol import (
    ComposerConvergenceError,
    ComposerPluginCrashError,
    ComposerResult,
    ComposerServiceError,
    ComposerSettings,
    ToolArgumentError,
)
from elspeth.web.composer.state import CompositionState, ValidationSummary
from elspeth.web.composer.tools import (
    execute_tool,
    get_tool_definitions,
    is_cacheable_discovery_tool,
    is_discovery_tool,
)
from elspeth.web.sessions.models import sessions_table

slog = structlog.get_logger()

_ARRAY_ITEM_SEGMENT = "[]"
type RequiredPath = tuple[str, ...]


def _collect_required_paths(
    schema: Mapping[str, object],
    prefix: RequiredPath = (),
) -> tuple[RequiredPath, ...]:
    """Compile schema-declared required fields into dotted/indexed paths.

    The schema tree is system-owned tool metadata, so direct key access is
    intentional: a malformed tool definition should crash at import time.
    """
    schema_type = cast(str, schema["type"])

    if schema_type == "object":
        required_paths: list[RequiredPath] = []
        if "required" in schema:
            required_fields = cast(list[str], schema["required"])
            required_paths.extend((*prefix, field) for field in required_fields)
        if "properties" in schema:
            properties = cast(Mapping[str, Mapping[str, object]], schema["properties"])
            for key, child_schema in properties.items():
                required_paths.extend(_collect_required_paths(child_schema, (*prefix, key)))
        return tuple(required_paths)

    if schema_type == "array" and "items" in schema:
        item_schema = cast(Mapping[str, object], schema["items"])
        return _collect_required_paths(item_schema, (*prefix, _ARRAY_ITEM_SEGMENT))

    return ()


def _build_tool_required_paths_index() -> dict[str, tuple[RequiredPath, ...]]:
    """Build a lookup of required argument paths per tool definition."""
    index: dict[str, tuple[RequiredPath, ...]] = {}
    for defn in get_tool_definitions():
        parameters = cast(Mapping[str, object], defn["parameters"])
        index[defn["name"]] = _collect_required_paths(parameters)
    return index


def _find_missing_path_instances(
    value: object,
    required_path: RequiredPath,
    *,
    current_path: str = "",
) -> list[str]:
    """Return concrete missing-path instances for one required path."""
    if not required_path:
        return []

    head = required_path[0]
    tail = required_path[1:]

    if head == _ARRAY_ITEM_SEGMENT:
        match value:
            case list() as items:
                missing_paths: list[str] = []
                for index, item in enumerate(items):
                    item_path = f"{current_path}[{index}]" if current_path else f"[{index}]"
                    missing_paths.extend(_find_missing_path_instances(item, tail, current_path=item_path))
                return missing_paths
            case _:
                return []

    match value:
        case dict() as mapping:
            next_path = f"{current_path}.{head}" if current_path else head
            if head not in mapping:
                return [next_path]
            return _find_missing_path_instances(mapping[head], tail, current_path=next_path)
        case _:
            return []


def _find_missing_required_paths(
    value: object,
    required_paths: tuple[RequiredPath, ...],
) -> list[str]:
    """Return dotted/indexed paths for missing schema-required fields."""
    missing_paths: list[str] = []
    for required_path in required_paths:
        missing_paths.extend(_find_missing_path_instances(value, required_path))
    return missing_paths


_TOOL_REQUIRED_PATHS: dict[str, tuple[RequiredPath, ...]] = _build_tool_required_paths_index()


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
        deadline = asyncio.get_event_loop().time() + self._timeout_seconds
        try:
            return await self._compose_loop(message, messages, state, session_id, user_id, deadline)
        except ComposerConvergenceError:
            # Has its own partial_state; route handler persists. Do not intercept.
            raise
        except ComposerPluginCrashError as crash:
            # Plugin-bug crash path. The exception already carries
            # partial_state (populated by _compose_loop at the execute_tool
            # site when state.version > initial_version), so the route
            # handler can persist the accumulated mutations into
            # composition_states symmetrically with the convergence path.
            #
            # Here we only add the session-row audit breadcrumb (updated_at
            # bump — richer crash-marker columns tracked as a follow-up
            # migration: elspeth-23b0987938).
            if self._session_engine is not None and session_id is not None:
                try:
                    # Offload to the thread pool — _persist_crashed_session
                    # executes a synchronous SQLAlchemy ``Engine.begin()``
                    # + UPDATE, which would otherwise block the event
                    # loop for the duration of the DB round-trip,
                    # stalling websocket heartbeats, rate-limit checks,
                    # and concurrent progress broadcasts. Symmetric with
                    # the execute_tool offload at the top of
                    # _compose_loop: every other sync DB path in this
                    # file runs through asyncio.to_thread, and this
                    # crash-path call was missed when it was hoisted
                    # out of the main loop.
                    await asyncio.to_thread(self._persist_crashed_session, session_id)
                except (SQLAlchemyError, OSError) as audit_failure:
                    # Audit-persistence is best-effort on the crash path —
                    # failure to persist MUST NOT mask the original plugin
                    # bug. Log via slog.error (audit system itself is failing
                    # here, which is one of the three permitted slog use
                    # cases per the logging-telemetry-policy skill).
                    #
                    # Catch is narrowed to (SQLAlchemyError, OSError) so that
                    # programmer-bug exceptions in _persist_crashed_session
                    # itself — RuntimeError from the engine guard,
                    # AttributeError from a drifted table column, TypeError
                    # from a signature change — propagate instead of being
                    # laundered as "audit failure". Mirrors the cleanup-
                    # rollback pattern in the ``fork_from_message`` route
                    # handler (web/sessions/routes.py); see also the
                    # tier-model enforcer entry for this call site.
                    #
                    # exc_info is deliberately omitted: the original plugin
                    # exception's message / __cause__ chain may carry DB
                    # URLs, filesystem paths, or secret fragments from
                    # deeper layers (the response-body redaction in
                    # routes.py exists for the same reason). The two
                    # exc_class fields give the operator enough correlation
                    # to triage from structured logs alone.
                    slog.error(
                        "composer_crash_persistence_failed",
                        session_id=session_id,
                        original_exc_class=crash.exc_class,
                        audit_exc_class=type(audit_failure).__name__,
                    )
            raise

    async def _compose_loop(
        self,
        message: str,
        messages: list[dict[str, Any]],
        state: CompositionState,
        session_id: str | None = None,
        user_id: str | None = None,
        deadline: float = 0.0,
    ) -> ComposerResult:
        """Inner composition loop with dual-counter budget tracking.

        Uses cooperative timeout: the deadline is checked at safe
        checkpoints (before LLM calls, after tool batches) rather
        than using asyncio.wait_for() cancellation.  This ensures
        tool calls that have filesystem/DB side effects always run
        to completion with their state published — no split between
        committed side effects and the response.

        LLM calls are wrapped in per-call asyncio.wait_for(remaining)
        because they are pure network I/O with no side effects and
        can be safely cancelled.
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
            response = await self._call_llm_before_deadline(
                llm_messages,
                tools,
                state,
                initial_version,
                deadline,
            )
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

                # Validate schema-declared required arguments at the
                # Tier 3 boundary BEFORE entering tool handler code.
                # This walks nested object/array schemas, so malformed
                # set_pipeline payloads like source.plugin omissions are
                # caught here; any KeyError that still escapes
                # execute_tool() is an internal bug and must crash.
                # Unknown tool names skip validation — execute_tool()
                # handles them with a failure result downstream.
                required_paths = _TOOL_REQUIRED_PATHS[tool_name] if tool_name in _TOOL_REQUIRED_PATHS else ()
                missing = _find_missing_required_paths(arguments, required_paths)
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

                # All tool calls are offloaded to the thread pool via
                # asyncio.to_thread() to avoid blocking the event loop.
                # to_thread (not run_in_executor) because it propagates
                # contextvars into the worker thread automatically —
                # OpenTelemetry span context follows tool execution.
                # Blob and secret tools perform synchronous filesystem
                # writes and SQLAlchemy transactions that would otherwise
                # stall the single-process web server for all concurrent
                # requests (rate-limit checks, websocket heartbeats,
                # progress broadcasts).
                #
                # Cancel-safety: tool calls are NOT wrapped in
                # asyncio.wait_for — they always run to completion.
                # The cooperative deadline is checked BETWEEN operations
                # (before LLM calls, after tool batches), so side effects
                # and state publication are never split.  LLM calls use
                # per-call wait_for because they are pure network I/O
                # with no side effects.
                #
                # Tool handlers raise ToolArgumentError at Tier-3 boundaries
                # (LLM supplied wrong types, semantically invalid values,
                # or malformed encodings that cannot be coerced).  The
                # compose loop catches ONLY that class and feeds the error
                # back to the LLM for retry.
                #
                # Any other exception — TypeError, ValueError, UnicodeError,
                # KeyError, AttributeError — escaping execute_tool() is a
                # plugin bug (Tier 1/2) and MUST crash.  Per CLAUDE.md,
                # silently laundering a plugin bug as an LLM-argument error
                # is worse than crashing: it pollutes the audit trail with
                # a confident but wrong Tier-3 story, and the LLM's "retry"
                # cannot correct a fault in our own code.
                try:
                    result = await asyncio.to_thread(
                        execute_tool,
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
                except ToolArgumentError as exc:
                    if not is_discovery_tool(tool_name):
                        turn_has_mutation = True
                    # Trust-boundary redaction: the echoed message reaches the
                    # LLM API and (via audit) the Landscape. ToolArgumentError
                    # is structurally safe by construction — the keyword-only
                    # constructor accepts (argument, expected, actual_type)
                    # and composes args[0] from those fields alone, so the
                    # message cannot carry a raw LLM-supplied value. Belt-
                    # and-suspenders: read ``exc.args[0]`` rather than
                    # ``str(exc)`` so a future subclass that overrides
                    # ``__str__`` to embed ``__cause__`` context (which may
                    # carry DB URLs, filesystem paths, or secret fragments
                    # from deeper layers) cannot leak through this path.
                    # Handlers that use
                    # ``raise ToolArgumentError(...) from exc`` get the
                    # cause preserved on ``__cause__`` for debug/audit but
                    # NOT echoed to the LLM.
                    safe_message = exc.args[0] if exc.args else "tool argument error"
                    llm_messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": json.dumps(
                                {
                                    "error": f"Tool '{tool_name}' failed: {safe_message}",
                                }
                            ),
                        }
                    )
                    continue
                except Exception as tool_exc:
                    # Plugin-bug path: any exception class OTHER than
                    # ToolArgumentError escaping execute_tool() is a plugin
                    # bug (CLAUDE.md tier 1/2). Capture the loop-local
                    # `state` — which has been rebound to
                    # result.updated_state on every successful prior
                    # iteration — so the route layer can persist the
                    # accumulated mutations into composition_states before
                    # returning the 500. Without this, any tool call that
                    # successfully mutated state prior to the crash would
                    # be silently dropped from the state history.
                    #
                    # Wrap narrow-scope: only exceptions from the
                    # execute_tool call are wrapped here. Bugs in
                    # _call_llm_before_deadline / _build_messages surface
                    # through their own exception classes
                    # (ComposerServiceError, ComposerConvergenceError).
                    raise ComposerPluginCrashError.capture(
                        tool_exc,
                        state=state,
                        initial_version=initial_version,
                    ) from tool_exc

                state = result.updated_state
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
                    response = await self._call_llm_before_deadline(
                        llm_messages,
                        tools,
                        state,
                        initial_version,
                        deadline,
                    )
                    assistant_message = response.choices[0].message
                    if not assistant_message.tool_calls:
                        return ComposerResult(
                            message=assistant_message.content or "",
                            state=state,
                        )
                    raise ComposerConvergenceError.capture(
                        max_turns=composition_turns_used + discovery_turns_used,
                        budget_exhausted="composition",
                        state=state,
                        initial_version=initial_version,
                    )
            else:
                discovery_turns_used += 1
                if discovery_turns_used >= self._max_discovery_turns:
                    raise ComposerConvergenceError.capture(
                        max_turns=composition_turns_used + discovery_turns_used,
                        budget_exhausted="discovery",
                        state=state,
                        initial_version=initial_version,
                    )

    def _persist_crashed_session(self, session_id: str) -> None:
        """Best-effort timestamp bump to mark that a compose session crashed.

        NOTE: The sessions-table schema does not yet have a dedicated crash
        marker column. Bumping updated_at is the minimum viable breadcrumb
        until a migration adds (e.g.) a ``status`` or ``crashed_at`` column.
        A follow-up issue tracks the schema addition; do NOT introduce the
        migration as part of this PR (scope creep).

        The crash's exc_class is NOT written to the session row — no column
        exists to hold it. The operator correlates the updated_at bump with
        the crash via the slog.error emission at the call site, which
        includes session_id and exc_class in structured fields.

        Signature intentionally minimal — only the data that actually gets
        persisted is accepted. When the schema migration lands, this
        method's signature expands to take last_state and exc_class, and
        callers are updated at that point. Today, the caller passes
        session_id and logs the rest via slog.

        The caller's outer try/except absorbs any failure — this method
        MUST NOT mask the original plugin-bug exception if persistence
        itself fails.
        """
        # Offensive guard (explicit raise, not assert): ``python -O`` strips
        # assert statements, so a caller that somehow reaches this method
        # with ``_session_engine is None`` would silently no-op under the
        # optimised interpreter — turning a recoverable audit failure into
        # a missed ``updated_at`` write with no trace.  A typed
        # ``RuntimeError`` always fires.
        if self._session_engine is None:
            raise RuntimeError("_persist_crashed_session must only be called when session_engine is set")
        now = datetime.now(UTC)
        with self._session_engine.begin() as conn:
            conn.execute(update(sessions_table).where(sessions_table.c.id == session_id).values(updated_at=now))

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

        OSError from deployment skill loading (PermissionError,
        IsADirectoryError) is translated into ComposerServiceError so
        the route handler returns a structured 502 rather than a raw 500.

        The HTTP body carries only ``type(exc).__name__`` — NOT
        ``str(exc)`` — because ``OSError.__str__`` expands to a string
        that includes the absolute filename (``[Errno 13] Permission
        denied: '/var/lib/elspeth/data/skills/...'``) which would
        leak filesystem layout and the operator's data-dir path into
        the 502 response body.  Full detail including the filename is
        preserved via ``raise ... from exc`` for the ASGI / server-log
        machinery only.  Mirrors the redaction contract landed by
        commits 1a30d985 (SQLAlchemy 422 path) and 127417cb (sibling
        HTTP-path slog sites) — both narrow the HTTP surface to
        class-name-only while preserving structured server-side detail.
        """
        try:
            return build_messages(
                chat_history=chat_history,
                state=state,
                user_message=user_message,
                catalog=self._catalog,
                data_dir=self._data_dir,
            )
        except OSError as exc:
            raise ComposerServiceError(f"Failed to load deployment skill ({type(exc).__name__})") from exc

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
        response = await litellm.acompletion(
            model=self._model,
            messages=messages,
            tools=tools,
        )
        # Tier 3 boundary: LiteLLM can return empty choices on content-filter,
        # rate-limit, or malformed upstream responses.  Validate before callers
        # index into choices[0].
        if not response.choices:
            raise ComposerServiceError("LLM returned empty choices array — cannot continue composition")
        return response

    async def _call_llm_before_deadline(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        state: CompositionState,
        initial_version: int,
        deadline: float,
    ) -> litellm.ModelResponse:
        """Call the LLM with a per-call timeout derived from the deadline.

        LLM calls are pure network I/O with no side effects, so they
        are safe to cancel via asyncio.wait_for.  If the deadline has
        already passed or the call exceeds the remaining budget, raise
        ComposerConvergenceError with the current partial state.
        """
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            raise ComposerConvergenceError.capture(
                max_turns=0,
                budget_exhausted="timeout",
                state=state,
                initial_version=initial_version,
            )
        try:
            return await asyncio.wait_for(
                self._call_llm(messages, tools),
                timeout=remaining,
            )
        except TimeoutError:
            raise ComposerConvergenceError.capture(
                max_turns=0,
                budget_exhausted="timeout",
                state=state,
                initial_version=initial_version,
            ) from None

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
