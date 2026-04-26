"""Session API routes -- /api/sessions/* with IDOR protection.

All endpoints require authentication via Depends(get_current_user).
Session-scoped endpoints verify ownership before any business logic.
"""

from __future__ import annotations

import asyncio
from typing import cast
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from litellm.exceptions import APIError as LiteLLMAPIError
from litellm.exceptions import AuthenticationError as LiteLLMAuthError
from sqlalchemy.exc import SQLAlchemyError

from elspeth.contracts.errors import AuditIntegrityError
from elspeth.contracts.freeze import deep_thaw
from elspeth.web.auth.middleware import get_current_user
from elspeth.web.auth.models import UserIdentity
from elspeth.web.blobs.protocol import BlobQuotaExceededError, BlobServiceProtocol
from elspeth.web.composer.progress import (
    ComposerProgressEvent,
    ComposerProgressRegistry,
    ComposerProgressSink,
    ComposerProgressSnapshot,
)
from elspeth.web.composer.protocol import (
    ComposerConvergenceError,
    ComposerPluginCrashError,
    ComposerService,
    ComposerServiceError,
)
from elspeth.web.composer.redaction import redact_source_storage_path
from elspeth.web.composer.state import CompositionState, PipelineMetadata, ValidationEntry, ValidationSummary
from elspeth.web.composer.yaml_generator import generate_yaml
from elspeth.web.middleware.rate_limit import ComposerRateLimiter, get_rate_limiter
from elspeth.web.sessions.converters import state_from_record as _state_from_record
from elspeth.web.sessions.protocol import (
    ChatMessageRecord,
    CompositionStateData,
    CompositionStateRecord,
    InvalidForkTargetError,
    SessionRecord,
    SessionServiceProtocol,
)
from elspeth.web.sessions.schemas import (
    ChatMessageResponse,
    CompositionStateResponse,
    CreateSessionRequest,
    ForkSessionRequest,
    ForkSessionResponse,
    MessageWithStateResponse,
    RevertStateRequest,
    RunResponse,
    SendMessageRequest,
    SessionResponse,
    ValidationEntryResponse,
)

slog = structlog.get_logger()


class _SessionComposeLockRegistry:
    """Per-session compose/recompose locks.

    Lazily creates asyncio.Lock instances under a running event loop so the
    registry can live on app.state without needing sync-time initialization in
    create_app().
    """

    def __init__(self) -> None:
        self._session_locks: dict[str, asyncio.Lock] = {}
        self._locks_lock: asyncio.Lock | None = None

    def _ensure_locks_lock(self) -> asyncio.Lock:
        if self._locks_lock is None:
            self._locks_lock = asyncio.Lock()
        return self._locks_lock

    async def get_lock(self, session_id: str) -> asyncio.Lock:
        async with self._ensure_locks_lock():
            if session_id not in self._session_locks:
                self._session_locks[session_id] = asyncio.Lock()
            return self._session_locks[session_id]

    async def cleanup_session_lock(self, session_id: str) -> None:
        async with self._ensure_locks_lock():
            if session_id in self._session_locks:
                self._session_locks.pop(session_id)


def _get_session_compose_lock_registry(request: Request) -> _SessionComposeLockRegistry:
    """Return the app-scoped compose lock registry, creating it on first use."""
    registry = getattr(request.app.state, "session_compose_lock_registry", None)
    if registry is None:
        registry = _SessionComposeLockRegistry()
        request.app.state.session_compose_lock_registry = registry
    return registry


def _get_composer_progress_registry(request: Request) -> ComposerProgressRegistry:
    """Return the app-scoped composer progress registry."""
    return cast(ComposerProgressRegistry, request.app.state.composer_progress_registry)


def _composer_progress_sink(
    registry: ComposerProgressRegistry,
    *,
    session_id: str,
    request_id: str | None,
) -> ComposerProgressSink:
    """Bind a registry sink to one session/request."""

    async def _publish(event: ComposerProgressEvent) -> None:
        await registry.publish(session_id=session_id, request_id=request_id, event=event)

    return _publish


async def _publish_progress(
    registry: ComposerProgressRegistry,
    *,
    session_id: str,
    request_id: str | None,
    event: ComposerProgressEvent,
) -> None:
    await registry.publish(session_id=session_id, request_id=request_id, event=event)


def _session_response(session: SessionRecord) -> SessionResponse:
    """Convert a SessionRecord to a SessionResponse."""
    return SessionResponse(
        id=str(session.id),
        user_id=session.user_id,
        title=session.title,
        created_at=session.created_at,
        updated_at=session.updated_at,
        forked_from_session_id=str(session.forked_from_session_id) if session.forked_from_session_id else None,
        forked_from_message_id=str(session.forked_from_message_id) if session.forked_from_message_id else None,
    )


def _message_response(msg: ChatMessageRecord) -> ChatMessageResponse:
    """Convert a ChatMessageRecord to a ChatMessageResponse."""
    return ChatMessageResponse(
        id=str(msg.id),
        session_id=str(msg.session_id),
        role=msg.role,
        content=msg.content,
        tool_calls=deep_thaw(msg.tool_calls) if msg.tool_calls is not None else None,
        created_at=msg.created_at,
        composition_state_id=str(msg.composition_state_id) if msg.composition_state_id else None,
    )


def _state_response(
    state: CompositionStateRecord,
    live_validation: ValidationSummary | None = None,
) -> CompositionStateResponse:
    """Convert a CompositionStateRecord to a CompositionStateResponse.

    Unfreezes container fields (MappingProxyType, tuple) into mutable
    dicts/lists so redact_source_storage_path can mutate them in place.

    When live_validation is provided (from a just-computed validate() call),
    transient warnings and suggestions are included in the response.
    Historical loads pass None, producing null for these fields.
    """
    # B4: Redact internal storage paths from blob-backed sources
    source_data = deep_thaw(state.source)
    if source_data is not None:
        redacted = redact_source_storage_path({"source": source_data})
        source_data = redacted.get("source", source_data)

    return CompositionStateResponse(
        id=str(state.id),
        session_id=str(state.session_id),
        version=state.version,
        source=source_data,
        nodes=deep_thaw(state.nodes),
        edges=deep_thaw(state.edges),
        outputs=deep_thaw(state.outputs),
        metadata=deep_thaw(state.metadata_),
        is_valid=state.is_valid,
        validation_errors=deep_thaw(state.validation_errors),
        validation_warnings=[
            ValidationEntryResponse(component=e.component, message=e.message, severity=e.severity) for e in live_validation.warnings
        ]
        if live_validation is not None
        else None,
        validation_suggestions=[
            ValidationEntryResponse(component=e.component, message=e.message, severity=e.severity) for e in live_validation.suggestions
        ]
        if live_validation is not None
        else None,
        derived_from_state_id=str(state.derived_from_state_id) if state.derived_from_state_id is not None else None,
        created_at=state.created_at,
    )


async def _verify_session_ownership(
    session_id: UUID,
    user: UserIdentity,
    request: Request,
) -> SessionRecord:
    """Verify the session exists and belongs to the current user.

    Returns 404 (not 403) to avoid leaking session existence (IDOR, W5).
    """
    service: SessionServiceProtocol = request.app.state.session_service
    try:
        session = await service.get_session(session_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Session not found") from None

    settings = request.app.state.settings
    if session.user_id != user.user_id or session.auth_provider_type != settings.auth_provider:
        raise HTTPException(status_code=404, detail="Session not found")

    return session


async def _handle_convergence_error(
    exc: ComposerConvergenceError,
    service: SessionServiceProtocol,
    session_id: UUID,
    log_prefix: str,
) -> dict[str, object]:
    """Build 422 response body and persist partial state for convergence errors.

    Shared by send_message and recompose — only the structlog event prefix
    differs between callers.

    Args:
        exc: The convergence error with optional partial_state
        service: Session service for DB persistence
        session_id: Session to persist partial state to
        log_prefix: Prefix for structlog event names (e.g. "convergence" or "recompose_convergence")

    Returns:
        Response body dict for HTTPException(status_code=422)
    """
    response_body: dict[str, object] = {
        "error_type": "convergence",
        "detail": str(exc),
        "turns_used": exc.max_turns,
        "budget_exhausted": exc.budget_exhausted,
    }
    if exc.partial_state is not None:
        # Validate guard: partial_state from the LLM loop may be
        # structurally damaged. Catch data-shape errors so we can
        # still persist with is_valid=False rather than losing it.
        try:
            validation = exc.partial_state.validate()
        except (ValueError, TypeError, KeyError) as val_err:
            # Class name only: ``str(val_err)`` can surface fragments of
            # the partial composition state (user-authored source text,
            # node options) that the validator was mid-way through
            # inspecting. Symmetric with the sibling handler
            # _handle_plugin_crash, hardened in 302dd34d.
            slog.warning(
                f"{log_prefix}_validation_failed",
                session_id=str(session_id),
                exc_class=type(val_err).__name__,
            )
            validation = ValidationSummary(
                is_valid=False,
                errors=(ValidationEntry("validation", "validation_failed", "high"),),
            )

        # Persistence guard: DB write failure should not upgrade the
        # response from 422 (convergence error) to 500 (internal).
        #
        # SQLAlchemyError ONLY — narrowed per CLAUDE.md Tier 1 semantics.
        # ``state_d = exc.partial_state.to_dict()`` and the subsequent
        # ``CompositionStateData(...)`` construction are OUR code operating
        # on OUR dataclass (``CompositionState``). A ``TypeError`` /
        # ``KeyError`` raised here is a broken invariant between our
        # dataclass and our DTO — a Tier 1 bug — and MUST propagate and
        # crash the request rather than being laundered into a soft
        # ``partial_state_save_failed=True``. The earlier ``validate()``
        # guard is the only place those classes are acceptable: ``validate``
        # is defined to tolerate structurally damaged partial state, which
        # is exactly the state we arrive here with.
        try:
            state_d = exc.partial_state.to_dict()
            state_data = CompositionStateData(
                source=state_d["source"],
                nodes=state_d["nodes"],
                edges=state_d["edges"],
                outputs=state_d["outputs"],
                metadata_=state_d["metadata"],
                is_valid=validation.is_valid,
                validation_errors=[e.message for e in validation.errors] if validation.errors else None,
            )
            await service.save_composition_state(session_id, state_data)
            response_body["partial_state"] = redact_source_storage_path(state_d)
        except SQLAlchemyError as save_err:
            # Full SQLAlchemyError family — ``IntegrityError`` alone would
            # let ``OperationalError`` (lock timeout / pool disconnect /
            # deadlock), ``ProgrammingError`` (schema drift), and siblings
            # escape, upgrading 422 → unstructured 500.
            # exc_info deliberately omitted: SQLAlchemyError __cause__
            # chains can carry DB connection strings, schema introspection
            # detail, or operational secrets that structured server logs
            # must not retain.
            slog.error(
                f"{log_prefix}_partial_state_save_failed",
                session_id=str(session_id),
                exc_class=type(save_err).__name__,
            )
            response_body["partial_state_save_failed"] = True
            # Class name only. ``str(save_err)`` on SQLAlchemyError
            # subclasses expands to ``[SQL: ...]`` + ``[parameters: ...]``
            # (the bound composition-state payload, which may reference
            # secrets) and appends ``__cause__`` text that can carry DB
            # URLs or credentials on ``OperationalError``. The slog above
            # is the triage surface; the HTTP body must not re-expose the
            # same material the ``exc_info`` omission was protecting.
            response_body["partial_state_save_error"] = type(save_err).__name__

    return response_body


async def _handle_plugin_crash(
    exc: ComposerPluginCrashError,
    service: SessionServiceProtocol,
    session_id: UUID,
    user_id: str,
    log_prefix: str,
) -> dict[str, object]:
    """Build 500 response body and persist partial state for plugin crashes.

    Symmetric with :func:`_handle_convergence_error` — same validation
    guard, same persistence guard, same response-body shape. The only
    differences are the exception class and the HTTP status (500 vs 422):
    a plugin crash is a server-side bug, not a user-driven failure.

    Args:
        exc: The plugin-crash wrapper with optional ``partial_state``.
        service: Session service for DB persistence of partial state.
        session_id: Session to persist partial state to.
        user_id: Authenticated user id (logged for triage).
        log_prefix: Prefix for structlog event names
            (e.g. "compose" or "recompose").

    Returns:
        Response body dict for ``HTTPException(status_code=500, ...)``.
    """
    response_body: dict[str, object] = {
        "error_type": "composer_plugin_error",
        "detail": ("A composer plugin crashed; see server logs for the traceback. This is not a user-retryable error."),
    }

    if exc.partial_state is not None:
        # Validate guard: partial_state was captured mid-compose — it may
        # be structurally damaged. Catch data-shape errors so we still
        # persist with is_valid=False rather than losing the row.
        try:
            validation = exc.partial_state.validate()
        except (ValueError, TypeError, KeyError) as val_err:
            # No exc_info: val_err may carry references to the same
            # secret-bearing state the plugin crash was mid-way through
            # mutating.
            slog.warning(
                f"{log_prefix}_plugin_crash_validation_failed",
                session_id=str(session_id),
                exc_class=type(val_err).__name__,
            )
            validation = ValidationSummary(
                is_valid=False,
                errors=(ValidationEntry("validation", "validation_failed", "high"),),
            )

        # Persistence guard: DB write failure MUST NOT mask the original
        # plugin crash (response stays as the 500 below, the save failure
        # is recorded as a separate audit-system-failure slog event).
        #
        # SQLAlchemyError ONLY — narrowed per CLAUDE.md Tier 1 semantics.
        # ``to_dict()`` / ``CompositionStateData(...)`` are OUR code on OUR
        # dataclass; ``TypeError`` / ``KeyError`` from this block is a
        # broken invariant (Tier 1 bug) and must propagate. Symmetric with
        # ``_handle_convergence_error``; see the comment there for the full
        # rationale.
        try:
            state_d = exc.partial_state.to_dict()
            state_data = CompositionStateData(
                source=state_d["source"],
                nodes=state_d["nodes"],
                edges=state_d["edges"],
                outputs=state_d["outputs"],
                metadata_=state_d["metadata"],
                is_valid=validation.is_valid,
                validation_errors=[e.message for e in validation.errors] if validation.errors else None,
            )
            await service.save_composition_state(session_id, state_data)
        except SQLAlchemyError as save_err:
            # Full SQLAlchemyError family — a narrow ``IntegrityError``
            # catch would let ``OperationalError`` / ``ProgrammingError`` /
            # siblings escape and mask the primary plugin-crash response.
            # exc_info deliberately omitted: ``str(save_err)`` and
            # ``__cause__`` text can carry SQL + bound parameters (the
            # composition-state payload, which may reference secrets) and
            # DB connection strings on ``OperationalError``.
            slog.error(
                f"{log_prefix}_plugin_crash_partial_state_save_failed",
                session_id=str(session_id),
                exc_class=type(save_err).__name__,
            )
            # Symmetry with _handle_convergence_error: frontend recovery UX
            # needs the same ``partial_state_save_failed`` signal on the
            # 500 path it already branches on for the 422 path. Without
            # this, a plugin crash whose partial-state persist also failed
            # looks identical to a plugin crash that succeeded in
            # persisting — the UI can't distinguish "state is captured,
            # safe to retry later" from "state is lost, start over."
            # Class name only; see the save_error comment in
            # _handle_convergence_error for the leak rationale.
            response_body["partial_state_save_failed"] = True
            response_body["partial_state_save_error"] = type(save_err).__name__

    # exc_info deliberately omitted: exc.original_exc / its __cause__ chain
    # may carry DB URLs, filesystem paths, or secret fragments. The
    # structured exc_class + session_id correlation is the complete
    # triage surface. The broader slog-for-run-events migration is
    # tracked in elspeth-940bfe3a0d.
    slog.error(
        f"{log_prefix}_plugin_crash",
        session_id=str(session_id),
        user_id=user_id,
        exc_class=exc.exc_class,
    )

    return response_body


def create_session_router() -> APIRouter:
    """Create the session router with /api/sessions prefix."""
    router = APIRouter(prefix="/api/sessions", tags=["sessions"])

    @router.post("", status_code=201, response_model=SessionResponse)
    async def create_session(
        body: CreateSessionRequest,
        request: Request,
        user: UserIdentity = Depends(get_current_user),  # noqa: B008
    ) -> SessionResponse:
        """Create a new session for the authenticated user."""
        service = request.app.state.session_service
        settings = request.app.state.settings
        session = await service.create_session(
            user.user_id,
            body.title,
            settings.auth_provider,
        )
        return _session_response(session)

    @router.get("", response_model=list[SessionResponse])
    async def list_sessions(
        request: Request,
        user: UserIdentity = Depends(get_current_user),  # noqa: B008
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
    ) -> list[SessionResponse]:
        """List sessions for the authenticated user."""
        service = request.app.state.session_service
        settings = request.app.state.settings
        sessions = await service.list_sessions(
            user.user_id,
            settings.auth_provider,
            limit=limit,
            offset=offset,
        )
        return [_session_response(s) for s in sessions]

    @router.get("/{session_id}", response_model=SessionResponse)
    async def get_session(
        session_id: UUID,
        request: Request,
        user: UserIdentity = Depends(get_current_user),  # noqa: B008
    ) -> SessionResponse:
        """Get a single session. IDOR-protected."""
        session = await _verify_session_ownership(session_id, user, request)
        return _session_response(session)

    @router.get(
        "/{session_id}/composer-progress",
        response_model=ComposerProgressSnapshot,
    )
    async def get_composer_progress(
        session_id: UUID,
        request: Request,
        user: UserIdentity = Depends(get_current_user),  # noqa: B008
    ) -> ComposerProgressSnapshot:
        """Return the latest provider-safe composer progress for a session."""
        session = await _verify_session_ownership(session_id, user, request)
        registry = _get_composer_progress_registry(request)
        return await registry.get_latest(str(session.id))

    @router.delete("/{session_id}", status_code=204)
    async def delete_session(
        session_id: UUID,
        request: Request,
        user: UserIdentity = Depends(get_current_user),  # noqa: B008
    ) -> None:
        """Archive (delete) a session and all associated data.

        Rejects deletion while a pipeline run is active — archive_session()
        would delete run rows and blob directories out from under the
        background worker, causing status update failures and data loss.
        """
        session = await _verify_session_ownership(session_id, user, request)
        service = request.app.state.session_service

        active_run = await service.get_active_run(session.id)
        if active_run is not None:
            raise HTTPException(
                status_code=409,
                detail="Cannot delete session while a pipeline run is active. Cancel the run first.",
            )

        try:
            await service.archive_session(session.id)
        finally:
            # Clean up ephemeral per-session state regardless of archive outcome.
            # If archive fails, the session still exists and a retry will re-enter
            # this path. The lock cleanup is idempotent.
            execution_service = request.app.state.execution_service
            execution_service.cleanup_session_lock(str(session.id))
            compose_lock_registry = _get_session_compose_lock_registry(request)
            await compose_lock_registry.cleanup_session_lock(str(session.id))
            progress_registry = _get_composer_progress_registry(request)
            await progress_registry.clear(str(session.id))

    @router.post(
        "/{session_id}/messages",
        response_model=MessageWithStateResponse,
    )
    async def send_message(
        session_id: UUID,
        body: SendMessageRequest,
        request: Request,
        user: UserIdentity = Depends(get_current_user),  # noqa: B008
        rate_limiter: ComposerRateLimiter = Depends(get_rate_limiter),  # noqa: B008
    ) -> MessageWithStateResponse:
        """Send a user message, run the LLM composer, persist results.

        1. Rate limit check (per-user).
        2. Load or create the current CompositionState (pre-send provenance).
        3. Persist the user message with pre-send state_id.
        4. Pre-fetch chat history for the composer.
        5. Run the LLM composition loop.
        6. Save state if version changed (post-compose provenance).
        7. Persist the assistant response message with post-compose state_id.
        8. Return the assistant message and (optionally) the new state.
        """
        # 0. Rate limit check — before any work
        await rate_limiter.check(user.user_id)

        session = await _verify_session_ownership(session_id, user, request)
        service: SessionServiceProtocol = request.app.state.session_service
        compose_lock = await _get_session_compose_lock_registry(request).get_lock(str(session.id))
        async with compose_lock:
            # 1. Load or create CompositionState — needed before user message
            #    for pre-send provenance (AD-7: user msg records what user saw).
            state_record = await service.get_current_state(session.id)
            if state_record is None:
                state = CompositionState(
                    source=None,
                    nodes=(),
                    edges=(),
                    outputs=(),
                    metadata=PipelineMetadata(),
                    version=1,
                )
                pre_send_state_id: UUID | None = None
            else:
                state = _state_from_record(state_record)
                # If client provided a state_id, verify it belongs to this session.
                # Use client-asserted state for provenance (AD-2) — it reflects
                # what the user was looking at, which may differ from current if
                # another tab mutated state.
                if body.state_id is not None:
                    client_state_id = body.state_id
                    # Two 404 paths below return byte-identical bodies by
                    # design. The commit that introduced this validation
                    # called the RuntimeError/ValueError mapping
                    # "load-bearing ... to avoid leaking other sessions'
                    # state existence" — but distinguishable 404 *details*
                    # would leak exactly that (an attacker could observe
                    # "State not found" vs "State not found for this
                    # session" and conclude the UUID exists in some OTHER
                    # user's session, which is the IDOR information leak
                    # the check exists to prevent). Keep both details
                    # identical; if a future refactor needs diagnostic
                    # precision, route it through structured audit/
                    # telemetry (server-side only), not through the HTTP
                    # response body.
                    try:
                        client_state = await service.get_state(client_state_id)
                    except ValueError:
                        raise HTTPException(
                            status_code=404,
                            detail="State not found",
                        ) from None
                    if client_state.session_id != session.id:
                        raise HTTPException(
                            status_code=404,
                            detail="State not found",
                        )
                    pre_send_state_id = client_state_id
                else:
                    pre_send_state_id = state_record.id

            # 2. Persist user message with pre-send provenance.
            # Keep the inserted row so the subsequent snapshot can prove
            # it is composing against the transcript that actually ends
            # at this request's user turn.
            user_msg = await service.add_message(
                session.id,
                "user",
                body.content,
                composition_state_id=pre_send_state_id,
            )
            progress_registry = _get_composer_progress_registry(request)
            progress_sink = _composer_progress_sink(
                progress_registry,
                session_id=str(session.id),
                request_id=str(user_msg.id),
            )
            await _publish_progress(
                progress_registry,
                session_id=str(session.id),
                request_id=str(user_msg.id),
                event=ComposerProgressEvent(
                    phase="starting",
                    headline="I'm reading your request and current pipeline.",
                    evidence=("The request was accepted for this session.",),
                    likely_next="ELSPETH will prepare the composer prompt with the current pipeline.",
                ),
            )

            # 3. Pre-fetch chat history as plain dicts (seam contract B)
            # Pass limit=None to fetch the full conversation — the default
            # limit=100 would silently drop recent context once a session
            # exceeds 100 turns, causing the LLM to lose conversation state.
            # Exclude the just-persisted user message — the composer receives
            # it separately via body.content and appends it in _build_messages.
            records = await service.get_messages(session.id, limit=None)
            if not records or records[-1].id != user_msg.id:
                raise AuditIntegrityError(
                    "Tier 1 audit anomaly: send_message transcript snapshot "
                    f"for session {session.id} does not end at inserted user "
                    f"message {user_msg.id}. Refusing to compose against "
                    "interleaved session history."
                )
            chat_messages = [{"role": r.role, "content": r.content} for r in records[:-1]]

            # 4. Run the LLM composition loop
            composer: ComposerService = request.app.state.composer_service
            try:
                result = await composer.compose(
                    body.content,
                    chat_messages,
                    state,
                    session_id=str(session_id),
                    user_id=str(user.user_id),
                    progress=progress_sink,
                )
            except ComposerConvergenceError as exc:
                await _publish_progress(
                    progress_registry,
                    session_id=str(session.id),
                    request_id=str(user_msg.id),
                    event=ComposerProgressEvent(
                        phase="failed",
                        headline="The composer could not finish this request.",
                        evidence=("The bounded composer loop stopped before a final answer.",),
                        likely_next="Try a smaller request or retry from the visible user message.",
                    ),
                )
                response_body = await _handle_convergence_error(exc, service, session.id, "convergence")
                raise HTTPException(status_code=422, detail=response_body) from exc
            except LiteLLMAuthError as exc:
                # ``str(exc)`` on LiteLLM exceptions can embed the provider
                # name, model ID, request payload fragments, and — on
                # certain provider code paths — the upstream HTTP response
                # body, which has been observed to echo the Authorization
                # header.  Redact the HTTP ``detail`` field to the class
                # name only; route the full exception to structured
                # server-side logging via ``slog.error`` with session
                # correlation.  Mirrors the ``partial_state_save_error``
                # contract on the SQLAlchemy 422 path in
                # ``_handle_convergence_error`` above.
                # exc_info deliberately omitted for the same reason
                # SQLAlchemy ``exc_info`` is dropped in the canonical
                # narrow-catch sites: ``__cause__`` chains on these
                # exception classes can carry upstream provider detail
                # that must not be retained in structured logs either.
                slog.error(
                    "compose_llm_auth_error",
                    session_id=str(session_id),
                    exc_class=type(exc).__name__,
                )
                await _publish_progress(
                    progress_registry,
                    session_id=str(session.id),
                    request_id=str(user_msg.id),
                    event=ComposerProgressEvent(
                        phase="failed",
                        headline="The composer model is not available.",
                        evidence=("The model provider rejected the composer request.",),
                        likely_next="Check the composer provider configuration before retrying.",
                    ),
                )
                raise HTTPException(
                    status_code=502,
                    detail={"error_type": "llm_auth_error", "detail": type(exc).__name__},
                ) from exc
            except LiteLLMAPIError as exc:
                # Same redaction rationale as the auth-error block above.
                # ``LiteLLMAPIError`` message shape varies by provider (OpenAI,
                # Azure OpenAI, Anthropic, Bedrock) and can include
                # rate-limit window details, account/tenant identifiers,
                # and upstream request IDs that are operator-only material.
                slog.error(
                    "compose_llm_unavailable",
                    session_id=str(session_id),
                    exc_class=type(exc).__name__,
                )
                await _publish_progress(
                    progress_registry,
                    session_id=str(session.id),
                    request_id=str(user_msg.id),
                    event=ComposerProgressEvent(
                        phase="failed",
                        headline="The composer model is temporarily unavailable.",
                        evidence=("The model provider did not complete the request.",),
                        likely_next="Retry when the provider is available.",
                    ),
                )
                raise HTTPException(
                    status_code=502,
                    detail={"error_type": "llm_unavailable", "detail": type(exc).__name__},
                ) from exc
            except ComposerPluginCrashError as crash:
                # Plugin-crash path: _compose_loop wraps any non-ToolArgumentError
                # escape from execute_tool into ComposerPluginCrashError carrying
                # partial_state — the accumulated mutations from earlier successful
                # tool calls within the same request. _handle_plugin_crash persists
                # that state into composition_states symmetrically with the
                # convergence-error path, so recompose does not lose those
                # mutations. The HTTP response body is fully redacted; the cause
                # chain is preserved via `from crash.original_exc` for the ASGI /
                # server-level error machinery only.
                #
                # MUST be caught BEFORE the generic `except ComposerServiceError`
                # below — ComposerPluginCrashError inherits from
                # ComposerServiceError (so it isn't caught by a later bare
                # Exception or mistakenly promoted by the route's convergence
                # handler), and Python evaluates except clauses top-to-bottom.
                # Inverting this order routes plugin crashes into the 502
                # composer_error branch, re-introducing the silent-laundering
                # behaviour this plan exists to eliminate.
                response_body = await _handle_plugin_crash(
                    crash,
                    service,
                    session.id,
                    str(user.user_id),
                    "compose",
                )
                await _publish_progress(
                    progress_registry,
                    session_id=str(session.id),
                    request_id=str(user_msg.id),
                    event=ComposerProgressEvent(
                        phase="failed",
                        headline="The composer could not safely finish this request.",
                        evidence=("A pipeline tool failed on the server side.",),
                        likely_next="Review the visible error message, then retry after the issue is resolved.",
                    ),
                )
                raise HTTPException(status_code=500, detail=response_body) from crash.original_exc
            except ComposerServiceError as exc:
                await _publish_progress(
                    progress_registry,
                    session_id=str(session.id),
                    request_id=str(user_msg.id),
                    event=ComposerProgressEvent(
                        phase="failed",
                        headline="The composer could not finish this request.",
                        evidence=("Prompt preparation or composer service setup failed.",),
                        likely_next="Retry once the composer service is available.",
                    ),
                )
                raise HTTPException(
                    status_code=502,
                    detail={"error_type": "composer_error", "detail": str(exc)},
                ) from exc

            # 5. Save state if version changed — post-compose provenance
            state_response: CompositionStateResponse | None = None
            post_compose_state_id: UUID | None = pre_send_state_id
            if result.state.version != state.version:
                await _publish_progress(
                    progress_registry,
                    session_id=str(session.id),
                    request_id=str(user_msg.id),
                    event=ComposerProgressEvent(
                        phase="validating",
                        headline="The composer has updated the pipeline and is validating the result.",
                        evidence=("The updated pipeline state is being checked before persistence.",),
                        likely_next="ELSPETH will save the validated pipeline snapshot.",
                    ),
                )
                state_d = result.state.to_dict()
                validation = result.state.validate()
                state_data = CompositionStateData(
                    source=state_d["source"],
                    nodes=state_d["nodes"],
                    edges=state_d["edges"],
                    outputs=state_d["outputs"],
                    metadata_=state_d["metadata"],
                    is_valid=validation.is_valid,
                    validation_errors=[e.message for e in validation.errors] if validation.errors else None,
                )
                await _publish_progress(
                    progress_registry,
                    session_id=str(session.id),
                    request_id=str(user_msg.id),
                    event=ComposerProgressEvent(
                        phase="saving",
                        headline="ELSPETH is saving the pipeline update.",
                        evidence=("A new composition state version is being stored for this session.",),
                        likely_next="The assistant response will appear after the save completes.",
                    ),
                )
                new_state_record = await service.save_composition_state(
                    session.id,
                    state_data,
                )
                state_response = _state_response(new_state_record, live_validation=validation)
                post_compose_state_id = new_state_record.id

            # 6. Persist assistant message with post-compose provenance
            assistant_msg = await service.add_message(
                session.id,
                "assistant",
                result.message,
                composition_state_id=post_compose_state_id,
            )
            await _publish_progress(
                progress_registry,
                session_id=str(session.id),
                request_id=str(user_msg.id),
                event=ComposerProgressEvent(
                    phase="complete",
                    headline="The composer has updated the pipeline."
                    if result.state.version != state.version
                    else "The composer response is ready.",
                    evidence=("The assistant response has been saved for this session.",),
                    likely_next="Review the response and current pipeline.",
                ),
            )

            # 7. Return response
            return MessageWithStateResponse(
                message=_message_response(assistant_msg),
                state=state_response,
            )

    @router.post(
        "/{session_id}/recompose",
        response_model=MessageWithStateResponse,
    )
    async def recompose(
        session_id: UUID,
        request: Request,
        user: UserIdentity = Depends(get_current_user),  # noqa: B008
        rate_limiter: ComposerRateLimiter = Depends(get_rate_limiter),  # noqa: B008
    ) -> MessageWithStateResponse:
        """Re-run the composer without inserting a new user message.

        Used by the frontend retry flow when the original send_message
        persisted the user message but the composer failed. Skips step 2
        of send_message (user message insertion) and uses the existing
        conversation history.
        """
        await rate_limiter.check(user.user_id)
        session = await _verify_session_ownership(session_id, user, request)
        service: SessionServiceProtocol = request.app.state.session_service
        compose_lock = await _get_session_compose_lock_registry(request).get_lock(str(session.id))
        async with compose_lock:
            # Load current state
            state_record = await service.get_current_state(session.id)
            if state_record is None:
                state = CompositionState(
                    source=None,
                    nodes=(),
                    edges=(),
                    outputs=(),
                    metadata=PipelineMetadata(),
                    version=1,
                )
                pre_send_state_id: UUID | None = None
            else:
                state = _state_from_record(state_record)
                pre_send_state_id = state_record.id

            # Fetch full chat history — the last message must be the user turn
            # that failed.  Reject if it's not, since blindly dropping
            # records[-1] would corrupt the conversation transcript.
            records = await service.get_messages(session.id, limit=None)
            if not records:
                raise HTTPException(status_code=400, detail="No messages to recompose from")
            if records[-1].role != "user":
                raise HTTPException(
                    status_code=409,
                    detail="Cannot recompose: the last message is not a user message. "
                    "Recompose is only valid when the most recent message is the "
                    "user turn whose composition failed.",
                )

            last_user_content = records[-1].content
            request_id = str(records[-1].id)
            progress_registry = _get_composer_progress_registry(request)
            progress_sink = _composer_progress_sink(
                progress_registry,
                session_id=str(session.id),
                request_id=request_id,
            )
            await _publish_progress(
                progress_registry,
                session_id=str(session.id),
                request_id=request_id,
                event=ComposerProgressEvent(
                    phase="starting",
                    headline="I'm rereading your request and current pipeline.",
                    evidence=("The retry was accepted for this session.",),
                    likely_next="ELSPETH will prepare the composer prompt with the current pipeline.",
                ),
            )
            # Exclude the last user message — the composer receives it
            # separately via the message arg and appends it in _build_messages.
            chat_messages = [{"role": r.role, "content": r.content} for r in records[:-1]]

            # Run the LLM composition loop
            composer: ComposerService = request.app.state.composer_service
            try:
                result = await composer.compose(
                    last_user_content,
                    chat_messages,
                    state,
                    session_id=str(session_id),
                    user_id=str(user.user_id),
                    progress=progress_sink,
                )
            except ComposerConvergenceError as exc:
                await _publish_progress(
                    progress_registry,
                    session_id=str(session.id),
                    request_id=request_id,
                    event=ComposerProgressEvent(
                        phase="failed",
                        headline="The composer could not finish this retry.",
                        evidence=("The bounded composer loop stopped before a final answer.",),
                        likely_next="Try a smaller request or edit the visible user message.",
                    ),
                )
                response_body = await _handle_convergence_error(exc, service, session.id, "recompose_convergence")
                raise HTTPException(status_code=422, detail=response_body) from exc
            except LiteLLMAuthError as exc:
                # Recompose mirror of the redaction contract in send_message
                # (see block comment there for full rationale).  The two
                # paths MUST carry byte-identical response shapes and
                # redaction granularity — any future divergence becomes a
                # selective leak surface (attacker picks whichever endpoint
                # still echoes str(exc)).
                slog.error(
                    "recompose_llm_auth_error",
                    session_id=str(session_id),
                    exc_class=type(exc).__name__,
                )
                await _publish_progress(
                    progress_registry,
                    session_id=str(session.id),
                    request_id=request_id,
                    event=ComposerProgressEvent(
                        phase="failed",
                        headline="The composer model is not available.",
                        evidence=("The model provider rejected the composer request.",),
                        likely_next="Check the composer provider configuration before retrying.",
                    ),
                )
                raise HTTPException(
                    status_code=502,
                    detail={"error_type": "llm_auth_error", "detail": type(exc).__name__},
                ) from exc
            except LiteLLMAPIError as exc:
                slog.error(
                    "recompose_llm_unavailable",
                    session_id=str(session_id),
                    exc_class=type(exc).__name__,
                )
                await _publish_progress(
                    progress_registry,
                    session_id=str(session.id),
                    request_id=request_id,
                    event=ComposerProgressEvent(
                        phase="failed",
                        headline="The composer model is temporarily unavailable.",
                        evidence=("The model provider did not complete the request.",),
                        likely_next="Retry when the provider is available.",
                    ),
                )
                raise HTTPException(
                    status_code=502,
                    detail={"error_type": "llm_unavailable", "detail": type(exc).__name__},
                ) from exc
            except ComposerPluginCrashError as crash:
                # Plugin-crash path: mirror /messages handler. See the send_message
                # block comment for full rationale on why the response body is
                # redacted but partial_state is still persisted, AND for why this
                # catch MUST precede `except ComposerServiceError` below.
                response_body = await _handle_plugin_crash(
                    crash,
                    service,
                    session.id,
                    str(user.user_id),
                    "recompose",
                )
                await _publish_progress(
                    progress_registry,
                    session_id=str(session.id),
                    request_id=request_id,
                    event=ComposerProgressEvent(
                        phase="failed",
                        headline="The composer could not safely finish this retry.",
                        evidence=("A pipeline tool failed on the server side.",),
                        likely_next="Review the visible error message, then retry after the issue is resolved.",
                    ),
                )
                raise HTTPException(status_code=500, detail=response_body) from crash.original_exc
            except ComposerServiceError as exc:
                await _publish_progress(
                    progress_registry,
                    session_id=str(session.id),
                    request_id=request_id,
                    event=ComposerProgressEvent(
                        phase="failed",
                        headline="The composer could not finish this retry.",
                        evidence=("Prompt preparation or composer service setup failed.",),
                        likely_next="Retry once the composer service is available.",
                    ),
                )
                raise HTTPException(
                    status_code=502,
                    detail={"error_type": "composer_error", "detail": str(exc)},
                ) from exc

            # Save state if version changed
            state_response: CompositionStateResponse | None = None
            post_compose_state_id: UUID | None = pre_send_state_id
            if result.state.version != state.version:
                await _publish_progress(
                    progress_registry,
                    session_id=str(session.id),
                    request_id=request_id,
                    event=ComposerProgressEvent(
                        phase="validating",
                        headline="The composer has updated the pipeline and is validating the result.",
                        evidence=("The updated pipeline state is being checked before persistence.",),
                        likely_next="ELSPETH will save the validated pipeline snapshot.",
                    ),
                )
                state_d = result.state.to_dict()
                validation = result.state.validate()
                state_data = CompositionStateData(
                    source=state_d["source"],
                    nodes=state_d["nodes"],
                    edges=state_d["edges"],
                    outputs=state_d["outputs"],
                    metadata_=state_d["metadata"],
                    is_valid=validation.is_valid,
                    validation_errors=[e.message for e in validation.errors] if validation.errors else None,
                )
                await _publish_progress(
                    progress_registry,
                    session_id=str(session.id),
                    request_id=request_id,
                    event=ComposerProgressEvent(
                        phase="saving",
                        headline="ELSPETH is saving the pipeline update.",
                        evidence=("A new composition state version is being stored for this session.",),
                        likely_next="The assistant response will appear after the save completes.",
                    ),
                )
                new_state_record = await service.save_composition_state(
                    session.id,
                    state_data,
                )
                state_response = _state_response(new_state_record, live_validation=validation)
                post_compose_state_id = new_state_record.id

            # Persist assistant message
            assistant_msg = await service.add_message(
                session.id,
                "assistant",
                result.message,
                composition_state_id=post_compose_state_id,
            )
            await _publish_progress(
                progress_registry,
                session_id=str(session.id),
                request_id=request_id,
                event=ComposerProgressEvent(
                    phase="complete",
                    headline="The composer has updated the pipeline."
                    if result.state.version != state.version
                    else "The composer response is ready.",
                    evidence=("The assistant response has been saved for this session.",),
                    likely_next="Review the response and current pipeline.",
                ),
            )

            return MessageWithStateResponse(
                message=_message_response(assistant_msg),
                state=state_response,
            )

    @router.get(
        "/{session_id}/messages",
        response_model=list[ChatMessageResponse],
    )
    async def get_messages(
        session_id: UUID,
        request: Request,
        user: UserIdentity = Depends(get_current_user),  # noqa: B008
        limit: int = Query(100, ge=1, le=500),
        offset: int = Query(0, ge=0),
    ) -> list[ChatMessageResponse]:
        """Get conversation history for a session."""
        session = await _verify_session_ownership(session_id, user, request)
        service = request.app.state.session_service
        messages = await service.get_messages(session.id, limit=limit, offset=offset)
        return [_message_response(m) for m in messages]

    @router.get(
        "/{session_id}/runs",
        response_model=list[RunResponse],
    )
    async def list_session_runs(
        session_id: UUID,
        request: Request,
        user: UserIdentity = Depends(get_current_user),  # noqa: B008
    ) -> list[RunResponse]:
        """List all runs for a session, newest first."""
        session = await _verify_session_ownership(session_id, user, request)
        service: SessionServiceProtocol = request.app.state.session_service
        runs = await service.list_runs_for_session(session.id)
        from elspeth.web.execution.discard_summary import load_discard_summaries_for_settings

        discard_summaries = await asyncio.to_thread(
            load_discard_summaries_for_settings,
            request.app.state.settings,
            (run.landscape_run_id for run in runs),
        )

        # Resolve composition_version from each run's state_id.
        # A missing state is Tier 1 data corruption — crash, don't hide.
        # Scope the read to the current session: the current-schema
        # composite FK prevents cross-session state refs at the schema
        # layer. ``get_state_in_session`` raises
        # ``AuditIntegrityError`` on session mismatch, surfacing Tier 1
        # corruption rather than silently returning the wrong state's
        # version number in another session's listing.
        responses: list[RunResponse] = []
        for run in runs:
            state = await service.get_state_in_session(run.state_id, session.id)
            version = state.version
            discard_summary = None
            if run.landscape_run_id is not None and run.landscape_run_id in discard_summaries:
                discard_summary = discard_summaries[run.landscape_run_id]
            responses.append(
                RunResponse(
                    id=str(run.id),
                    session_id=str(run.session_id),
                    status=run.status,
                    rows_processed=run.rows_processed,
                    rows_failed=run.rows_failed,
                    error=run.error,
                    started_at=run.started_at,
                    finished_at=run.finished_at,
                    composition_version=version,
                    discard_summary=discard_summary,
                )
            )
        return responses

    @router.get("/{session_id}/state")
    async def get_current_state(
        session_id: UUID,
        request: Request,
        user: UserIdentity = Depends(get_current_user),  # noqa: B008
    ) -> CompositionStateResponse | None:
        """Get the current (highest-version) composition state."""
        session = await _verify_session_ownership(session_id, user, request)
        service = request.app.state.session_service
        state = await service.get_current_state(session.id)
        if state is None:
            return None
        return _state_response(state)

    @router.get(
        "/{session_id}/state/versions",
        response_model=list[CompositionStateResponse],
    )
    async def get_state_versions(
        session_id: UUID,
        request: Request,
        user: UserIdentity = Depends(get_current_user),  # noqa: B008
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
    ) -> list[CompositionStateResponse]:
        """Get composition state versions for a session."""
        session = await _verify_session_ownership(session_id, user, request)
        service = request.app.state.session_service
        versions = await service.get_state_versions(session.id, limit=limit, offset=offset)
        return [_state_response(v) for v in versions]

    @router.post(
        "/{session_id}/state/revert",
        response_model=CompositionStateResponse,
    )
    async def revert_state(
        session_id: UUID,
        body: RevertStateRequest,
        request: Request,
        user: UserIdentity = Depends(get_current_user),  # noqa: B008
    ) -> CompositionStateResponse:
        """Revert the pipeline to a prior composition state version (R1).

        Creates a new version that is a copy of the specified prior state.
        Injects a system message recording the revert.
        """
        session = await _verify_session_ownership(session_id, user, request)
        service = request.app.state.session_service

        try:
            new_state = await service.set_active_state(
                session.id,
                body.state_id,
            )
        except ValueError:
            raise HTTPException(
                status_code=404,
                detail="State not found",
            ) from None

        # Look up the original version number for the system message
        original_state = await service.get_state(body.state_id)
        await service.add_message(
            session.id,
            role="system",
            content=f"Pipeline reverted to version {original_state.version}.",
        )

        return _state_response(new_state)

    @router.get("/{session_id}/state/yaml")
    async def get_state_yaml(
        session_id: UUID,
        request: Request,
        user: UserIdentity = Depends(get_current_user),  # noqa: B008
    ) -> dict[str, str]:
        """Get YAML representation of the current composition state (M1).

        Reconstructs a CompositionState from the persisted record and
        re-validates it before generating deterministic YAML via
        generate_yaml().
        """
        session = await _verify_session_ownership(session_id, user, request)
        service: SessionServiceProtocol = request.app.state.session_service
        state_record = await service.get_current_state(session.id)
        if state_record is None:
            raise HTTPException(status_code=404, detail="No composition state exists")
        state = _state_from_record(state_record)
        validation = state.validate()
        if not validation.is_valid:
            raise HTTPException(
                status_code=409,
                detail="Current composition state is invalid. Fix validation errors before exporting YAML.",
            )
        yaml_str = generate_yaml(state)
        return {"yaml": yaml_str}

    @router.post(
        "/{session_id}/fork",
        status_code=201,
        response_model=ForkSessionResponse,
    )
    async def fork_from_message(
        session_id: UUID,
        body: ForkSessionRequest,
        request: Request,
        user: UserIdentity = Depends(get_current_user),  # noqa: B008
    ) -> ForkSessionResponse:
        """Fork a session from a specific user message.

        Creates a new session inheriting history and composition state up to
        the fork point, with the edited message replacing the original.
        The original session is never mutated.
        """
        await _verify_session_ownership(session_id, user, request)
        service: SessionServiceProtocol = request.app.state.session_service
        settings = request.app.state.settings

        try:
            new_session, new_messages, copied_state = await service.fork_session(
                source_session_id=session_id,
                fork_message_id=body.from_message_id,
                new_message_content=body.new_message_content,
                user_id=user.user_id,
                auth_provider_type=settings.auth_provider,
            )
        except InvalidForkTargetError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        # Everything after fork_session() is a compensatable post-commit
        # phase.  If ANY step fails, archive the fork to avoid orphaned
        # sessions/blobs/state.  BlobQuotaExceededError gets a specific
        # 413; all other failures re-raise after cleanup.
        blob_service: BlobServiceProtocol = request.app.state.blob_service
        try:
            source_blobs = await blob_service.list_blobs(session_id)
            # Copy blobs from source session into the forked session.
            # Returns old_id → new_blob mapping for source reference rewriting.
            blob_map = await blob_service.copy_blobs_for_fork(session_id, new_session.id)
            source_blob_path_map = {blob.storage_path: blob_map[blob.id] for blob in source_blobs if blob.id in blob_map}

            # Rewrite source references in the forked state so the fork is
            # self-contained.  Without this, blob_ref and path in the source
            # options still point at the original session's assets.
            if copied_state is not None and copied_state.source is not None and blob_map:
                source_dict = deep_thaw(copied_state.source) if copied_state.source else None
                if not isinstance(source_dict, dict):
                    raise AuditIntegrityError(
                        f"Tier 1 audit anomaly: composition_state {copied_state.id} "
                        f"has source type {type(source_dict).__name__}, expected dict "
                        f"before fork blob rewrite for session {new_session.id}."
                    )

                options = source_dict.get("options")
                if options is None:
                    rewritten = False
                else:
                    if not isinstance(options, dict):
                        raise AuditIntegrityError(
                            f"Tier 1 audit anomaly: composition_state {copied_state.id} "
                            f"has source.options type {type(options).__name__}, expected "
                            f"dict before fork blob rewrite for session {new_session.id}."
                        )

                    rewritten = False
                    rewrite_target = None
                    # Remap blob_ref to the new blob's ID.
                    # composition_states.source is Tier 1 ("our data") — the
                    # composer writes blob_ref as the blob's UUID string
                    # (composer/tools.py _execute_set_source_from_blob).  A
                    # non-UUID value here means a write-path bug, DB
                    # corruption, or tampering — crash with a diagnostic
                    # rather than silently skipping the remap.  Silent skip
                    # would leave the forked state's blob_ref pointing at
                    # the source session's blob, which is the cross-session
                    # reference class closed at the FK layer by the
                    # current-schema composite FK and is audit-contradictory
                    # on its face.  The enclosing ``except Exception``
                    # block archives the partially-created fork (see the
                    # cleanup-rollback site below), so this crash does
                    # not leak artifacts.
                    old_ref = options.get("blob_ref")
                    if old_ref is not None:
                        try:
                            old_uuid = UUID(old_ref) if isinstance(old_ref, str) else old_ref
                        except ValueError as exc:
                            raise AuditIntegrityError(
                                f"Tier 1 audit anomaly: composition_state "
                                f"{copied_state.id} has non-UUID blob_ref "
                                f"{old_ref!r} in source.options (expected a "
                                f"UUID string written by composer/tools.py). "
                                f"Fork aborted to prevent cross-session blob "
                                f"reference in forked session {new_session.id}."
                            ) from exc
                        rewrite_target = blob_map.get(old_uuid)

                    if rewrite_target is None:
                        for path_key in ("path", "file"):
                            path_value = options.get(path_key)
                            if isinstance(path_value, str) and path_value in source_blob_path_map:
                                rewrite_target = source_blob_path_map[path_value]
                                break

                    if rewrite_target is not None:
                        options["blob_ref"] = str(rewrite_target.id)
                        if "path" in options or "file" not in options:
                            options["path"] = rewrite_target.storage_path
                        if "file" in options:
                            options["file"] = rewrite_target.storage_path
                        rewritten = True

                if rewritten:
                    source_dict["options"] = options
                    # Save updated state with remapped source
                    state_data = CompositionStateData(
                        source=source_dict,
                        nodes=deep_thaw(copied_state.nodes),
                        edges=deep_thaw(copied_state.edges),
                        outputs=deep_thaw(copied_state.outputs),
                        metadata_=deep_thaw(copied_state.metadata_),
                        is_valid=copied_state.is_valid,
                        validation_errors=list(copied_state.validation_errors) if copied_state.validation_errors else None,
                    )
                    copied_state = await service.save_composition_state(
                        new_session.id,
                        state_data,
                    )

                    # The edited user message (last in list) still references
                    # the pre-rewrite state.  Re-point it at the replacement
                    # state so message-state lineage is self-contained.
                    user_msg = new_messages[-1]
                    await service.update_message_composition_state(
                        user_msg.id,
                        copied_state.id,
                    )
                    new_messages[-1] = ChatMessageRecord(
                        id=user_msg.id,
                        session_id=user_msg.session_id,
                        role=user_msg.role,
                        content=user_msg.content,
                        tool_calls=user_msg.tool_calls,
                        created_at=user_msg.created_at,
                        composition_state_id=copied_state.id,
                    )
        except BlobQuotaExceededError:
            # Build the HTTPException up-front so cleanup failures can be
            # attached as a note on the object that actually propagates —
            # the inner BlobQuotaExceededError is suppressed by `from None`
            # and any note attached to it would never reach operator logs.
            # Cleanup catch is narrowed to recoverable IO/DB failures so
            # programmer bugs (AttributeError, TypeError) still crash.
            quota_exc = HTTPException(
                status_code=413,
                detail="Blob quota exceeded during fork — unable to copy files",
            )
            try:
                await service.archive_session(new_session.id)
            except (SQLAlchemyError, OSError) as cleanup_exc:
                quota_exc.add_note(
                    f"RecoveryFailed[{type(cleanup_exc).__name__}]: "
                    f"could not archive forked session {new_session.id} "
                    f"after blob quota rollback ({cleanup_exc}). "
                    f"Manual cleanup of sessions.id={new_session.id} required."
                )
            raise quota_exc from None
        except Exception as primary_exc:
            # Mirror the RecoveryFailed[...] convention from
            # ``BlobServiceImpl.copy_blobs_for_fork`` and
            # ``BlobServiceImpl.finalize_run_output_blobs`` (web/blobs/service.py):
            # cleanup failures must NOT mask the original error.  Narrow the
            # catch to (SQLAlchemyError, OSError) — programmer bugs in
            # archive_session must propagate — and attach the cleanup
            # failure as a note so the orphan session row is visible to
            # operators reading the traceback.  Bare `raise` preserves
            # primary_exc and its original traceback as the headline.
            try:
                await service.archive_session(new_session.id)
            except (SQLAlchemyError, OSError) as cleanup_exc:
                primary_exc.add_note(
                    f"RecoveryFailed[{type(cleanup_exc).__name__}]: "
                    f"could not archive forked session {new_session.id} "
                    f"during fork rollback ({cleanup_exc}). "
                    f"Manual cleanup of sessions.id={new_session.id} required."
                )
            raise

        return ForkSessionResponse(
            session=_session_response(new_session),
            messages=[_message_response(m) for m in new_messages],
            composition_state=_state_response(copied_state) if copied_state else None,
        )

    return router
