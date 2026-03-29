"""ExecutionService protocol — called from FastAPI route handlers."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from elspeth.web.auth.models import UserIdentity
from elspeth.web.execution.schemas import RunStatusResponse, ValidationResult


class ExecutionService(Protocol):
    """Protocol for pipeline execution operations.

    All methods are called from FastAPI route handlers in the async context.
    execute() returns immediately; the pipeline runs in a background thread.
    """

    async def validate(self, session_id: UUID) -> ValidationResult:
        """Async dry-run validation using real engine code paths.

        Loads the current CompositionState for the session, generates YAML,
        and runs it through load_settings -> instantiate_plugins_from_config
        -> ExecutionGraph.from_plugin_instances -> graph.validate().

        Async because the implementation wraps the sync validate_pipeline()
        call via run_in_executor to avoid blocking the event loop.
        """
        ...

    async def execute(self, session_id: UUID, state_id: UUID | None = None) -> UUID:
        """Start a background pipeline run.

        Returns the run_id immediately. Raises RunAlreadyActiveError if
        a pending or running Run already exists for this session.

        Note: async because it calls SessionService (async) for active-run
        check and run creation. The actual pipeline runs in a background
        thread via ThreadPoolExecutor — only the setup is async.
        """
        ...

    async def get_status(self, run_id: UUID) -> RunStatusResponse:
        """Return current run status from the Run database record."""
        ...

    async def cancel(self, run_id: UUID) -> None:
        """Cancel a run. Sets the shutdown Event for active runs.

        Idempotent — cancelling a terminal run is a no-op.
        Note: async because cancelling a pending run calls
        SessionService.update_run_status() directly (not via _call_async,
        since we're in the event loop thread).
        """
        ...

    async def verify_run_ownership(self, user: UserIdentity, run_id: str) -> bool:
        """Verify that a run belongs to the authenticated user's session."""
        ...
