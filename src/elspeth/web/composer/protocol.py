"""ComposerService protocol and result types.

Layer: L3 (application). Defines the service boundary for LLM-driven
pipeline composition.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol

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
    """Raised when the LLM tool-use loop exhausts its budget or times out.

    Attributes:
        max_turns: Total turns used before exhaustion.
        budget_exhausted: Which budget was exhausted — one of
            "composition", "discovery", or "timeout".
        partial_state: The last CompositionState with version > initial,
            or None if no mutations occurred.
    """

    def __init__(
        self,
        max_turns: int,
        *,
        budget_exhausted: Literal["composition", "discovery", "timeout"] = "composition",
        partial_state: CompositionState | None = None,
    ) -> None:
        super().__init__(
            f"Composer did not converge within {max_turns} turns "
            f"(budget exhausted: {budget_exhausted}). "
            f"The LLM kept making tool calls without producing a final response."
        )
        self.max_turns = max_turns
        self.budget_exhausted = budget_exhausted
        self.partial_state = partial_state


class ComposerPluginCrashError(ComposerServiceError):
    """Raised when an exception escapes ``execute_tool()`` inside the compose loop.

    Signals a plugin (tier 1/2) bug — distinct from ``ToolArgumentError``
    (which is a tier 3 boundary signal and is caught inside the loop).

    Symmetric with :class:`ComposerConvergenceError`: both transport a
    ``partial_state`` field from service to route so the route handler can
    persist the accumulated in-memory mutations into ``composition_states``
    before returning the failure response. Without this carrier, any tool
    call that successfully mutated state prior to a later crash would be
    silently dropped from the immutable-append state history, and recompose
    would restart from the stale pre-request state.

    Attributes:
        original_exc: The underlying plugin-bug exception. Preserved on
            ``__cause__`` via ``raise ... from`` so the ASGI error machinery
            still has the full traceback, but the route handler redacts
            ``str(original_exc)`` / its ``__cause__`` chain from the HTTP
            response because those may carry DB URLs, filesystem paths, or
            secret fragments.
        partial_state: The last :class:`CompositionState` with ``version >
            initial_version``, or ``None`` if no mutations occurred before
            the crash.
        exc_class: ``type(original_exc).__name__`` — the only safe
            exception-identity hint for structured logs.

    Route ordering: this class inherits from ``ComposerServiceError`` so the
    route must catch ``ComposerPluginCrashError`` BEFORE the generic
    ``except ComposerServiceError`` block, mirroring the ordering already
    used for ``ComposerConvergenceError`` at routes.py:377/512. If the
    ordering is inverted the generic handler would launder the crash into
    a 502, reintroducing the silent-laundering behaviour the narrowed catch
    was designed to eliminate.
    """

    def __init__(
        self,
        original_exc: Exception,
        *,
        partial_state: CompositionState | None = None,
    ) -> None:
        super().__init__(f"Composer plugin crash: {type(original_exc).__name__}")
        self.original_exc = original_exc
        self.partial_state = partial_state
        self.exc_class = type(original_exc).__name__


class ToolArgumentError(Exception):
    """Raised by a tool handler when LLM-supplied arguments are unusable.

    Signals a Tier-3 boundary failure: the LLM provided arguments of the
    wrong type, or semantically invalid values that the handler cannot
    coerce. The compose loop catches this exception and returns the
    message to the LLM as a tool error so it can retry.

    This is the ONLY exception class the compose loop catches around
    execute_tool(). Any other TypeError/ValueError/UnicodeError/KeyError
    escaping a tool handler is a plugin bug and MUST crash — per
    CLAUDE.md, plugin bugs that silently produce wrong results are worse
    than a crash because they pollute the audit trail with confidently
    wrong data.

    Inheritance rationale: this class inherits from ``Exception`` directly,
    NOT from ``ComposerServiceError``. A handler-internal signal caught by
    the compose loop must not be absorbed by the route-level
    ``except ComposerServiceError`` block (routes.py:390/505), which would
    silently convert an escaped ToolArgumentError into a 502 — recreating
    the laundering pattern the compose-loop narrowing is designed to
    eliminate. If a ToolArgumentError ever escapes ``_compose_loop``, that
    is a compose-loop bug: FastAPI's default handler will surface it as
    an unstructured 500 for investigation, which is the correct failure
    mode for an invariant violation.

    Handlers that wrap an underlying exception should use::

        raise ToolArgumentError("descriptive message") from exc

    so the cause chain survives ``asyncio.to_thread`` re-raise for audit.
    """


class ComposerSettings(Protocol):
    """Protocol for the settings the composer service needs.

    Allows ComposerServiceImpl to depend on a structural type rather than
    the concrete WebSettings class. Properties are read-only to match
    frozen Pydantic models.
    """

    @property
    def composer_model(self) -> str: ...

    @property
    def composer_max_composition_turns(self) -> int: ...

    @property
    def composer_max_discovery_turns(self) -> int: ...

    @property
    def composer_timeout_seconds(self) -> float: ...

    @property
    def data_dir(self) -> Any: ...


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
        messages: list[dict[str, Any]],
        state: CompositionState,
        session_id: str | None = None,
        user_id: str | None = None,
    ) -> ComposerResult:
        """Run the LLM composition loop.

        Args:
            message: The user's chat message.
            messages: Chat history as plain dicts (role/content keys).
                The route handler fetches ChatMessageRecord from
                session_service.get_messages(), converts each to a dict,
                and passes the result here. ComposerService does NOT
                depend on SessionService (seam contract B).
            state: The current CompositionState.
            user_id: Current user ID. Passed through to secret tools.

        Returns:
            ComposerResult with assistant message and updated state.

        Raises:
            ComposerConvergenceError: If the loop exceeds max_turns.
        """
        ...
