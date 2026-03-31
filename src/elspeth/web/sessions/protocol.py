"""SessionService protocol and record dataclasses.

Record types are frozen dataclasses representing database rows.
CompositionStateData is the input DTO for saving new state versions.
"""

# ID Convention: Record dataclasses use UUID for type safety. The database
# stores IDs as String (TEXT). The SessionServiceImpl (Sub-2d) converts
# between UUID and str at the query/record boundary. Callers work with
# UUID exclusively; the storage representation is an implementation detail.

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Protocol, runtime_checkable
from uuid import UUID

from elspeth.contracts.freeze import freeze_fields

# Legal run status transitions. Implementations MUST reject any
# transition not in this table.
LEGAL_RUN_TRANSITIONS: dict[str, frozenset[str]] = {
    "pending": frozenset({"running", "cancelled"}),
    "running": frozenset({"completed", "failed", "cancelled"}),
    "completed": frozenset(),  # terminal
    "failed": frozenset(),  # terminal
    "cancelled": frozenset(),  # terminal
}


@dataclass(frozen=True, slots=True)
class SessionRecord:
    """Represents a row from the sessions table.

    All fields are scalars or datetime -- no freeze guard needed.
    """

    id: UUID
    user_id: str
    auth_provider_type: str
    title: str
    created_at: datetime
    updated_at: datetime
    forked_from_session_id: UUID | None = None
    forked_from_message_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class ChatMessageRecord:
    """Represents a row from the chat_messages table.

    tool_calls may contain a dict -- requires freeze guard when not None.
    """

    id: UUID
    session_id: UUID
    role: Literal["user", "assistant", "system", "tool"]
    content: str
    tool_calls: Mapping[str, Any] | None
    created_at: datetime
    composition_state_id: UUID | None = None

    def __post_init__(self) -> None:
        if self.tool_calls is not None:
            freeze_fields(self, "tool_calls")


@dataclass(frozen=True, slots=True)
class CompositionStateData:
    """Input DTO for saving a new composition state version.

    Contains mutable container fields -- requires freeze guard.
    """

    source: Mapping[str, Any] | None = None
    nodes: Sequence[Mapping[str, Any]] | None = None
    edges: Sequence[Mapping[str, Any]] | None = None
    outputs: Sequence[Mapping[str, Any]] | None = None
    metadata_: Mapping[str, Any] | None = None
    is_valid: bool = False
    validation_errors: Sequence[str] | None = None

    def __post_init__(self) -> None:
        non_none = []
        if self.source is not None:
            non_none.append("source")
        if self.nodes is not None:
            non_none.append("nodes")
        if self.edges is not None:
            non_none.append("edges")
        if self.outputs is not None:
            non_none.append("outputs")
        if self.metadata_ is not None:
            non_none.append("metadata_")
        if self.validation_errors is not None:
            non_none.append("validation_errors")
        if non_none:
            freeze_fields(self, *non_none)


@dataclass(frozen=True, slots=True)
class CompositionStateRecord:
    """Represents a row from the composition_states table.

    Contains mutable container fields -- requires freeze guard.
    """

    id: UUID
    session_id: UUID
    version: int
    source: Mapping[str, Any] | None
    nodes: Sequence[Mapping[str, Any]] | None
    edges: Sequence[Mapping[str, Any]] | None
    outputs: Sequence[Mapping[str, Any]] | None
    metadata_: Mapping[str, Any] | None
    is_valid: bool
    validation_errors: Sequence[str] | None
    created_at: datetime
    derived_from_state_id: UUID | None

    def __post_init__(self) -> None:
        non_none = []
        if self.source is not None:
            non_none.append("source")
        if self.nodes is not None:
            non_none.append("nodes")
        if self.edges is not None:
            non_none.append("edges")
        if self.outputs is not None:
            non_none.append("outputs")
        if self.metadata_ is not None:
            non_none.append("metadata_")
        if self.validation_errors is not None:
            non_none.append("validation_errors")
        if non_none:
            freeze_fields(self, *non_none)


@dataclass(frozen=True, slots=True)
class RunRecord:
    """Represents a row from the runs table.

    All fields are scalars, datetime, or None -- no freeze guard needed.
    """

    id: UUID
    session_id: UUID
    state_id: UUID
    status: Literal["pending", "running", "completed", "failed", "cancelled"]
    started_at: datetime
    finished_at: datetime | None
    rows_processed: int
    rows_failed: int
    error: str | None
    landscape_run_id: str | None
    pipeline_yaml: str | None


class InvalidForkTargetError(Exception):
    """Raised when attempting to fork from a non-user message.

    Route handlers catching this error should return 422.
    """

    def __init__(self, message_id: str, role: str) -> None:
        self.message_id = message_id
        self.role = role
        super().__init__(f"Can only fork from user messages, got role '{role}' for message {message_id}")


class RunAlreadyActiveError(Exception):
    """Raised when attempting to create a run while one is already active.

    Seam contract D: HTTP handlers catching this error MUST return 409 with
    {"detail": str(exc), "error_type": "run_already_active"} -- not a bare
    HTTPException. See seam-contracts.md for the canonical error shape.
    """

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        super().__init__(f"Session {session_id} already has an active run")


@runtime_checkable
class SessionServiceProtocol(Protocol):
    """Protocol for session persistence operations."""

    async def create_session(
        self,
        user_id: str,
        title: str,
        auth_provider_type: str,
        forked_from_session_id: UUID | None = None,
        forked_from_message_id: UUID | None = None,
    ) -> SessionRecord: ...

    async def get_session(self, session_id: UUID) -> SessionRecord: ...

    async def list_sessions(
        self,
        user_id: str,
        auth_provider_type: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[SessionRecord]: ...

    async def archive_session(self, session_id: UUID) -> None: ...

    async def add_message(
        self,
        session_id: UUID,
        role: Literal["user", "assistant", "system", "tool"],
        content: str,
        tool_calls: Mapping[str, Any] | None = None,
        composition_state_id: UUID | None = None,
    ) -> ChatMessageRecord: ...

    async def get_messages(
        self,
        session_id: UUID,
        limit: int | None = 100,
        offset: int = 0,
    ) -> list[ChatMessageRecord]: ...

    async def save_composition_state(
        self,
        session_id: UUID,
        state: CompositionStateData,
    ) -> CompositionStateRecord: ...

    async def get_current_state(
        self,
        session_id: UUID,
    ) -> CompositionStateRecord | None: ...

    async def get_state(self, state_id: UUID) -> CompositionStateRecord: ...

    async def get_state_versions(
        self,
        session_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> list[CompositionStateRecord]: ...

    async def set_active_state(
        self,
        session_id: UUID,
        state_id: UUID,
    ) -> CompositionStateRecord:
        """Set the active composition state for a session.

        Creates a new state version derived from the specified state_id.
        Sets derived_from_state_id on the new version to record lineage.
        """
        ...

    async def create_run(
        self,
        session_id: UUID,
        state_id: UUID,
        pipeline_yaml: str | None = None,
    ) -> RunRecord: ...

    async def get_run(self, run_id: UUID) -> RunRecord: ...

    async def list_runs_for_session(self, session_id: UUID) -> list[RunRecord]: ...

    async def update_run_status(
        self,
        run_id: UUID,
        status: str,
        error: str | None = None,
        landscape_run_id: str | None = None,
        rows_processed: int | None = None,
        rows_failed: int | None = None,
    ) -> None:
        """Update a run's status and metadata.

        Transitions MUST comply with LEGAL_RUN_TRANSITIONS.

        landscape_run_id is write-once: once set to a non-None value,
        subsequent calls MUST NOT overwrite it. Implementations MUST
        raise ValueError if landscape_run_id is provided but the run
        already has one set.
        """
        ...

    async def get_active_run(
        self,
        session_id: UUID,
    ) -> RunRecord | None: ...

    async def prune_state_versions(
        self,
        session_id: UUID,
        keep_latest: int = 50,
    ) -> int:
        """Delete old composition state versions beyond keep_latest.

        Preserves the most recent `keep_latest` versions and any versions
        referenced by a run (via runs.state_id). Returns the count of
        deleted versions.
        """
        ...

    async def fork_session(
        self,
        source_session_id: UUID,
        fork_message_id: UUID,
        new_message_content: str,
        user_id: str,
        auth_provider_type: str,
    ) -> tuple[SessionRecord, list[ChatMessageRecord], CompositionStateRecord | None]:
        """Fork a session from a specific user message.

        Creates a new session with inherited history and state up to the
        fork point. The original session is never mutated.
        """
        ...

    async def update_message_composition_state(
        self,
        message_id: UUID,
        composition_state_id: UUID,
    ) -> None:
        """Re-point a message's composition_state_id to a different state.

        Used after fork blob-remapping creates a replacement state so
        the user message's provenance tracks the rewritten (self-contained)
        state rather than the original copy.
        """
        ...

    async def cancel_orphaned_runs(
        self,
        session_id: UUID,
        max_age_seconds: int = 3600,
    ) -> list[RunRecord]:
        """Force-cancel runs stuck in 'running' status beyond max_age_seconds.

        Returns the list of cancelled RunRecords. Called by the execution
        service on startup and periodically to prevent orphaned runs from
        permanently blocking sessions.
        """
        ...

    async def cancel_all_orphaned_runs(
        self,
        max_age_seconds: int = 3600,
    ) -> int:
        """Force-cancel stale runs across all sessions.

        Called on startup to recover sessions blocked by runs orphaned
        during a previous server crash. Returns the count of cancelled runs.
        """
        ...
