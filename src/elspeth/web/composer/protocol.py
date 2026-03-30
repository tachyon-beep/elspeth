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
        budget_exhausted: str = "composition",
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
