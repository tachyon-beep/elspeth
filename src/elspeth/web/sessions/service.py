"""SessionService implementation -- CRUD, state versioning, active run enforcement.

Uses SQLAlchemy Core with a synchronous engine. Database calls run in a
thread pool executor to avoid blocking the async event loop.
"""

from __future__ import annotations

import asyncio
import functools
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

from sqlalchemy import Engine, delete, desc, func, insert, select, update
from sqlalchemy.exc import IntegrityError

from elspeth.contracts.freeze import deep_thaw
from elspeth.web.sessions.models import (
    chat_messages_table,
    composition_states_table,
    run_events_table,
    runs_table,
    sessions_table,
)
from elspeth.web.sessions.protocol import (
    LEGAL_RUN_TRANSITIONS,
    ChatMessageRecord,
    CompositionStateData,
    CompositionStateRecord,
    RunAlreadyActiveError,
    RunRecord,
    SessionRecord,
)


class SessionServiceImpl:
    """Concrete session service backed by SQLAlchemy Core.

    All public methods are async. Database I/O runs in the default thread
    pool executor via _run_sync() so the async event loop is never blocked.
    """

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    async def _run_sync(self, func: Any, *args: Any, **kwargs: Any) -> Any:
        """Run a synchronous callable in the thread pool executor."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            functools.partial(func, *args, **kwargs),
        )

    def _now(self) -> datetime:
        return datetime.now(UTC)

    async def create_session(
        self,
        user_id: str,
        title: str,
        auth_provider_type: str,
        forked_from_session_id: UUID | None = None,
        forked_from_message_id: UUID | None = None,
    ) -> SessionRecord:
        """Create a new session and return its record."""
        session_id = uuid.uuid4()
        now = self._now()

        def _sync() -> None:
            with self._engine.begin() as conn:
                conn.execute(
                    insert(sessions_table).values(
                        id=str(session_id),
                        user_id=user_id,
                        auth_provider_type=auth_provider_type,
                        title=title,
                        created_at=now,
                        updated_at=now,
                        forked_from_session_id=str(forked_from_session_id) if forked_from_session_id else None,
                        forked_from_message_id=str(forked_from_message_id) if forked_from_message_id else None,
                    )
                )

        await self._run_sync(_sync)

        return SessionRecord(
            id=session_id,
            user_id=user_id,
            auth_provider_type=auth_provider_type,
            title=title,
            created_at=now,
            updated_at=now,
            forked_from_session_id=forked_from_session_id,
            forked_from_message_id=forked_from_message_id,
        )

    async def get_session(self, session_id: UUID) -> SessionRecord:
        """Fetch a session by ID. Raises ValueError if not found."""

        def _sync() -> Any:
            with self._engine.begin() as conn:
                return conn.execute(select(sessions_table).where(sessions_table.c.id == str(session_id))).fetchone()

        row = await self._run_sync(_sync)

        if row is None:
            raise ValueError(f"Session not found: {session_id}")

        return SessionRecord(
            id=UUID(row.id),
            user_id=row.user_id,
            auth_provider_type=row.auth_provider_type,
            title=row.title,
            created_at=row.created_at,
            updated_at=row.updated_at,
            forked_from_session_id=UUID(row.forked_from_session_id) if row.forked_from_session_id else None,
            forked_from_message_id=UUID(row.forked_from_message_id) if row.forked_from_message_id else None,
        )

    async def list_sessions(
        self,
        user_id: str,
        auth_provider_type: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[SessionRecord]:
        """List sessions for a user, ordered by updated_at descending."""

        def _sync() -> Any:
            with self._engine.begin() as conn:
                return conn.execute(
                    select(sessions_table)
                    .where(
                        sessions_table.c.user_id == user_id,
                        sessions_table.c.auth_provider_type == auth_provider_type,
                    )
                    .order_by(desc(sessions_table.c.updated_at))
                    .limit(limit)
                    .offset(offset)
                ).fetchall()

        rows = await self._run_sync(_sync)

        return [
            SessionRecord(
                id=UUID(row.id),
                user_id=row.user_id,
                auth_provider_type=row.auth_provider_type,
                title=row.title,
                created_at=row.created_at,
                updated_at=row.updated_at,
                forked_from_session_id=UUID(row.forked_from_session_id) if row.forked_from_session_id else None,
                forked_from_message_id=UUID(row.forked_from_message_id) if row.forked_from_message_id else None,
            )
            for row in rows
        ]

    async def archive_session(self, session_id: UUID) -> None:
        """Delete a session and cascade to all related records."""
        sid = str(session_id)

        def _sync() -> None:
            with self._engine.begin() as conn:
                # Delete in dependency order (children first for non-CASCADE DBs)
                # Get run IDs for this session to delete run_events
                run_ids = [r.id for r in conn.execute(select(runs_table.c.id).where(runs_table.c.session_id == sid)).fetchall()]
                if run_ids:
                    conn.execute(delete(run_events_table).where(run_events_table.c.run_id.in_(run_ids)))
                conn.execute(delete(runs_table).where(runs_table.c.session_id == sid))
                conn.execute(delete(composition_states_table).where(composition_states_table.c.session_id == sid))
                conn.execute(delete(chat_messages_table).where(chat_messages_table.c.session_id == sid))
                conn.execute(delete(sessions_table).where(sessions_table.c.id == sid))

        await self._run_sync(_sync)

    async def add_message(
        self,
        session_id: UUID,
        role: str,
        content: str,
        tool_calls: Mapping[str, Any] | None = None,
        composition_state_id: UUID | None = None,
    ) -> ChatMessageRecord:
        """Add a chat message and update the session's updated_at."""
        msg_id = uuid.uuid4()
        now = self._now()
        sid = str(session_id)

        def _sync() -> None:
            with self._engine.begin() as conn:
                conn.execute(
                    insert(chat_messages_table).values(
                        id=str(msg_id),
                        session_id=sid,
                        role=role,
                        content=content,
                        tool_calls=tool_calls,
                        created_at=now,
                        composition_state_id=str(composition_state_id) if composition_state_id else None,
                    )
                )
                conn.execute(update(sessions_table).where(sessions_table.c.id == sid).values(updated_at=now))

        await self._run_sync(_sync)

        return ChatMessageRecord(
            id=msg_id,
            session_id=session_id,
            role=role,
            content=content,
            tool_calls=tool_calls,
            created_at=now,
            composition_state_id=composition_state_id,
        )

    async def get_messages(
        self,
        session_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ChatMessageRecord]:
        """Get messages for a session, ordered by created_at ascending."""

        def _sync() -> Any:
            with self._engine.begin() as conn:
                return conn.execute(
                    select(chat_messages_table)
                    .where(chat_messages_table.c.session_id == str(session_id))
                    .order_by(chat_messages_table.c.created_at)
                    .limit(limit)
                    .offset(offset)
                ).fetchall()

        rows = await self._run_sync(_sync)

        return [
            ChatMessageRecord(
                id=UUID(row.id),
                session_id=UUID(row.session_id),
                role=row.role,
                content=row.content,
                tool_calls=row.tool_calls,
                created_at=row.created_at,
                composition_state_id=UUID(row.composition_state_id) if row.composition_state_id else None,
            )
            for row in rows
        ]

    async def save_composition_state(
        self,
        session_id: UUID,
        state: CompositionStateData,
    ) -> CompositionStateRecord:
        """Save a new immutable composition state snapshot.

        Version is max(existing versions for session) + 1, starting at 1.
        """
        state_id = uuid.uuid4()
        now = self._now()
        sid = str(session_id)

        # Seam contract A: wrap JSON columns with _version envelope
        # for schema evolution. deep_thaw() handles MappingProxyType→dict
        # and tuple→list from freeze_fields().
        def _enveloped(val: Any) -> Any:
            raw = deep_thaw(val)
            if raw is None:
                return None
            return {"_version": 1, "data": raw}

        def _sync() -> int:
            # Retry loop handles concurrent version increment (TOCTOU).
            # The UniqueConstraint on (session_id, version) is the real guard.
            for _attempt in range(3):
                try:
                    return _try_insert_state()
                except IntegrityError:
                    # The only constraint on this insert is uq_composition_state_version
                    # (PK is UUID4, FK is pre-validated). Retry with next version number.
                    continue
            raise RuntimeError(f"Failed to allocate version for session {sid} after 3 attempts")

        def _try_insert_state() -> int:
            with self._engine.begin() as conn:
                result = conn.execute(
                    select(func.max(composition_states_table.c.version)).where(composition_states_table.c.session_id == sid)
                ).scalar()
                version = (result or 0) + 1

                conn.execute(
                    insert(composition_states_table).values(
                        id=str(state_id),
                        session_id=sid,
                        version=version,
                        source=_enveloped(state.source),
                        nodes=_enveloped(state.nodes),
                        edges=_enveloped(state.edges),
                        outputs=_enveloped(state.outputs),
                        metadata_=_enveloped(state.metadata_),
                        is_valid=state.is_valid,
                        validation_errors=deep_thaw(state.validation_errors),
                        derived_from_state_id=None,
                        created_at=now,
                    )
                )
                return version

        version = await self._run_sync(_sync)

        return CompositionStateRecord(
            id=state_id,
            session_id=session_id,
            version=version,
            source=state.source,
            nodes=state.nodes,
            edges=state.edges,
            outputs=state.outputs,
            metadata_=state.metadata_,
            is_valid=state.is_valid,
            validation_errors=state.validation_errors,
            created_at=now,
            derived_from_state_id=None,
        )

    async def get_current_state(
        self,
        session_id: UUID,
    ) -> CompositionStateRecord | None:
        """Return the highest-version state for a session, or None."""

        def _sync() -> Any:
            with self._engine.begin() as conn:
                return conn.execute(
                    select(composition_states_table)
                    .where(composition_states_table.c.session_id == str(session_id))
                    .order_by(desc(composition_states_table.c.version))
                    .limit(1)
                ).fetchone()

        row = await self._run_sync(_sync)

        if row is None:
            return None

        return self._row_to_state_record(row)

    async def get_state_versions(
        self,
        session_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> list[CompositionStateRecord]:
        """Return state versions for a session, ascending order."""

        def _sync() -> Any:
            with self._engine.begin() as conn:
                return conn.execute(
                    select(composition_states_table)
                    .where(composition_states_table.c.session_id == str(session_id))
                    .order_by(composition_states_table.c.version)
                    .limit(limit)
                    .offset(offset)
                ).fetchall()

        rows = await self._run_sync(_sync)

        return [self._row_to_state_record(row) for row in rows]

    @staticmethod
    def _unwrap_envelope(val: Any) -> Any:
        """Unwrap _version envelope from a JSON column value.

        Seam contract A: JSON columns are stored with {"_version": 1, "data": ...}.
        Raises ValueError on unknown versions. Returns None for NULL columns.
        """
        if val is None:
            return None
        if isinstance(val, dict) and "_version" in val:
            if val["_version"] != 1:
                raise ValueError(f"Unknown composition state envelope version: {val['_version']}")
            return val["data"]
        raise ValueError(
            f"Composition state column has no _version envelope: {val!r}. This indicates a bug in the write path or database corruption."
        )

    def _row_to_state_record(self, row: Any) -> CompositionStateRecord:
        """Convert a SQLAlchemy row to a CompositionStateRecord.

        Seam contract A: metadata_ maps DB column metadata_ back to the
        dataclass field. JSON columns are unwrapped from their _version envelope.
        When Sub-4 provides CompositionState.from_dict(), this method becomes
        the swap point for domain object reconstruction.
        """
        # TODO(sub-4): Replace raw dict fields with CompositionState.from_dict()
        # call once Sub-4 defines it. The swap should be a single-line change.
        return CompositionStateRecord(
            id=UUID(row.id),
            session_id=UUID(row.session_id),
            version=row.version,
            source=self._unwrap_envelope(row.source),
            nodes=self._unwrap_envelope(row.nodes),
            edges=self._unwrap_envelope(row.edges),
            outputs=self._unwrap_envelope(row.outputs),
            metadata_=self._unwrap_envelope(row.metadata_),
            is_valid=row.is_valid,
            validation_errors=row.validation_errors,
            created_at=row.created_at,
            derived_from_state_id=(UUID(row.derived_from_state_id) if row.derived_from_state_id is not None else None),
        )

    async def create_run(
        self,
        session_id: UUID,
        state_id: UUID,
        pipeline_yaml: str | None = None,
    ) -> RunRecord:
        """Create a new pending run, enforcing one active run per session (B6).

        Enforced by partial unique index uq_runs_one_active_per_session
        (at most one row with status IN ('pending','running') per session_id).
        The SELECT is an early-out optimization; the index is the real guard.
        Raises RunAlreadyActiveError if a pending or running run exists.
        """
        run_id = uuid.uuid4()
        now = self._now()
        sid = str(session_id)

        def _sync() -> None:
            with self._engine.begin() as conn:
                # Early-out: check before INSERT to give a clear error message
                active = conn.execute(
                    select(runs_table.c.id).where(
                        runs_table.c.session_id == sid,
                        runs_table.c.status.in_(["pending", "running"]),
                    )
                ).fetchone()

                if active is not None:
                    raise RunAlreadyActiveError(sid)

                try:
                    conn.execute(
                        insert(runs_table).values(
                            id=str(run_id),
                            session_id=sid,
                            state_id=str(state_id),
                            status="pending",
                            started_at=now,
                            rows_processed=0,
                            rows_failed=0,
                            pipeline_yaml=pipeline_yaml,
                        )
                    )
                except IntegrityError as exc:
                    # The pre-check for active runs passed, but a concurrent insert
                    # hit the partial unique index. This is genuinely "run already active."
                    raise RunAlreadyActiveError(sid) from exc

        await self._run_sync(_sync)

        return RunRecord(
            id=run_id,
            session_id=session_id,
            state_id=state_id,
            status="pending",
            started_at=now,
            finished_at=None,
            rows_processed=0,
            rows_failed=0,
            error=None,
            landscape_run_id=None,
            pipeline_yaml=pipeline_yaml,
        )

    async def get_run(self, run_id: UUID) -> RunRecord:
        """Fetch a run by ID. Raises ValueError if not found."""

        def _sync() -> Any:
            with self._engine.begin() as conn:
                return conn.execute(select(runs_table).where(runs_table.c.id == str(run_id))).fetchone()

        row = await self._run_sync(_sync)

        if row is None:
            raise ValueError(f"Run not found: {run_id}")

        return self._row_to_run_record(row)

    async def update_run_status(
        self,
        run_id: UUID,
        status: str,
        error: str | None = None,
        landscape_run_id: str | None = None,
        rows_processed: int | None = None,
        rows_failed: int | None = None,
    ) -> None:
        """Update a run's status and optional fields.

        Enforces LEGAL_RUN_TRANSITIONS (D3). Enforces landscape_run_id
        write-once semantics (D4). Sets finished_at for terminal states
        (completed, failed, cancelled). Optional parameters only update
        the column when not None. Raises ValueError if run not found or
        transition is illegal.
        """
        now = self._now()
        rid = str(run_id)

        def _sync() -> None:
            with self._engine.begin() as conn:
                # Read current state for transition + write-once validation
                current = conn.execute(
                    select(
                        runs_table.c.status,
                        runs_table.c.landscape_run_id,
                    ).where(runs_table.c.id == rid)
                ).fetchone()

                if current is None:
                    raise ValueError(f"Run not found: {run_id}")

                # D3: Enforce legal transitions — direct access; KeyError = Tier 1 crash
                current_status = current.status
                allowed = LEGAL_RUN_TRANSITIONS[current_status]
                if status not in allowed:
                    raise ValueError(f"Illegal run transition: {current_status!r} \u2192 {status!r}. Allowed: {sorted(allowed)}")

                # D4: landscape_run_id is write-once
                if landscape_run_id is not None and current.landscape_run_id is not None:
                    raise ValueError(f"landscape_run_id already set to {current.landscape_run_id!r}; cannot overwrite")

                values: dict[str, Any] = {"status": status}
                if status in ("completed", "failed", "cancelled"):
                    values["finished_at"] = now
                if error is not None:
                    values["error"] = error
                if landscape_run_id is not None:
                    values["landscape_run_id"] = landscape_run_id
                if rows_processed is not None:
                    values["rows_processed"] = rows_processed
                if rows_failed is not None:
                    values["rows_failed"] = rows_failed

                conn.execute(update(runs_table).where(runs_table.c.id == rid).values(**values))

        await self._run_sync(_sync)

    async def get_active_run(
        self,
        session_id: UUID,
    ) -> RunRecord | None:
        """Return the pending/running run for a session, or None."""

        def _sync() -> Any:
            with self._engine.begin() as conn:
                return conn.execute(
                    select(runs_table).where(
                        runs_table.c.session_id == str(session_id),
                        runs_table.c.status.in_(["pending", "running"]),
                    )
                ).fetchone()

        row = await self._run_sync(_sync)

        if row is None:
            return None

        return self._row_to_run_record(row)

    async def get_state(self, state_id: UUID) -> CompositionStateRecord:
        """Fetch a composition state by its primary key. Raises ValueError if not found."""

        def _sync() -> Any:
            with self._engine.begin() as conn:
                return conn.execute(select(composition_states_table).where(composition_states_table.c.id == str(state_id))).fetchone()

        row = await self._run_sync(_sync)

        if row is None:
            raise ValueError(f"State not found: {state_id}")

        return self._row_to_state_record(row)

    async def set_active_state(
        self,
        session_id: UUID,
        state_id: UUID,
    ) -> CompositionStateRecord:
        """Revert to a prior state by copying it as a new version.

        Creates a new version record that is a copy of the specified prior
        version (looked up by state_id). The new record gets
        version = max(existing) + 1. Raises ValueError if state_id not
        found or does not belong to the session.
        """
        sid = str(session_id)
        new_state_id = uuid.uuid4()
        now = self._now()

        def _sync() -> tuple[Any, int]:
            # Retry loop handles concurrent version increment (TOCTOU).
            # The UniqueConstraint on (session_id, version) is the real guard.
            for _attempt in range(3):
                try:
                    return _try_insert_revert()
                except IntegrityError:
                    # The only constraint on this insert is uq_composition_state_version
                    # (PK is UUID4, FK is pre-validated). Retry with next version number.
                    continue
            raise RuntimeError(f"Failed to allocate version for session {sid} after 3 attempts")

        def _try_insert_revert() -> tuple[Any, int]:
            with self._engine.begin() as conn:
                prior_row = conn.execute(select(composition_states_table).where(composition_states_table.c.id == str(state_id))).fetchone()

                if prior_row is None:
                    raise ValueError(f"State not found: {state_id}")
                if prior_row.session_id != sid:
                    raise ValueError(f"State {state_id} does not belong to session {session_id}")

                max_version = conn.execute(
                    select(func.max(composition_states_table.c.version)).where(composition_states_table.c.session_id == sid)
                ).scalar()
                new_version = (max_version or 0) + 1

                conn.execute(
                    insert(composition_states_table).values(
                        id=str(new_state_id),
                        session_id=sid,
                        version=new_version,
                        # prior_row.* values are already enveloped — copy as-is
                        source=prior_row.source,
                        nodes=prior_row.nodes,
                        edges=prior_row.edges,
                        outputs=prior_row.outputs,
                        metadata_=prior_row.metadata_,
                        is_valid=prior_row.is_valid,
                        validation_errors=prior_row.validation_errors,
                        derived_from_state_id=str(state_id),
                        created_at=now,
                    )
                )
                return prior_row, new_version

        prior_row, new_version = await self._run_sync(_sync)

        return CompositionStateRecord(
            id=new_state_id,
            session_id=session_id,
            version=new_version,
            source=self._unwrap_envelope(prior_row.source),
            nodes=self._unwrap_envelope(prior_row.nodes),
            edges=self._unwrap_envelope(prior_row.edges),
            outputs=self._unwrap_envelope(prior_row.outputs),
            metadata_=self._unwrap_envelope(prior_row.metadata_),
            is_valid=prior_row.is_valid,
            validation_errors=prior_row.validation_errors,
            created_at=now,
            derived_from_state_id=state_id,
        )

    async def cancel_orphaned_runs(
        self,
        session_id: UUID,
        max_age_seconds: int = 3600,
    ) -> list[RunRecord]:
        """Force-cancel runs stuck in 'pending' or 'running' beyond max_age_seconds.

        Returns the list of cancelled RunRecords. Called by the execution
        service on startup and periodically to prevent orphaned runs from
        permanently blocking sessions (D5). Includes 'pending' because a
        crash between create_run() and the first update_run_status("running")
        would leave a permanently unblockable session otherwise.
        """
        sid = str(session_id)
        now = self._now()
        cutoff = now - timedelta(seconds=max_age_seconds)

        def _sync() -> list[RunRecord]:
            cancelled: list[RunRecord] = []
            with self._engine.begin() as conn:
                stale_rows = conn.execute(
                    select(runs_table).where(
                        runs_table.c.session_id == sid,
                        runs_table.c.status.in_(["pending", "running"]),
                        runs_table.c.started_at <= cutoff,
                    )
                ).fetchall()

                for row in stale_rows:
                    conn.execute(update(runs_table).where(runs_table.c.id == row.id).values(status="cancelled", finished_at=now))
                    cancelled.append(
                        RunRecord(
                            id=UUID(row.id),
                            session_id=UUID(row.session_id),
                            state_id=UUID(row.state_id),
                            status="cancelled",
                            started_at=row.started_at,
                            finished_at=now,
                            rows_processed=row.rows_processed,
                            rows_failed=row.rows_failed,
                            error=row.error,
                            landscape_run_id=row.landscape_run_id,
                            pipeline_yaml=row.pipeline_yaml,
                        )
                    )
            return cancelled

        result: list[RunRecord] = cast(list[RunRecord], await self._run_sync(_sync))
        return result

    async def cancel_all_orphaned_runs(
        self,
        max_age_seconds: int = 3600,
    ) -> int:
        """Force-cancel stale runs across all sessions.

        Called on startup to recover sessions blocked by runs orphaned
        during a previous server crash. Returns the count of cancelled runs.
        """
        now = self._now()
        cutoff = now - timedelta(seconds=max_age_seconds)

        def _sync() -> int:
            with self._engine.begin() as conn:
                stale_rows = conn.execute(
                    select(runs_table.c.id).where(
                        runs_table.c.status.in_(["pending", "running"]),
                        runs_table.c.started_at <= cutoff,
                    )
                ).fetchall()

                for row in stale_rows:
                    conn.execute(update(runs_table).where(runs_table.c.id == row.id).values(status="cancelled", finished_at=now))
                return len(stale_rows)

        return cast(int, await self._run_sync(_sync))

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
        sid = str(session_id)

        def _sync() -> int:
            with self._engine.begin() as conn:
                # Get all version IDs ordered by version DESC
                all_rows = conn.execute(
                    select(
                        composition_states_table.c.id,
                        composition_states_table.c.version,
                    )
                    .where(composition_states_table.c.session_id == sid)
                    .order_by(desc(composition_states_table.c.version))
                ).fetchall()

                if len(all_rows) <= keep_latest:
                    return 0

                # IDs to keep: the top keep_latest versions
                keep_ids = {row.id for row in all_rows[:keep_latest]}

                # IDs referenced by runs
                run_referenced = {
                    row.state_id
                    for row in conn.execute(
                        select(runs_table.c.state_id).where(
                            runs_table.c.session_id == sid,
                        )
                    ).fetchall()
                }

                # Candidates for deletion: everything not kept and not referenced
                delete_ids = [row.id for row in all_rows if row.id not in keep_ids and row.id not in run_referenced]

                if not delete_ids:
                    return 0

                result = conn.execute(delete(composition_states_table).where(composition_states_table.c.id.in_(delete_ids)))
                return result.rowcount

        return cast(int, await self._run_sync(_sync))

    async def fork_session(
        self,
        source_session_id: UUID,
        fork_message_id: UUID,
        new_message_content: str,
        user_id: str,
        auth_provider_type: str,
    ) -> tuple[SessionRecord, list[ChatMessageRecord], CompositionStateRecord | None]:
        """Fork a session from a specific user message.

        Creates a new session containing:
        1. All messages BEFORE the fork message
        2. A synthetic system message noting the fork
        3. The new edited user message
        4. Composition state copied from the fork message's pre-send state

        Returns (new_session, new_messages, copied_state_or_none).
        """
        # Load source session and verify ownership
        source_session = await self.get_session(source_session_id)
        if source_session.user_id != user_id:
            raise ValueError(f"Session {source_session_id} not owned by {user_id}")

        # Load all messages from source session
        source_messages = await self.get_messages(source_session_id, limit=10000)

        # Find the fork message — must be a user message
        fork_msg = None
        fork_idx = -1
        for i, msg in enumerate(source_messages):
            if msg.id == fork_message_id:
                fork_msg = msg
                fork_idx = i
                break

        if fork_msg is None:
            raise ValueError(f"Message {fork_message_id} not found in session {source_session_id}")
        if fork_msg.role != "user":
            raise ValueError(f"Can only fork from user messages, got role '{fork_msg.role}'")

        # Messages to copy: everything BEFORE the fork message
        messages_to_copy = source_messages[:fork_idx]

        # Get the pre-send composition state from the fork message
        pre_send_state_id = fork_msg.composition_state_id

        # Create the forked session
        title = f"{source_session.title} (fork)"
        new_session = await self.create_session(
            user_id=user_id,
            title=title,
            auth_provider_type=auth_provider_type,
            forked_from_session_id=source_session_id,
            forked_from_message_id=fork_message_id,
        )

        # Copy messages into the new session (preserving order)
        new_messages: list[ChatMessageRecord] = []
        for msg in messages_to_copy:
            copied = await self.add_message(
                new_session.id,
                msg.role,
                msg.content,
                tool_calls=msg.tool_calls,
                composition_state_id=msg.composition_state_id,
            )
            new_messages.append(copied)

        # Add synthetic system message indicating the fork
        system_msg = await self.add_message(
            new_session.id,
            "system",
            "Conversation forked from an earlier point.",
        )
        new_messages.append(system_msg)

        # Add the new edited user message with pre-send state provenance
        new_user_msg = await self.add_message(
            new_session.id,
            "user",
            new_message_content,
            composition_state_id=pre_send_state_id,
        )
        new_messages.append(new_user_msg)

        # Copy composition state into the forked session if it exists
        copied_state: CompositionStateRecord | None = None
        if pre_send_state_id is not None:
            source_state = await self.get_state(pre_send_state_id)
            state_data = CompositionStateData(
                source=source_state.source,
                nodes=source_state.nodes,
                edges=source_state.edges,
                outputs=source_state.outputs,
                metadata_=source_state.metadata_,
                is_valid=source_state.is_valid,
                validation_errors=source_state.validation_errors,
            )
            copied_state = await self.save_composition_state(
                new_session.id,
                state_data,
            )

        return new_session, new_messages, copied_state

    def _row_to_run_record(self, row: Any) -> RunRecord:
        """Convert a SQLAlchemy row to a RunRecord."""
        return RunRecord(
            id=UUID(row.id),
            session_id=UUID(row.session_id),
            state_id=UUID(row.state_id),
            status=row.status,
            started_at=row.started_at,
            finished_at=row.finished_at,
            rows_processed=row.rows_processed,
            rows_failed=row.rows_failed,
            error=row.error,
            landscape_run_id=row.landscape_run_id,
            pipeline_yaml=row.pipeline_yaml,
        )
